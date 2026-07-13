//! Discord gateway (websocket) client.
//!
//! Features:
//!
//! * Heartbeat on an independent tokio task (interval from HELLO, jittered
//!   first beat) with ACK tracking — a missed ACK forces a resume-reconnect.
//! * RESUME support: `session_id` + `resume_gateway_url` + last sequence are
//!   tracked and replayed on reconnect.
//! * Automatic reconnect with exponential backoff and a close-code policy
//!   (fatal vs resume vs re-identify) per the Discord docs.
//! * Typed [`Intents`], op 3 presence updates and op 8 guild-member requests
//!   through a cloneable [`GatewayHandle`].

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicI64, Ordering};

use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tokio::sync::mpsc;
use tokio::time::{Duration, Instant};
use tokio_tungstenite::tungstenite::Message as WsMessage;

use crate::client::Client;
use crate::error::Error;

// --------------------------------------------------------------------- //
// Intents                                                               //
// --------------------------------------------------------------------- //

/// Typed gateway intents bitflags.
///
/// ```
/// use vaidcord::Intents;
///
/// let intents = Intents::GUILDS | Intents::GUILD_MESSAGES | Intents::MESSAGE_CONTENT;
/// assert!(intents.contains(Intents::GUILD_MESSAGES));
/// ```
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub struct Intents(u64);

impl Intents {
    pub const GUILDS: Intents = Intents(1 << 0);
    pub const GUILD_MEMBERS: Intents = Intents(1 << 1);
    pub const GUILD_MODERATION: Intents = Intents(1 << 2);
    pub const GUILD_EXPRESSIONS: Intents = Intents(1 << 3);
    pub const GUILD_INTEGRATIONS: Intents = Intents(1 << 4);
    pub const GUILD_WEBHOOKS: Intents = Intents(1 << 5);
    pub const GUILD_INVITES: Intents = Intents(1 << 6);
    pub const GUILD_VOICE_STATES: Intents = Intents(1 << 7);
    pub const GUILD_PRESENCES: Intents = Intents(1 << 8);
    pub const GUILD_MESSAGES: Intents = Intents(1 << 9);
    pub const GUILD_MESSAGE_REACTIONS: Intents = Intents(1 << 10);
    pub const GUILD_MESSAGE_TYPING: Intents = Intents(1 << 11);
    pub const DIRECT_MESSAGES: Intents = Intents(1 << 12);
    pub const DIRECT_MESSAGE_REACTIONS: Intents = Intents(1 << 13);
    pub const DIRECT_MESSAGE_TYPING: Intents = Intents(1 << 14);
    pub const MESSAGE_CONTENT: Intents = Intents(1 << 15);
    pub const GUILD_SCHEDULED_EVENTS: Intents = Intents(1 << 16);
    pub const AUTO_MODERATION_CONFIGURATION: Intents = Intents(1 << 20);
    pub const AUTO_MODERATION_EXECUTION: Intents = Intents(1 << 21);
    pub const GUILD_MESSAGE_POLLS: Intents = Intents(1 << 24);
    pub const DIRECT_MESSAGE_POLLS: Intents = Intents(1 << 25);

    /// No intents.
    pub const fn none() -> Intents {
        Intents(0)
    }

    /// Every intent that does not require privileged approval.
    pub const fn unprivileged() -> Intents {
        Intents(
            Self::all().0
                & !(Self::GUILD_MEMBERS.0 | Self::GUILD_PRESENCES.0 | Self::MESSAGE_CONTENT.0),
        )
    }

    /// Every defined intent (including privileged ones).
    pub const fn all() -> Intents {
        Intents(
            Self::GUILDS.0
                | Self::GUILD_MEMBERS.0
                | Self::GUILD_MODERATION.0
                | Self::GUILD_EXPRESSIONS.0
                | Self::GUILD_INTEGRATIONS.0
                | Self::GUILD_WEBHOOKS.0
                | Self::GUILD_INVITES.0
                | Self::GUILD_VOICE_STATES.0
                | Self::GUILD_PRESENCES.0
                | Self::GUILD_MESSAGES.0
                | Self::GUILD_MESSAGE_REACTIONS.0
                | Self::GUILD_MESSAGE_TYPING.0
                | Self::DIRECT_MESSAGES.0
                | Self::DIRECT_MESSAGE_REACTIONS.0
                | Self::DIRECT_MESSAGE_TYPING.0
                | Self::MESSAGE_CONTENT.0
                | Self::GUILD_SCHEDULED_EVENTS.0
                | Self::AUTO_MODERATION_CONFIGURATION.0
                | Self::AUTO_MODERATION_EXECUTION.0
                | Self::GUILD_MESSAGE_POLLS.0
                | Self::DIRECT_MESSAGE_POLLS.0,
        )
    }

    /// Raw bit value sent in IDENTIFY.
    pub const fn bits(self) -> u64 {
        self.0
    }

    /// Build from a raw bit value.
    pub const fn from_bits(bits: u64) -> Intents {
        Intents(bits)
    }

    /// Whether every bit in `other` is set in `self`.
    pub const fn contains(self, other: Intents) -> bool {
        self.0 & other.0 == other.0
    }

    /// Whether no intents are set.
    pub const fn is_empty(self) -> bool {
        self.0 == 0
    }
}

impl std::ops::BitOr for Intents {
    type Output = Intents;
    fn bitor(self, rhs: Intents) -> Intents {
        Intents(self.0 | rhs.0)
    }
}

impl std::ops::BitOrAssign for Intents {
    fn bitor_assign(&mut self, rhs: Intents) {
        self.0 |= rhs.0;
    }
}

impl std::ops::BitAnd for Intents {
    type Output = Intents;
    fn bitand(self, rhs: Intents) -> Intents {
        Intents(self.0 & rhs.0)
    }
}

// --------------------------------------------------------------------- //
// Close-code policy                                                     //
// --------------------------------------------------------------------- //

/// What to do after the gateway websocket closes with a given code.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GatewayCloseAction {
    /// Reconnect and send RESUME.
    Resume,
    /// Reconnect with a fresh IDENTIFY (session is gone).
    Reidentify,
    /// Do not reconnect (bad token, bad intents, sharding config, ...).
    Fatal,
}

/// Classify a gateway close code per the Discord developer docs.
///
/// * Fatal: 4004 (auth failed), 4010/4011 (shard errors), 4012 (bad API
///   version), 4013/4014 (bad or disallowed intents).
/// * Re-identify: 4007 (invalid seq), 4009 (session timed out) and normal
///   closures 1000/1001, all of which invalidate the session.
/// * Everything else (including abnormal closes and unknown codes) is worth
///   a RESUME attempt; the server rejects it with op 9 if the session died.
pub fn classify_gateway_close_code(close_code: Option<u16>) -> GatewayCloseAction {
    match close_code {
        Some(4004) | Some(4010) | Some(4011) | Some(4012) | Some(4013) | Some(4014) => {
            GatewayCloseAction::Fatal
        }
        Some(1000) | Some(1001) | Some(4007) | Some(4009) => GatewayCloseAction::Reidentify,
        _ => GatewayCloseAction::Resume,
    }
}

// --------------------------------------------------------------------- //
// Payload types & builders                                              //
// --------------------------------------------------------------------- //

/// A raw gateway payload (`op`/`t`/`s`/`d`).
#[derive(Debug, Clone, Deserialize)]
pub struct GatewayDispatch {
    pub op: i64,
    #[serde(default)]
    pub t: Option<String>,
    #[serde(default)]
    pub s: Option<i64>,
    #[serde(default)]
    pub d: Value,
}

/// Parameters for an op 8 Request Guild Members command.
#[derive(Debug, Clone, Default)]
pub struct GuildMembersRequest {
    pub guild_id: String,
    /// Username prefix to search for; `""` (with `limit: 0`) requests all.
    pub query: String,
    pub limit: u64,
    pub presences: bool,
    /// When set, `query` is ignored and only these users are requested.
    pub user_ids: Option<Vec<String>>,
    pub nonce: Option<String>,
}

/// Parameters for an op 3 Presence Update.
#[derive(Debug, Clone, Serialize)]
pub struct PresenceUpdate {
    pub since: Option<u64>,
    pub activities: Vec<Value>,
    pub status: String,
    pub afk: bool,
}

impl PresenceUpdate {
    /// A simple online presence with a "playing" activity.
    pub fn playing(name: impl Into<String>) -> Self {
        Self {
            since: None,
            activities: vec![json!({ "name": name.into(), "type": 0 })],
            status: "online".to_string(),
            afk: false,
        }
    }

    /// A bare presence with the given status (`online`, `idle`, `dnd`, ...).
    pub fn status(status: impl Into<String>) -> Self {
        Self {
            since: None,
            activities: Vec::new(),
            status: status.into(),
            afk: false,
        }
    }
}

pub(crate) fn identify_payload(token: &str, intents: Intents) -> Value {
    json!({
        "op": 2,
        "d": {
            "token": token,
            "intents": intents.bits(),
            "properties": { "os": "linux", "browser": "vaidcord-rust", "device": "vaidcord-rust" },
            "compress": false,
            "large_threshold": 250,
        }
    })
}

pub(crate) fn resume_payload(token: &str, session_id: &str, seq: i64) -> Value {
    json!({
        "op": 6,
        "d": { "token": token, "session_id": session_id, "seq": seq }
    })
}

pub(crate) fn heartbeat_payload(seq: Option<i64>) -> Value {
    json!({ "op": 1, "d": seq })
}

pub(crate) fn presence_update_payload(presence: &PresenceUpdate) -> Value {
    json!({
        "op": 3,
        "d": {
            "since": presence.since,
            "activities": presence.activities,
            "status": presence.status,
            "afk": presence.afk,
        }
    })
}

pub(crate) fn request_guild_members_payload(request: &GuildMembersRequest) -> Value {
    let mut data = json!({
        "guild_id": request.guild_id,
        "limit": request.limit,
        "presences": request.presences,
    });
    if let Some(user_ids) = &request.user_ids {
        data["user_ids"] = json!(user_ids);
    } else {
        data["query"] = json!(request.query);
    }
    if let Some(nonce) = &request.nonce {
        data["nonce"] = json!(nonce);
    }
    json!({ "op": 8, "d": data })
}

// --------------------------------------------------------------------- //
// Connection plumbing                                                   //
// --------------------------------------------------------------------- //

/// Lifecycle + dispatch notifications emitted by a gateway connection.
#[derive(Debug)]
pub enum GatewayEvent {
    /// An op 0 dispatch.
    Dispatch(GatewayDispatch),
    /// Handshake completed (IDENTIFY acknowledged by READY, or RESUMED).
    Connected { resumed: bool },
    /// The socket closed; the runner acts according to `action`.
    Disconnected {
        close_code: Option<u16>,
        action: GatewayCloseAction,
    },
    /// A non-fatal transport/decoding error.
    Error(Error),
}

#[derive(Debug)]
enum GatewayCommand {
    Send(Value),
    Shutdown,
}

/// Cloneable handle for sending commands into a running gateway connection.
#[derive(Debug, Clone)]
pub struct GatewayHandle {
    commands: mpsc::Sender<GatewayCommand>,
}

impl GatewayHandle {
    /// Send a raw gateway payload (advanced use).
    pub async fn send(&self, payload: Value) -> Result<(), Error> {
        self.commands
            .send(GatewayCommand::Send(payload))
            .await
            .map_err(|_| Error::Other("gateway connection is closed".to_string()))
    }

    /// Send an op 3 Presence Update.
    pub async fn update_presence(&self, presence: &PresenceUpdate) -> Result<(), Error> {
        self.send(presence_update_payload(presence)).await
    }

    /// Send an op 8 Request Guild Members; results arrive as
    /// `GUILD_MEMBERS_CHUNK` dispatches.
    pub async fn request_guild_members(
        &self,
        request: &GuildMembersRequest,
    ) -> Result<(), Error> {
        self.send(request_guild_members_payload(request)).await
    }

    /// Cleanly close the connection and stop the reconnect loop.
    pub async fn shutdown(&self) {
        let _ = self.commands.send(GatewayCommand::Shutdown).await;
    }
}

/// A running gateway connection: an event stream plus a command handle.
#[derive(Debug)]
pub struct GatewayConnection {
    events: mpsc::Receiver<GatewayEvent>,
    handle: GatewayHandle,
}

impl GatewayConnection {
    /// Receive the next lifecycle/dispatch event (`None` when the runner has
    /// stopped for good).
    pub async fn next_event(&mut self) -> Option<GatewayEvent> {
        self.events.recv().await
    }

    /// A cloneable command handle (presence, member requests, shutdown).
    pub fn handle(&self) -> GatewayHandle {
        self.handle.clone()
    }
}

#[derive(Debug, Clone, Default)]
struct SessionState {
    session_id: Option<String>,
    resume_gateway_url: Option<String>,
    seq: Option<i64>,
}

enum ConnectionEnd {
    Shutdown,
    Reconnect { resume: bool },
    Fatal,
}

#[derive(Debug, Clone, Deserialize)]
struct GatewayBotInfo {
    url: String,
}

/// Gateway client: owns the REST [`Client`] used for `/gateway/bot` lookup
/// and spawns resilient websocket connections.
pub struct GatewayClient {
    client: Client,
}

impl GatewayClient {
    pub fn new(client: Client) -> Self {
        Self { client }
    }

    /// Open a resilient gateway connection (auto heartbeat, RESUME,
    /// exponential-backoff reconnect).
    pub async fn connect(&self, intents: Intents) -> Result<GatewayConnection, Error> {
        let (events_tx, events_rx) = mpsc::channel(256);
        let (commands_tx, commands_rx) = mpsc::channel(32);
        let runner = GatewayRunner {
            client: self.client.clone(),
            intents,
            events: events_tx,
            commands: commands_rx,
            session: SessionState::default(),
        };
        tokio::spawn(runner.run());
        Ok(GatewayConnection {
            events: events_rx,
            handle: GatewayHandle {
                commands: commands_tx,
            },
        })
    }

    /// Back-compat: stream only op 0 dispatches plus a separate error channel.
    ///
    /// Prefer [`GatewayClient::connect`] which also exposes lifecycle events
    /// and a command handle.
    pub async fn stream_updates(
        &self,
        intents: u64,
    ) -> Result<(mpsc::Receiver<GatewayDispatch>, mpsc::Receiver<Error>), Error> {
        let mut connection = self.connect(Intents::from_bits(intents)).await?;
        let (updates_tx, updates_rx) = mpsc::channel(128);
        let (errors_tx, errors_rx) = mpsc::channel(16);
        tokio::spawn(async move {
            while let Some(event) = connection.next_event().await {
                match event {
                    GatewayEvent::Dispatch(dispatch) => {
                        if updates_tx.send(dispatch).await.is_err() {
                            return;
                        }
                    }
                    GatewayEvent::Error(error) => {
                        let _ = errors_tx.send(error).await;
                    }
                    GatewayEvent::Disconnected {
                        close_code,
                        action: GatewayCloseAction::Fatal,
                    } => {
                        let _ = errors_tx
                            .send(Error::Other(format!(
                                "gateway closed fatally (close code {close_code:?})"
                            )))
                            .await;
                        return;
                    }
                    _ => {}
                }
            }
        });
        Ok((updates_rx, errors_rx))
    }
}

enum OutboundMessage {
    Payload(Value),
    MissedAck,
}

struct GatewayRunner {
    client: Client,
    intents: Intents,
    events: mpsc::Sender<GatewayEvent>,
    commands: mpsc::Receiver<GatewayCommand>,
    session: SessionState,
}

impl GatewayRunner {
    async fn run(mut self) {
        let mut backoff = Duration::from_secs(1);
        let mut resume = false;
        loop {
            let started = Instant::now();
            match self.run_connection(resume).await {
                Ok(ConnectionEnd::Shutdown) | Ok(ConnectionEnd::Fatal) => return,
                Ok(ConnectionEnd::Reconnect { resume: next_resume }) => {
                    resume = next_resume;
                    // A connection that lived for a while resets the backoff.
                    if started.elapsed() > Duration::from_secs(60) {
                        backoff = Duration::from_secs(1);
                    }
                }
                Err(error) => {
                    if self.events.send(GatewayEvent::Error(error)).await.is_err() {
                        return;
                    }
                    resume = true;
                }
            }
            tokio::time::sleep(backoff).await;
            backoff = (backoff * 2).min(Duration::from_secs(64));
        }
    }

    async fn gateway_url(&mut self, resume: bool) -> Result<String, Error> {
        let base = if resume {
            self.session.resume_gateway_url.clone()
        } else {
            None
        };
        let base = match base {
            Some(url) => url,
            None => {
                let info: GatewayBotInfo = self
                    .client
                    .request_json(reqwest::Method::GET, "/gateway/bot", Option::<&Value>::None)
                    .await?;
                info.url
            }
        };
        normalize_gateway_url(&base, &self.client.config().api_version)
    }

    async fn run_connection(&mut self, resume: bool) -> Result<ConnectionEnd, Error> {
        let can_resume = resume && self.session.session_id.is_some();
        let url = self.gateway_url(can_resume).await?;
        let (stream, _) = tokio_tungstenite::connect_async(url).await?;
        let (mut sink, mut stream) = stream.split();

        let (outbound_tx, mut outbound_rx) = mpsc::channel::<OutboundMessage>(64);
        let ack_received = Arc::new(AtomicBool::new(true));
        let last_seq = Arc::new(AtomicI64::new(self.session.seq.unwrap_or(i64::MIN)));
        let mut heartbeat_task: Option<tokio::task::JoinHandle<()>> = None;
        let mut close_code: Option<u16> = None;
        let token = self.client.config().token.clone();

        let end = loop {
            tokio::select! {
                incoming = stream.next() => {
                    let message = match incoming {
                        None => break self.close_end(close_code).await,
                        Some(Err(error)) => {
                            let _ = self.events.send(GatewayEvent::Error(error.into())).await;
                            break ConnectionEnd::Reconnect { resume: true };
                        }
                        Some(Ok(message)) => message,
                    };
                    match message {
                        WsMessage::Close(frame) => {
                            close_code = frame.map(|frame| u16::from(frame.code));
                        }
                        WsMessage::Text(text) => {
                            let payload: GatewayDispatch = match serde_json::from_str(&text) {
                                Ok(payload) => payload,
                                Err(error) => {
                                    let _ = self.events.send(GatewayEvent::Error(error.into())).await;
                                    continue;
                                }
                            };
                            if let Some(seq) = payload.s {
                                last_seq.store(seq, Ordering::SeqCst);
                                self.session.seq = Some(seq);
                            }
                            match payload.op {
                                10 => {
                                    let interval_ms = payload
                                        .d
                                        .get("heartbeat_interval")
                                        .and_then(Value::as_u64)
                                        .unwrap_or(41_250);
                                    if let Some(task) = heartbeat_task.take() {
                                        task.abort();
                                    }
                                    ack_received.store(true, Ordering::SeqCst);
                                    heartbeat_task = Some(tokio::spawn(heartbeat_loop(
                                        interval_ms,
                                        outbound_tx.clone(),
                                        Arc::clone(&ack_received),
                                        Arc::clone(&last_seq),
                                    )));
                                    let handshake = if can_resume {
                                        resume_payload(
                                            &token,
                                            self.session.session_id.as_deref().unwrap_or(""),
                                            self.session.seq.unwrap_or(0),
                                        )
                                    } else {
                                        identify_payload(&token, self.intents)
                                    };
                                    if let Err(error) = send_json(&mut sink, &handshake).await {
                                        let _ = self.events.send(GatewayEvent::Error(error)).await;
                                        break ConnectionEnd::Reconnect { resume: true };
                                    }
                                }
                                0 => {
                                    match payload.t.as_deref() {
                                        Some("READY") => {
                                            self.session.session_id = payload
                                                .d
                                                .get("session_id")
                                                .and_then(Value::as_str)
                                                .map(str::to_string);
                                            self.session.resume_gateway_url = payload
                                                .d
                                                .get("resume_gateway_url")
                                                .and_then(Value::as_str)
                                                .map(str::to_string);
                                            let _ = self
                                                .events
                                                .send(GatewayEvent::Connected { resumed: false })
                                                .await;
                                        }
                                        Some("RESUMED") => {
                                            let _ = self
                                                .events
                                                .send(GatewayEvent::Connected { resumed: true })
                                                .await;
                                        }
                                        _ => {}
                                    }
                                    if self
                                        .events
                                        .send(GatewayEvent::Dispatch(payload))
                                        .await
                                        .is_err()
                                    {
                                        break ConnectionEnd::Shutdown;
                                    }
                                }
                                1 => {
                                    let seq = self.session.seq;
                                    if let Err(error) =
                                        send_json(&mut sink, &heartbeat_payload(seq)).await
                                    {
                                        let _ = self.events.send(GatewayEvent::Error(error)).await;
                                        break ConnectionEnd::Reconnect { resume: true };
                                    }
                                }
                                7 => break ConnectionEnd::Reconnect { resume: true },
                                9 => {
                                    let resumable =
                                        payload.d.as_bool().unwrap_or(false);
                                    if !resumable {
                                        self.session.session_id = None;
                                        self.session.resume_gateway_url = None;
                                        self.session.seq = None;
                                    }
                                    // Discord asks clients to wait 1-5s before
                                    // re-authenticating after INVALID_SESSION.
                                    tokio::time::sleep(Duration::from_secs(2)).await;
                                    break ConnectionEnd::Reconnect { resume: resumable };
                                }
                                11 => {
                                    ack_received.store(true, Ordering::SeqCst);
                                }
                                _ => {}
                            }
                        }
                        _ => {}
                    }
                }
                outbound = outbound_rx.recv() => match outbound {
                    Some(OutboundMessage::Payload(payload)) => {
                        if let Err(error) = send_json(&mut sink, &payload).await {
                            let _ = self.events.send(GatewayEvent::Error(error)).await;
                            break ConnectionEnd::Reconnect { resume: true };
                        }
                    }
                    Some(OutboundMessage::MissedAck) => {
                        let _ = self.events.send(GatewayEvent::Error(Error::Other(
                            "heartbeat ACK missed; reconnecting with RESUME".to_string(),
                        ))).await;
                        break ConnectionEnd::Reconnect { resume: true };
                    }
                    None => break ConnectionEnd::Reconnect { resume: true },
                },
                command = self.commands.recv() => match command {
                    Some(GatewayCommand::Send(payload)) => {
                        if let Err(error) = send_json(&mut sink, &payload).await {
                            let _ = self.events.send(GatewayEvent::Error(error)).await;
                            break ConnectionEnd::Reconnect { resume: true };
                        }
                    }
                    Some(GatewayCommand::Shutdown) | None => {
                        let _ = sink.send(WsMessage::Close(None)).await;
                        break ConnectionEnd::Shutdown;
                    }
                },
            }
        };

        if let Some(task) = heartbeat_task.take() {
            task.abort();
        }
        Ok(end)
    }

    async fn close_end(&mut self, close_code: Option<u16>) -> ConnectionEnd {
        let action = classify_gateway_close_code(close_code);
        let _ = self
            .events
            .send(GatewayEvent::Disconnected { close_code, action })
            .await;
        match action {
            GatewayCloseAction::Fatal => ConnectionEnd::Fatal,
            GatewayCloseAction::Reidentify => {
                self.session = SessionState::default();
                ConnectionEnd::Reconnect { resume: false }
            }
            GatewayCloseAction::Resume => ConnectionEnd::Reconnect { resume: true },
        }
    }
}

async fn send_json<S>(sink: &mut S, payload: &Value) -> Result<(), Error>
where
    S: SinkExt<WsMessage> + Unpin,
    Error: From<S::Error>,
{
    sink.send(WsMessage::Text(payload.to_string())).await?;
    Ok(())
}

/// Independent heartbeat task: first beat after `interval * jitter`, then a
/// steady interval. Before each beat the previous ACK must have arrived;
/// otherwise the connection is considered zombied and a reconnect is forced.
async fn heartbeat_loop(
    interval_ms: u64,
    outbound: mpsc::Sender<OutboundMessage>,
    ack_received: Arc<AtomicBool>,
    last_seq: Arc<AtomicI64>,
) {
    let jitter_ms = (interval_ms as f64
        * (std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| (d.subsec_millis() % 1000) as f64 / 1000.0)
            .unwrap_or(0.37))) as u64;
    tokio::time::sleep(Duration::from_millis(jitter_ms)).await;
    let mut ticker = tokio::time::interval(Duration::from_millis(interval_ms.max(1)));
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    loop {
        if !ack_received.swap(false, Ordering::SeqCst) {
            let _ = outbound.send(OutboundMessage::MissedAck).await;
            return;
        }
        let seq = match last_seq.load(Ordering::SeqCst) {
            i64::MIN => None,
            seq => Some(seq),
        };
        if outbound
            .send(OutboundMessage::Payload(heartbeat_payload(seq)))
            .await
            .is_err()
        {
            return;
        }
        ticker.tick().await;
    }
}

fn normalize_gateway_url(base: &str, version: &str) -> Result<String, Error> {
    let mut parsed = reqwest::Url::parse(base).map_err(|error| Error::Other(error.to_string()))?;
    if !parsed.scheme().starts_with("ws") {
        parsed
            .set_scheme("wss")
            .map_err(|()| Error::Other("failed to set websocket scheme".to_string()))?;
    }
    parsed.query_pairs_mut().append_pair("v", version);
    parsed.query_pairs_mut().append_pair("encoding", "json");
    Ok(parsed.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn intents_compose_with_bitor() {
        let intents = Intents::GUILDS | Intents::GUILD_MESSAGES | Intents::MESSAGE_CONTENT;
        assert_eq!(intents.bits(), 1 | (1 << 9) | (1 << 15));
        assert!(intents.contains(Intents::GUILDS));
        assert!(!intents.contains(Intents::GUILD_MEMBERS));
        assert!(Intents::none().is_empty());
    }

    #[test]
    fn unprivileged_excludes_privileged_intents() {
        let intents = Intents::unprivileged();
        assert!(!intents.contains(Intents::GUILD_MEMBERS));
        assert!(!intents.contains(Intents::GUILD_PRESENCES));
        assert!(!intents.contains(Intents::MESSAGE_CONTENT));
        assert!(intents.contains(Intents::GUILDS));
        assert!(Intents::all().contains(Intents::MESSAGE_CONTENT));
    }

    #[test]
    fn close_code_policy_matches_discord_docs() {
        use GatewayCloseAction::*;
        assert_eq!(classify_gateway_close_code(Some(4004)), Fatal);
        assert_eq!(classify_gateway_close_code(Some(4010)), Fatal);
        assert_eq!(classify_gateway_close_code(Some(4011)), Fatal);
        assert_eq!(classify_gateway_close_code(Some(4012)), Fatal);
        assert_eq!(classify_gateway_close_code(Some(4013)), Fatal);
        assert_eq!(classify_gateway_close_code(Some(4014)), Fatal);
        assert_eq!(classify_gateway_close_code(Some(4007)), Reidentify);
        assert_eq!(classify_gateway_close_code(Some(4009)), Reidentify);
        assert_eq!(classify_gateway_close_code(Some(1000)), Reidentify);
        assert_eq!(classify_gateway_close_code(Some(1001)), Reidentify);
        assert_eq!(classify_gateway_close_code(Some(4000)), Resume);
        assert_eq!(classify_gateway_close_code(Some(4008)), Resume);
        assert_eq!(classify_gateway_close_code(Some(1006)), Resume);
        assert_eq!(classify_gateway_close_code(None), Resume);
    }

    #[test]
    fn identify_payload_shape() {
        let payload = identify_payload("token", Intents::GUILDS | Intents::GUILD_MESSAGES);
        assert_eq!(payload["op"], 2);
        assert_eq!(payload["d"]["token"], "token");
        assert_eq!(payload["d"]["intents"], 513);
        assert_eq!(payload["d"]["properties"]["browser"], "vaidcord-rust");
    }

    #[test]
    fn resume_payload_shape() {
        let payload = resume_payload("token", "session", 42);
        assert_eq!(payload["op"], 6);
        assert_eq!(payload["d"]["session_id"], "session");
        assert_eq!(payload["d"]["seq"], 42);
    }

    #[test]
    fn heartbeat_payload_uses_null_before_first_sequence() {
        assert_eq!(heartbeat_payload(None)["d"], Value::Null);
        assert_eq!(heartbeat_payload(Some(7))["d"], 7);
    }

    #[test]
    fn presence_payload_shape() {
        let payload = presence_update_payload(&PresenceUpdate::playing("with fire"));
        assert_eq!(payload["op"], 3);
        assert_eq!(payload["d"]["status"], "online");
        assert_eq!(payload["d"]["activities"][0]["name"], "with fire");
        assert_eq!(payload["d"]["afk"], false);
    }

    #[test]
    fn request_guild_members_payload_query_vs_user_ids() {
        let by_query = request_guild_members_payload(&GuildMembersRequest {
            guild_id: "1".into(),
            query: "vai".into(),
            limit: 10,
            ..Default::default()
        });
        assert_eq!(by_query["op"], 8);
        assert_eq!(by_query["d"]["query"], "vai");
        assert!(by_query["d"].get("user_ids").is_none());

        let by_ids = request_guild_members_payload(&GuildMembersRequest {
            guild_id: "1".into(),
            user_ids: Some(vec!["7".into()]),
            nonce: Some("n".into()),
            ..Default::default()
        });
        assert_eq!(by_ids["d"]["user_ids"][0], "7");
        assert_eq!(by_ids["d"]["nonce"], "n");
        assert!(by_ids["d"].get("query").is_none());
    }

    #[test]
    fn gateway_url_is_normalized() {
        let url = normalize_gateway_url("wss://gateway.discord.gg", "10").unwrap();
        assert!(url.starts_with("wss://gateway.discord.gg"));
        assert!(url.contains("v=10"));
        assert!(url.contains("encoding=json"));
    }
}
