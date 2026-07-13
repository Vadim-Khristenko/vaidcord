//! Discord voice gateway (websocket) client — protocol v8.
//!
//! The protocol logic lives in [`VoiceGatewayState`], a synchronous state
//! machine that consumes decoded payloads and yields [`VoiceGatewayNotice`]s;
//! this keeps identify/resume/heartbeat (with `seq_ack`), READY, the session
//! description and the SSRC map fully unit-testable without a network.
//! [`VoiceGatewayClient`] wires the state machine to a real websocket.

use std::collections::HashMap;

use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use tokio::sync::mpsc;
use tokio::time::Duration;
use tokio_tungstenite::tungstenite::Message as WsMessage;

use crate::error::Error;

/// Voice gateway protocol version spoken by this client.
pub const VOICE_GATEWAY_VERSION: u8 = 8;

// --------------------------------------------------------------------- //
// Close-code policy                                                     //
// --------------------------------------------------------------------- //

/// What to do when the voice websocket closes with a given code.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VoiceCloseAction {
    /// Reconnect and send op 7 RESUME.
    Resume,
    /// Session is invalid: leave + rejoin the channel (fresh IDENTIFY).
    Rejoin,
    /// Reconnecting is pointless or forbidden.
    Fatal,
}

/// Classify a voice close code (mirrors
/// `vaidcord-py/src/vaidcord/voice/connection.py`).
pub fn classify_voice_close_code(close_code: Option<u16>) -> VoiceCloseAction {
    match close_code {
        Some(4001) | Some(4002) | Some(4003) | Some(4004) | Some(4005) | Some(4011)
        | Some(4012) | Some(4014) | Some(4016) | Some(4017) => VoiceCloseAction::Fatal,
        Some(4006) | Some(4009) => VoiceCloseAction::Rejoin,
        // Unknown/network-level closes (None, 1000, 1006, 4015, ...) are
        // worth a resume attempt; the server rejects it if the session died.
        _ => VoiceCloseAction::Resume,
    }
}

// --------------------------------------------------------------------- //
// Models                                                                //
// --------------------------------------------------------------------- //

/// The op 2 READY payload.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VoiceReady {
    pub ssrc: u32,
    pub ip: String,
    pub port: u16,
    pub modes: Vec<String>,
}

/// The op 4 SESSION DESCRIPTION payload.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VoiceSessionDescription {
    pub mode: String,
    pub secret_key: Vec<u8>,
    pub dave_protocol_version: Option<u8>,
}

/// Speaking flags for the op 5 payload.
pub mod speaking_flags {
    pub const MICROPHONE: u32 = 1 << 0;
    pub const SOUNDSHARE: u32 = 1 << 1;
    pub const PRIORITY: u32 = 1 << 2;
}

// --------------------------------------------------------------------- //
// Payload builders                                                      //
// --------------------------------------------------------------------- //

/// Identity of one voice session (guild, user, session, token).
#[derive(Debug, Clone)]
pub struct VoiceIdentify {
    pub server_id: String,
    pub user_id: String,
    pub session_id: String,
    pub token: String,
    /// When > 0, advertised as `max_dave_protocol_version` in IDENTIFY.
    pub max_dave_protocol_version: u8,
}

pub(crate) fn voice_identify_payload(identify: &VoiceIdentify) -> Value {
    let mut data = json!({
        "server_id": identify.server_id,
        "user_id": identify.user_id,
        "session_id": identify.session_id,
        "token": identify.token,
    });
    if identify.max_dave_protocol_version > 0 {
        data["max_dave_protocol_version"] = json!(identify.max_dave_protocol_version);
    }
    json!({ "op": 0, "d": data })
}

pub(crate) fn voice_resume_payload(identify: &VoiceIdentify, seq_ack: i64) -> Value {
    json!({
        "op": 7,
        "d": {
            "server_id": identify.server_id,
            "session_id": identify.session_id,
            "token": identify.token,
            "seq_ack": seq_ack,
        }
    })
}

pub(crate) fn voice_heartbeat_payload(timestamp_ms: u128, seq_ack: i64) -> Value {
    json!({ "op": 3, "d": { "t": timestamp_ms as u64, "seq_ack": seq_ack } })
}

pub(crate) fn select_protocol_payload(address: &str, port: u16, mode: &str) -> Value {
    json!({
        "op": 1,
        "d": { "protocol": "udp", "data": { "address": address, "port": port, "mode": mode } }
    })
}

/// Build an op 5 Speaking payload.
pub fn speaking_payload(ssrc: u32, speaking: u32, delay: u32) -> Value {
    json!({ "op": 5, "d": { "speaking": speaking, "delay": delay, "ssrc": ssrc } })
}

// --------------------------------------------------------------------- //
// State machine                                                         //
// --------------------------------------------------------------------- //

/// Notices produced by [`VoiceGatewayState::handle_payload`].
#[derive(Debug, Clone, PartialEq)]
pub enum VoiceGatewayNotice {
    /// op 8 HELLO: start heartbeating at this interval.
    Hello { heartbeat_interval: Duration },
    /// op 2 READY.
    Ready(VoiceReady),
    /// op 4 SESSION DESCRIPTION (transport keys negotiated).
    SessionDescription(VoiceSessionDescription),
    /// op 5: a user's speaking state changed.
    Speaking { user_id: u64, ssrc: u32, flags: u32 },
    /// op 6 heartbeat ACK.
    HeartbeatAck,
    /// op 9 RESUMED.
    Resumed,
    /// op 13: a user left; their SSRC mappings were dropped.
    ClientDisconnect { user_id: u64 },
    /// A DAVE opcode (21..=31) arrived; payload preserved for a DAVE backend.
    Dave { op: u8, data: Value },
}

/// Synchronous voice-gateway protocol state: sequence tracking (`seq_ack`),
/// READY/session-description capture and the SSRC -> user map (op 5/12/13).
#[derive(Debug, Default)]
pub struct VoiceGatewayState {
    last_sequence: i64,
    ready: Option<VoiceReady>,
    session_description: Option<VoiceSessionDescription>,
    ssrc_to_user: HashMap<u32, u64>,
}

impl VoiceGatewayState {
    pub fn new() -> Self {
        Self {
            last_sequence: -1,
            ..Self::default()
        }
    }

    /// Last received server sequence number (`-1` before the first one),
    /// echoed back as `seq_ack` in heartbeats and RESUME.
    pub fn seq_ack(&self) -> i64 {
        self.last_sequence
    }

    pub fn ready(&self) -> Option<&VoiceReady> {
        self.ready.as_ref()
    }

    pub fn session_description(&self) -> Option<&VoiceSessionDescription> {
        self.session_description.as_ref()
    }

    /// Resolve an RTP SSRC to the user it belongs to (learned from op 5/12).
    pub fn ssrc_to_user(&self, ssrc: u32) -> Option<u64> {
        self.ssrc_to_user.get(&ssrc).copied()
    }

    /// A snapshot of the SSRC -> user map.
    pub fn ssrc_map(&self) -> &HashMap<u32, u64> {
        &self.ssrc_to_user
    }

    /// Consume one decoded gateway payload, updating state and returning a
    /// notice when the payload is meaningful to the caller.
    pub fn handle_payload(&mut self, payload: &Value) -> Option<VoiceGatewayNotice> {
        if let Some(seq) = payload.get("seq").and_then(Value::as_i64) {
            self.last_sequence = seq;
        }
        let op = payload.get("op").and_then(Value::as_i64).unwrap_or(-1);
        let data = payload.get("d").cloned().unwrap_or(Value::Null);
        match op {
            8 => {
                let interval_ms = data
                    .get("heartbeat_interval")
                    .and_then(Value::as_f64)
                    .unwrap_or(41_250.0);
                Some(VoiceGatewayNotice::Hello {
                    heartbeat_interval: Duration::from_millis(interval_ms as u64),
                })
            }
            2 => {
                let ready = VoiceReady {
                    ssrc: data.get("ssrc").and_then(Value::as_u64).unwrap_or(0) as u32,
                    ip: data
                        .get("ip")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    port: data.get("port").and_then(Value::as_u64).unwrap_or(0) as u16,
                    modes: data
                        .get("modes")
                        .and_then(Value::as_array)
                        .map(|modes| {
                            modes
                                .iter()
                                .filter_map(Value::as_str)
                                .map(str::to_string)
                                .collect()
                        })
                        .unwrap_or_default(),
                };
                self.ready = Some(ready.clone());
                Some(VoiceGatewayNotice::Ready(ready))
            }
            4 => {
                let description = VoiceSessionDescription {
                    mode: data
                        .get("mode")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    secret_key: data
                        .get("secret_key")
                        .and_then(Value::as_array)
                        .map(|bytes| {
                            bytes
                                .iter()
                                .filter_map(Value::as_u64)
                                .map(|byte| byte as u8)
                                .collect()
                        })
                        .unwrap_or_default(),
                    dave_protocol_version: data
                        .get("dave_protocol_version")
                        .and_then(Value::as_u64)
                        .map(|version| version as u8),
                };
                self.session_description = Some(description.clone());
                Some(VoiceGatewayNotice::SessionDescription(description))
            }
            5 => {
                let ssrc = data.get("ssrc").and_then(Value::as_u64)? as u32;
                let user_id = parse_user_id(data.get("user_id")?)?;
                let flags = data.get("speaking").and_then(Value::as_u64).unwrap_or(0) as u32;
                self.ssrc_to_user.insert(ssrc, user_id);
                Some(VoiceGatewayNotice::Speaking {
                    user_id,
                    ssrc,
                    flags,
                })
            }
            6 => Some(VoiceGatewayNotice::HeartbeatAck),
            9 => Some(VoiceGatewayNotice::Resumed),
            12 => {
                // Video announcement also carries the sender's audio SSRC.
                let user_id = parse_user_id(data.get("user_id")?)?;
                if let Some(audio_ssrc) = data.get("audio_ssrc").and_then(Value::as_u64)
                    && audio_ssrc != 0
                {
                    self.ssrc_to_user.insert(audio_ssrc as u32, user_id);
                }
                None
            }
            13 => {
                let user_id = parse_user_id(data.get("user_id")?)?;
                self.ssrc_to_user.retain(|_, mapped| *mapped != user_id);
                Some(VoiceGatewayNotice::ClientDisconnect { user_id })
            }
            21..=31 => Some(VoiceGatewayNotice::Dave {
                op: op as u8,
                data,
            }),
            _ => None,
        }
    }
}

fn parse_user_id(value: &Value) -> Option<u64> {
    match value {
        Value::String(text) => text.parse().ok(),
        Value::Number(number) => number.as_u64(),
        _ => None,
    }
}

// --------------------------------------------------------------------- //
// Websocket client                                                      //
// --------------------------------------------------------------------- //

/// Events emitted by a running [`VoiceGatewayClient`].
#[derive(Debug)]
pub enum VoiceGatewayEvent {
    Notice(VoiceGatewayNotice),
    /// The socket closed; `action` is the reconnect policy for the code.
    Closed {
        close_code: Option<u16>,
        action: VoiceCloseAction,
    },
    Error(Error),
}

/// A live voice gateway websocket connection.
///
/// Heartbeats (op 3 with `t` + `seq_ack`) run on an independent tokio task
/// started when HELLO arrives. Use [`VoiceGatewayClient::send`] for
/// select-protocol / speaking payloads and [`VoiceGatewayClient::next_event`]
/// to consume notices.
pub struct VoiceGatewayClient {
    outbound: mpsc::Sender<Value>,
    events: mpsc::Receiver<VoiceGatewayEvent>,
}

impl VoiceGatewayClient {
    /// Connect to `wss://{endpoint}/?v=8` and identify (or resume when
    /// `resume_seq_ack` is `Some`).
    pub async fn connect(
        endpoint: &str,
        identify: VoiceIdentify,
        resume_seq_ack: Option<i64>,
    ) -> Result<Self, Error> {
        let url = normalize_voice_endpoint(endpoint);
        let (stream, _) = tokio_tungstenite::connect_async(url).await?;
        let (outbound_tx, outbound_rx) = mpsc::channel(64);
        let (events_tx, events_rx) = mpsc::channel(256);
        tokio::spawn(run_voice_socket(
            stream,
            identify,
            resume_seq_ack,
            outbound_tx.clone(),
            outbound_rx,
            events_tx,
        ));
        Ok(Self {
            outbound: outbound_tx,
            events: events_rx,
        })
    }

    /// Send a raw payload (select protocol, speaking, DAVE, ...).
    pub async fn send(&self, payload: Value) -> Result<(), Error> {
        self.outbound
            .send(payload)
            .await
            .map_err(|_| Error::Voice("voice gateway connection is closed".to_string()))
    }

    /// Send an op 5 speaking update.
    pub async fn set_speaking(&self, ssrc: u32, speaking: u32) -> Result<(), Error> {
        self.send(speaking_payload(ssrc, speaking, 0)).await
    }

    /// Send op 1 SELECT PROTOCOL after IP discovery.
    pub async fn select_protocol(
        &self,
        address: &str,
        port: u16,
        mode: &str,
    ) -> Result<(), Error> {
        self.send(select_protocol_payload(address, port, mode)).await
    }

    /// Next protocol notice / lifecycle event (`None` once disconnected).
    pub async fn next_event(&mut self) -> Option<VoiceGatewayEvent> {
        self.events.recv().await
    }
}

fn normalize_voice_endpoint(endpoint: &str) -> String {
    let trimmed = endpoint.trim_end_matches('/');
    if trimmed.starts_with("ws://") || trimmed.starts_with("wss://") {
        format!("{trimmed}/?v={VOICE_GATEWAY_VERSION}")
    } else {
        format!("wss://{trimmed}/?v={VOICE_GATEWAY_VERSION}")
    }
}

async fn run_voice_socket(
    stream: tokio_tungstenite::WebSocketStream<
        tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
    >,
    identify: VoiceIdentify,
    resume_seq_ack: Option<i64>,
    outbound_tx: mpsc::Sender<Value>,
    mut outbound_rx: mpsc::Receiver<Value>,
    events: mpsc::Sender<VoiceGatewayEvent>,
) {
    let (mut sink, mut stream) = stream.split();
    let mut state = VoiceGatewayState::new();
    if let Some(seq) = resume_seq_ack {
        // Preserve the pre-reconnect sequence for the RESUME payload.
        state.last_sequence = seq;
    }
    let mut heartbeat_task: Option<tokio::task::JoinHandle<()>> = None;
    let (seq_tx, _) = tokio::sync::watch::channel(state.seq_ack());
    let mut close_code: Option<u16> = None;

    // Handshake: identify or resume.
    let handshake = if resume_seq_ack.is_some() {
        voice_resume_payload(&identify, state.seq_ack())
    } else {
        voice_identify_payload(&identify)
    };
    if sink
        .send(WsMessage::Text(handshake.to_string()))
        .await
        .is_err()
    {
        let _ = events
            .send(VoiceGatewayEvent::Closed {
                close_code: None,
                action: VoiceCloseAction::Resume,
            })
            .await;
        return;
    }

    loop {
        tokio::select! {
            incoming = stream.next() => {
                let message = match incoming {
                    None => break,
                    Some(Err(error)) => {
                        let _ = events.send(VoiceGatewayEvent::Error(error.into())).await;
                        break;
                    }
                    Some(Ok(message)) => message,
                };
                match message {
                    WsMessage::Close(frame) => {
                        close_code = frame.map(|frame| u16::from(frame.code));
                    }
                    WsMessage::Text(text) => {
                        let payload: Value = match serde_json::from_str(&text) {
                            Ok(payload) => payload,
                            Err(error) => {
                                let _ = events.send(VoiceGatewayEvent::Error(error.into())).await;
                                continue;
                            }
                        };
                        let notice = state.handle_payload(&payload);
                        let _ = seq_tx.send(state.seq_ack());
                        if let Some(notice) = notice {
                            if let VoiceGatewayNotice::Hello { heartbeat_interval } = &notice {
                                if let Some(task) = heartbeat_task.take() {
                                    task.abort();
                                }
                                heartbeat_task = Some(tokio::spawn(voice_heartbeat_loop(
                                    *heartbeat_interval,
                                    outbound_tx.clone(),
                                    seq_tx.subscribe(),
                                )));
                            }
                            if events.send(VoiceGatewayEvent::Notice(notice)).await.is_err() {
                                break;
                            }
                        }
                    }
                    _ => {}
                }
            }
            payload = outbound_rx.recv() => match payload {
                Some(payload) => {
                    if sink.send(WsMessage::Text(payload.to_string())).await.is_err() {
                        break;
                    }
                }
                None => break,
            },
        }
    }

    if let Some(task) = heartbeat_task.take() {
        task.abort();
    }
    let action = classify_voice_close_code(close_code);
    let _ = events
        .send(VoiceGatewayEvent::Closed { close_code, action })
        .await;
}

/// Independent heartbeat task for the voice websocket (op 3 with the
/// millisecond timestamp nonce and the latest `seq_ack`).
async fn voice_heartbeat_loop(
    interval: Duration,
    outbound: mpsc::Sender<Value>,
    seq_ack: tokio::sync::watch::Receiver<i64>,
) {
    let mut ticker = tokio::time::interval(interval.max(Duration::from_millis(1)));
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    loop {
        ticker.tick().await;
        let timestamp_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|duration| duration.as_millis())
            .unwrap_or(0);
        let payload = voice_heartbeat_payload(timestamp_ms, *seq_ack.borrow());
        if outbound.send(payload).await.is_err() {
            return;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Ports of the close-code and connection-event cases in
    // vaidcord-py/tests/test_voice_protocol.py.

    #[test]
    fn classify_voice_close_code_matches_python_sdk() {
        use VoiceCloseAction::*;
        for (code, action) in [
            (None, Resume),
            (Some(1000), Resume),
            (Some(1006), Resume),
            (Some(4015), Resume),
            (Some(4006), Rejoin),
            (Some(4009), Rejoin),
            (Some(4004), Fatal),
            (Some(4014), Fatal),
            (Some(4017), Fatal),
        ] {
            assert_eq!(classify_voice_close_code(code), action, "code {code:?}");
        }
    }

    fn identify() -> VoiceIdentify {
        VoiceIdentify {
            server_id: "10".into(),
            user_id: "30".into(),
            session_id: "session".into(),
            token: "token".into(),
            max_dave_protocol_version: 0,
        }
    }

    #[test]
    fn identify_payload_shape() {
        let payload = voice_identify_payload(&identify());
        assert_eq!(payload["op"], 0);
        assert_eq!(payload["d"]["server_id"], "10");
        assert_eq!(payload["d"]["session_id"], "session");
        assert!(payload["d"].get("max_dave_protocol_version").is_none());

        let mut dave = identify();
        dave.max_dave_protocol_version = 1;
        assert_eq!(
            voice_identify_payload(&dave)["d"]["max_dave_protocol_version"],
            1
        );
    }

    #[test]
    fn resume_payload_carries_seq_ack() {
        let payload = voice_resume_payload(&identify(), 41);
        assert_eq!(payload["op"], 7);
        assert_eq!(payload["d"]["seq_ack"], 41);
        assert_eq!(payload["d"]["server_id"], "10");
        assert!(payload["d"].get("user_id").is_none());
    }

    #[test]
    fn heartbeat_payload_carries_timestamp_and_seq_ack() {
        let payload = voice_heartbeat_payload(1_700_000_000_000, 7);
        assert_eq!(payload["op"], 3);
        assert_eq!(payload["d"]["t"], 1_700_000_000_000u64);
        assert_eq!(payload["d"]["seq_ack"], 7);
    }

    #[test]
    fn speaking_and_select_protocol_payload_shapes() {
        let speaking = speaking_payload(321, speaking_flags::MICROPHONE, 0);
        assert_eq!(speaking["op"], 5);
        assert_eq!(speaking["d"]["ssrc"], 321);
        assert_eq!(speaking["d"]["speaking"], 1);

        let select = select_protocol_payload("203.0.113.1", 50004, "aead_aes256_gcm_rtpsize");
        assert_eq!(select["op"], 1);
        assert_eq!(select["d"]["protocol"], "udp");
        assert_eq!(select["d"]["data"]["mode"], "aead_aes256_gcm_rtpsize");
    }

    #[test]
    fn state_tracks_hello_ready_and_session_description() {
        let mut state = VoiceGatewayState::new();
        assert_eq!(state.seq_ack(), -1);

        let hello = state
            .handle_payload(&serde_json::json!({"op": 8, "d": {"heartbeat_interval": 13750.0}}))
            .unwrap();
        assert_eq!(
            hello,
            VoiceGatewayNotice::Hello {
                heartbeat_interval: Duration::from_millis(13750)
            }
        );

        state.handle_payload(&serde_json::json!({
            "op": 2, "seq": 1,
            "d": {"ssrc": 321, "ip": "127.0.0.1", "port": 5000, "modes": ["aead_aes256_gcm_rtpsize"]}
        }));
        assert_eq!(state.seq_ack(), 1);
        let ready = state.ready().unwrap();
        assert_eq!(ready.ssrc, 321);
        assert_eq!(ready.port, 5000);

        state.handle_payload(&serde_json::json!({
            "op": 4, "seq": 2,
            "d": {"mode": "aead_aes256_gcm_rtpsize", "secret_key": (0..32).collect::<Vec<u8>>()}
        }));
        let description = state.session_description().unwrap();
        assert_eq!(description.secret_key.len(), 32);
        assert_eq!(state.seq_ack(), 2);
    }

    #[test]
    fn state_tracks_speaking_ssrc_map_and_disconnects() {
        let mut state = VoiceGatewayState::new();
        let notice = state
            .handle_payload(
                &serde_json::json!({"op": 5, "d": {"ssrc": 555, "user_id": "42", "speaking": 1}}),
            )
            .unwrap();
        assert_eq!(
            notice,
            VoiceGatewayNotice::Speaking {
                user_id: 42,
                ssrc: 555,
                flags: 1
            }
        );
        assert_eq!(state.ssrc_to_user(555), Some(42));

        state.handle_payload(&serde_json::json!({"op": 13, "d": {"user_id": "42"}}));
        assert_eq!(state.ssrc_to_user(555), None);
    }

    #[test]
    fn state_maps_audio_ssrc_from_video_payload() {
        let mut state = VoiceGatewayState::new();
        state.handle_payload(&serde_json::json!({
            "op": 12, "d": {"user_id": "9", "audio_ssrc": 777, "video_ssrc": 778}
        }));
        assert_eq!(state.ssrc_to_user(777), Some(9));
        assert_eq!(state.ssrc_to_user(778), None);
    }

    #[test]
    fn state_signals_resumed_on_op9() {
        let mut state = VoiceGatewayState::new();
        assert_eq!(
            state.handle_payload(&serde_json::json!({"op": 9, "d": {}})),
            Some(VoiceGatewayNotice::Resumed)
        );
    }

    #[test]
    fn state_forwards_dave_opcodes() {
        let mut state = VoiceGatewayState::new();
        let notice = state
            .handle_payload(&serde_json::json!({"op": 21, "d": {"transition_id": 3}}))
            .unwrap();
        match notice {
            VoiceGatewayNotice::Dave { op, data } => {
                assert_eq!(op, 21);
                assert_eq!(data["transition_id"], 3);
            }
            other => panic!("expected Dave notice, got {other:?}"),
        }
    }

    #[test]
    fn voice_endpoint_is_normalized_to_v8() {
        assert_eq!(
            normalize_voice_endpoint("voice.example.com"),
            "wss://voice.example.com/?v=8"
        );
        assert_eq!(
            normalize_voice_endpoint("wss://voice.example.com/"),
            "wss://voice.example.com/?v=8"
        );
    }
}
