//! Typed message embeds with a fluent builder.

use serde::{Deserialize, Serialize};

/// A rich message embed.
///
/// Build one fluently:
///
/// ```
/// use vaidcord::models::Embed;
///
/// let embed = Embed::new()
///     .title("Status")
///     .description("All systems nominal")
///     .color(0x57F287)
///     .field("Uptime", "42 days", true);
/// assert_eq!(embed.fields.len(), 1);
/// ```
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct Embed {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    #[serde(default, rename = "type", skip_serializing_if = "Option::is_none")]
    pub kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub timestamp: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub color: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub footer: Option<EmbedFooter>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub image: Option<EmbedMedia>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub thumbnail: Option<EmbedMedia>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub video: Option<EmbedMedia>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider: Option<EmbedProvider>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub author: Option<EmbedAuthor>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub fields: Vec<EmbedField>,
}

/// Footer of an [`Embed`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct EmbedFooter {
    pub text: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub icon_url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub proxy_icon_url: Option<String>,
}

/// Image/thumbnail/video media object of an [`Embed`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct EmbedMedia {
    pub url: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub proxy_url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub height: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub width: Option<u32>,
}

/// Provider block of an [`Embed`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct EmbedProvider {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
}

/// Author block of an [`Embed`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct EmbedAuthor {
    pub name: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub icon_url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub proxy_icon_url: Option<String>,
}

/// A single name/value field of an [`Embed`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct EmbedField {
    pub name: String,
    pub value: String,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub inline: bool,
}

impl Embed {
    /// Create an empty embed.
    pub fn new() -> Self {
        Self::default()
    }

    /// Set the embed title.
    pub fn title(mut self, title: impl Into<String>) -> Self {
        self.title = Some(title.into());
        self
    }

    /// Set the embed description.
    pub fn description(mut self, description: impl Into<String>) -> Self {
        self.description = Some(description.into());
        self
    }

    /// Set the embed URL.
    pub fn url(mut self, url: impl Into<String>) -> Self {
        self.url = Some(url.into());
        self
    }

    /// Set the accent color (`0xRRGGBB`).
    pub fn color(mut self, color: u32) -> Self {
        self.color = Some(color);
        self
    }

    /// Set the ISO8601 timestamp.
    pub fn timestamp(mut self, timestamp: impl Into<String>) -> Self {
        self.timestamp = Some(timestamp.into());
        self
    }

    /// Append a name/value field.
    pub fn field(mut self, name: impl Into<String>, value: impl Into<String>, inline: bool) -> Self {
        self.fields.push(EmbedField {
            name: name.into(),
            value: value.into(),
            inline,
        });
        self
    }

    /// Set the footer text.
    pub fn footer(mut self, text: impl Into<String>) -> Self {
        self.footer = Some(EmbedFooter {
            text: text.into(),
            icon_url: None,
            proxy_icon_url: None,
        });
        self
    }

    /// Set the large image.
    pub fn image(mut self, url: impl Into<String>) -> Self {
        self.image = Some(EmbedMedia {
            url: url.into(),
            proxy_url: None,
            height: None,
            width: None,
        });
        self
    }

    /// Set the thumbnail image.
    pub fn thumbnail(mut self, url: impl Into<String>) -> Self {
        self.thumbnail = Some(EmbedMedia {
            url: url.into(),
            proxy_url: None,
            height: None,
            width: None,
        });
        self
    }

    /// Set the author line.
    pub fn author(mut self, name: impl Into<String>) -> Self {
        self.author = Some(EmbedAuthor {
            name: name.into(),
            url: None,
            icon_url: None,
            proxy_icon_url: None,
        });
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embed_builder_serializes_compactly() {
        let embed = Embed::new().title("t").color(0xFF0000).field("a", "b", true);
        let json = serde_json::to_value(&embed).unwrap();
        assert_eq!(json["title"], "t");
        assert_eq!(json["color"], 0xFF0000);
        assert_eq!(json["fields"][0]["inline"], true);
        assert!(json.get("description").is_none());
        assert!(json.get("footer").is_none());
    }

    #[test]
    fn embed_roundtrips_and_ignores_unknown_fields() {
        let embed: Embed = serde_json::from_str(
            r#"{"title":"x","fields":[{"name":"n","value":"v"}],"unknown_thing":1}"#,
        )
        .unwrap();
        assert_eq!(embed.title.as_deref(), Some("x"));
        assert!(!embed.fields[0].inline);
    }
}
