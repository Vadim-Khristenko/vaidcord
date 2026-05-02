use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::User;

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct Message {
    pub id: String,
    pub channel_id: String,
    #[serde(default)]
    pub guild_id: Option<String>,
    pub author: User,
    pub content: String,
    #[serde(default)]
    pub timestamp: Option<String>,
    #[serde(default)]
    pub edited_timestamp: Option<String>,
    #[serde(default)]
    pub tts: bool,
    #[serde(default)]
    pub mention_everyone: bool,
    #[serde(default)]
    pub mentions: Vec<User>,
    #[serde(default)]
    pub embeds: Vec<Value>,
    #[serde(default)]
    pub attachments: Vec<Value>,
    #[serde(default)]
    pub components: Vec<Value>,
    #[serde(default)]
    pub flags: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct EditedMessage {
    #[serde(flatten)]
    pub message: Message,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct DeletedMessage {
    pub id: String,
    pub channel_id: String,
    #[serde(default)]
    pub guild_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct BulkDeletedMessages {
    pub ids: Vec<String>,
    pub channel_id: String,
    #[serde(default)]
    pub guild_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct MessagePayload {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub tts: bool,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub embeds: Vec<Value>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub components: Vec<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub allowed_mentions: Option<Value>,
}

impl MessagePayload {
    pub fn text(content: impl Into<String>) -> Self {
        Self {
            content: Some(content.into()),
            tts: false,
            embeds: Vec::new(),
            components: Vec::new(),
            allowed_mentions: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn message_payload_omits_empty_fields() {
        let payload = serde_json::to_value(MessagePayload::text("hello")).unwrap();

        assert_eq!(payload["content"], "hello");
        assert!(payload.get("embeds").is_none());
        assert!(payload.get("components").is_none());
    }

    #[test]
    fn decodes_typed_message() {
        let message: Message = serde_json::from_str(
            r#"{"id":"900","channel_id":"123","author":{"id":"42","username":"vaidcord"},"content":"pong"}"#,
        )
        .unwrap();

        assert_eq!(message.id, "900");
        assert_eq!(message.author.username, "vaidcord");
        assert_eq!(message.content, "pong");
    }
}
