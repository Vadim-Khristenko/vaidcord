//! Guild, role and member models.

use serde::Deserialize;
use serde_json::Value;

use super::User;

/// A Discord guild ("server").
///
/// Unknown fields in the payload are ignored so the model stays tolerant of
/// API additions.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Default)]
pub struct Guild {
    pub id: String,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub icon: Option<String>,
    #[serde(default)]
    pub owner_id: Option<String>,
    #[serde(default)]
    pub afk_channel_id: Option<String>,
    #[serde(default)]
    pub afk_timeout: Option<u64>,
    #[serde(default)]
    pub verification_level: Option<u8>,
    #[serde(default)]
    pub roles: Vec<Role>,
    #[serde(default)]
    pub emojis: Vec<Value>,
    #[serde(default)]
    pub features: Vec<String>,
    #[serde(default)]
    pub member_count: Option<u64>,
    #[serde(default)]
    pub members: Vec<Member>,
    #[serde(default)]
    pub channels: Vec<Value>,
    #[serde(default)]
    pub threads: Vec<Value>,
    #[serde(default)]
    pub joined_at: Option<String>,
    #[serde(default)]
    pub large: Option<bool>,
    #[serde(default)]
    pub unavailable: Option<bool>,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub preferred_locale: Option<String>,
    #[serde(default)]
    pub system_channel_id: Option<String>,
    #[serde(default)]
    pub rules_channel_id: Option<String>,
    #[serde(default)]
    pub premium_tier: Option<u8>,
    #[serde(default)]
    pub nsfw_level: Option<u8>,
}

/// A guild role.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Default)]
pub struct Role {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub color: Option<u32>,
    #[serde(default)]
    pub hoist: bool,
    #[serde(default)]
    pub icon: Option<String>,
    #[serde(default)]
    pub unicode_emoji: Option<String>,
    #[serde(default)]
    pub position: Option<i64>,
    #[serde(default)]
    pub permissions: Option<String>,
    #[serde(default)]
    pub managed: bool,
    #[serde(default)]
    pub mentionable: bool,
    #[serde(default)]
    pub flags: Option<u64>,
}

/// A guild member.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Default)]
pub struct Member {
    #[serde(default)]
    pub user: Option<User>,
    #[serde(default)]
    pub nick: Option<String>,
    #[serde(default)]
    pub avatar: Option<String>,
    #[serde(default)]
    pub roles: Vec<String>,
    #[serde(default)]
    pub joined_at: Option<String>,
    #[serde(default)]
    pub premium_since: Option<String>,
    #[serde(default)]
    pub deaf: bool,
    #[serde(default)]
    pub mute: bool,
    #[serde(default)]
    pub pending: Option<bool>,
    #[serde(default)]
    pub permissions: Option<String>,
    #[serde(default)]
    pub communication_disabled_until: Option<String>,
    #[serde(default)]
    pub flags: Option<u64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn guild_decodes_with_unknown_fields() {
        let guild: Guild = serde_json::from_str(
            r#"{"id":"1","name":"Test","owner_id":"42","roles":[{"id":"9","name":"admin","permissions":"8"}],"some_future_field":{"x":1}}"#,
        )
        .unwrap();
        assert_eq!(guild.id, "1");
        assert_eq!(guild.name.as_deref(), Some("Test"));
        assert_eq!(guild.roles.len(), 1);
        assert_eq!(guild.roles[0].permissions.as_deref(), Some("8"));
    }

    #[test]
    fn member_decodes_with_partial_payload() {
        let member: Member =
            serde_json::from_str(r#"{"roles":["1","2"],"nick":"vai","mute":true}"#).unwrap();
        assert_eq!(member.roles.len(), 2);
        assert!(member.mute);
        assert!(member.user.is_none());
    }
}
