//! The gateway `READY` event model.

use serde::Deserialize;
use serde_json::Value;

use super::User;

/// Payload of the gateway `READY` dispatch.
///
/// Carries the session information needed for RESUME (`session_id`,
/// `resume_gateway_url`) alongside the bot user.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct Ready {
    #[serde(default)]
    pub v: Option<u8>,
    pub user: User,
    pub session_id: String,
    #[serde(default)]
    pub resume_gateway_url: Option<String>,
    #[serde(default)]
    pub guilds: Vec<Value>,
    #[serde(default)]
    pub shard: Option<Vec<u32>>,
    #[serde(default)]
    pub application: Option<Value>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ready_decodes_resume_fields() {
        let ready: Ready = serde_json::from_str(
            r#"{
                "v": 10,
                "user": {"id": "42", "username": "bot"},
                "session_id": "abc",
                "resume_gateway_url": "wss://gateway-us-east1-b.discord.gg",
                "guilds": [{"id": "1", "unavailable": true}]
            }"#,
        )
        .unwrap();
        assert_eq!(ready.session_id, "abc");
        assert_eq!(
            ready.resume_gateway_url.as_deref(),
            Some("wss://gateway-us-east1-b.discord.gg")
        );
        assert_eq!(ready.guilds.len(), 1);
    }
}
