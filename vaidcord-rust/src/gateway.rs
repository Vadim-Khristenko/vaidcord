use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::sync::mpsc;
use tokio::time::{Duration, Instant};

use crate::client::Client;
use crate::error::Error;

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

#[derive(Debug, Clone, Deserialize)]
struct GatewayBotInfo {
    url: String,
}

#[derive(Debug, Serialize)]
struct IdentifyProperties {
    os: &'static str,
    browser: &'static str,
    device: &'static str,
}

#[derive(Debug, Serialize)]
struct IdentifyData {
    token: String,
    intents: u64,
    properties: IdentifyProperties,
}

#[derive(Debug, Serialize)]
struct GatewayPayload<T> {
    op: i64,
    d: T,
}

pub struct GatewayClient {
    client: Client,
}

impl GatewayClient {
    pub fn new(client: Client) -> Self {
        Self { client }
    }

    pub async fn stream_updates(
        &self,
        intents: u64,
    ) -> Result<(mpsc::Receiver<GatewayDispatch>, mpsc::Receiver<Error>), Error> {
        let info: GatewayBotInfo = self
            .client
            .request_json(reqwest::Method::GET, "/gateway/bot", Option::<&Value>::None)
            .await?;
        let ws_url = normalize_gateway_url(&info.url, &self.client.config().api_version)?;

        let (mut stream, _) = tokio_tungstenite::connect_async(ws_url)
            .await
            .map_err(Error::from)?;
        let (updates_tx, updates_rx) = mpsc::channel(128);
        let (errors_tx, errors_rx) = mpsc::channel(16);
        let token = self.client.config().token.clone();

        tokio::spawn(async move {
            let mut last_sequence: Option<i64> = None;
            let mut next_heartbeat: Option<(Duration, Instant)> = None;

            while let Some(message) = stream.next().await {
                let message = match message {
                    Ok(message) => message,
                    Err(error) => {
                        let _ = errors_tx.send(Error::from(error)).await;
                        return;
                    }
                };
                let text = match message.into_text() {
                    Ok(text) => text,
                    Err(_) => continue,
                };
                let payload: GatewayDispatch = match serde_json::from_str(&text) {
                    Ok(payload) => payload,
                    Err(error) => {
                        let _ = errors_tx.send(Error::Decode(error)).await;
                        return;
                    }
                };
                if let Some(seq) = payload.s {
                    last_sequence = Some(seq);
                }

                match payload.op {
                    10 => {
                        let heartbeat_interval = payload
                            .d
                            .get("heartbeat_interval")
                            .and_then(|value| value.as_u64())
                            .unwrap_or(41250);
                        next_heartbeat =
                            Some((Duration::from_millis(heartbeat_interval), Instant::now()));
                        let identify = GatewayPayload {
                            op: 2,
                            d: IdentifyData {
                                token: token.clone(),
                                intents,
                                properties: IdentifyProperties {
                                    os: "linux",
                                    browser: "vaidcord-rust",
                                    device: "vaidcord-rust",
                                },
                            },
                        };
                        if let Err(error) = stream
                            .send(tokio_tungstenite::tungstenite::Message::Text(
                                serde_json::to_string(&identify).unwrap_or_default(),
                            ))
                            .await
                        {
                            let _ = errors_tx.send(Error::from(error)).await;
                            return;
                        }
                    }
                    0 => {
                        if updates_tx.send(payload).await.is_err() {
                            return;
                        }
                    }
                    _ => {}
                }

                if let Some((interval, mut at)) = next_heartbeat
                    && at.elapsed() >= interval
                {
                    at = Instant::now();
                    next_heartbeat = Some((interval, at));
                    let heartbeat = GatewayPayload {
                        op: 1,
                        d: last_sequence,
                    };
                    if let Err(error) = stream
                        .send(tokio_tungstenite::tungstenite::Message::Text(
                            serde_json::to_string(&heartbeat).unwrap_or_default(),
                        ))
                        .await
                    {
                        let _ = errors_tx.send(Error::from(error)).await;
                        return;
                    }
                }
            }
        });

        Ok((updates_rx, errors_rx))
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
