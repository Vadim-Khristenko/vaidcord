//! Interaction (slash command / component) models and response payloads.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::guild::Member;
use super::user::User;

/// Interaction types (`InteractionCreate.kind`).
pub mod interaction_type {
    pub const PING: u8 = 1;
    pub const APPLICATION_COMMAND: u8 = 2;
    pub const MESSAGE_COMPONENT: u8 = 3;
    pub const APPLICATION_COMMAND_AUTOCOMPLETE: u8 = 4;
    pub const MODAL_SUBMIT: u8 = 5;
}

/// Interaction response callback types.
pub mod interaction_callback_type {
    pub const PONG: u8 = 1;
    pub const CHANNEL_MESSAGE_WITH_SOURCE: u8 = 4;
    pub const DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE: u8 = 5;
    pub const DEFERRED_UPDATE_MESSAGE: u8 = 6;
    pub const UPDATE_MESSAGE: u8 = 7;
    pub const APPLICATION_COMMAND_AUTOCOMPLETE_RESULT: u8 = 8;
    pub const MODAL: u8 = 9;
}

/// An incoming interaction (`INTERACTION_CREATE`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Interaction {
    pub id: String,
    pub application_id: String,
    #[serde(rename = "type")]
    pub kind: u8,
    #[serde(default)]
    pub data: Option<InteractionData>,
    #[serde(default)]
    pub guild_id: Option<String>,
    #[serde(default)]
    pub channel_id: Option<String>,
    #[serde(default)]
    pub member: Option<Member>,
    #[serde(default)]
    pub user: Option<User>,
    pub token: String,
    #[serde(default)]
    pub version: Option<u8>,
    #[serde(default)]
    pub message: Option<Value>,
    #[serde(default)]
    pub locale: Option<String>,
    #[serde(default)]
    pub guild_locale: Option<String>,
    #[serde(default)]
    pub app_permissions: Option<String>,
}

impl Interaction {
    /// The user that triggered this interaction (member user in guilds,
    /// top-level user in DMs).
    pub fn invoker(&self) -> Option<&User> {
        self.member
            .as_ref()
            .and_then(|member| member.user.as_ref())
            .or(self.user.as_ref())
    }

    /// Name of the invoked application command, if any.
    pub fn command_name(&self) -> Option<&str> {
        self.data.as_ref().and_then(|data| data.name.as_deref())
    }
}

/// Data payload of an [`Interaction`].
#[derive(Debug, Clone, PartialEq, Deserialize, Default)]
pub struct InteractionData {
    #[serde(default)]
    pub id: Option<String>,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default, rename = "type")]
    pub kind: Option<u8>,
    #[serde(default)]
    pub options: Vec<Value>,
    #[serde(default)]
    pub custom_id: Option<String>,
    #[serde(default)]
    pub component_type: Option<u8>,
    #[serde(default)]
    pub values: Vec<Value>,
    #[serde(default)]
    pub resolved: Option<Value>,
    #[serde(default)]
    pub target_id: Option<String>,
}

/// Outbound interaction response (`POST /interactions/{id}/{token}/callback`).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct InteractionResponse {
    #[serde(rename = "type")]
    pub kind: u8,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

impl InteractionResponse {
    /// Respond immediately with a text message (callback type 4).
    pub fn message(content: impl Into<String>) -> Self {
        Self {
            kind: interaction_callback_type::CHANNEL_MESSAGE_WITH_SOURCE,
            data: Some(serde_json::json!({ "content": content.into() })),
        }
    }

    /// Acknowledge now, respond later (callback type 5).
    pub fn deferred() -> Self {
        Self {
            kind: interaction_callback_type::DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
            data: None,
        }
    }

    /// Respond to a gateway PING (callback type 1).
    pub fn pong() -> Self {
        Self {
            kind: interaction_callback_type::PONG,
            data: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn interaction_decodes_slash_command() {
        let interaction: Interaction = serde_json::from_str(
            r#"{
                "id": "1", "application_id": "2", "type": 2, "token": "tok",
                "guild_id": "3",
                "data": {"id": "10", "name": "ping", "type": 1},
                "member": {"user": {"id": "42", "username": "vai"}},
                "extra_future_field": true
            }"#,
        )
        .unwrap();
        assert_eq!(interaction.kind, interaction_type::APPLICATION_COMMAND);
        assert_eq!(interaction.command_name(), Some("ping"));
        assert_eq!(interaction.invoker().unwrap().id, "42");
    }

    #[test]
    fn interaction_response_serializes_type_field() {
        let response = serde_json::to_value(InteractionResponse::message("hi")).unwrap();
        assert_eq!(response["type"], 4);
        assert_eq!(response["data"]["content"], "hi");
        let deferred = serde_json::to_value(InteractionResponse::deferred()).unwrap();
        assert_eq!(deferred["type"], 5);
        assert!(deferred.get("data").is_none());
    }
}
