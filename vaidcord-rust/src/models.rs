use serde::Serialize;
use serde_json::Value;

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
}
