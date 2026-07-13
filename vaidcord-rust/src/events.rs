//! Typed gateway events dispatched through routers and middleware.

use serde_json::Value;

use crate::models::{DeletedMessage, Guild, Interaction, Message, Ready};

/// Discriminant of an [`Event`], used for route matching.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[non_exhaustive]
pub enum EventKind {
    Ready,
    MessageCreate,
    MessageUpdate,
    MessageDelete,
    GuildCreate,
    InteractionCreate,
    /// Any dispatch the SDK has no typed model for (or that failed to parse
    /// into its typed model). The raw payload is preserved.
    Unknown,
}

/// A parsed gateway dispatch event.
///
/// Typed variants expose parsed models; anything else is carried as
/// [`Event::Unknown`] with the raw JSON payload (typed events first, raw
/// payload second — see UNITED.md §7).
#[derive(Debug, Clone)]
#[non_exhaustive]
pub enum Event {
    Ready(Ready),
    MessageCreate(Message),
    MessageUpdate(Message),
    MessageDelete(DeletedMessage),
    GuildCreate(Box<Guild>),
    InteractionCreate(Box<Interaction>),
    Unknown { name: String, data: Value },
}

impl Event {
    /// Parse a gateway dispatch (`t` + `d`) into a typed event.
    ///
    /// Unknown event names — or known names whose payloads fail to decode —
    /// fall back to [`Event::Unknown`] so no dispatch is ever lost.
    pub fn parse(name: &str, data: Value) -> Event {
        macro_rules! parse_or_raw {
            ($variant:ident) => {
                parse_or_raw!($variant, |parsed| parsed)
            };
            ($variant:ident, $wrap:expr) => {
                match serde_json::from_value(data.clone()) {
                    Ok(parsed) => Event::$variant(($wrap)(parsed)),
                    Err(_) => Event::Unknown {
                        name: name.to_string(),
                        data,
                    },
                }
            };
        }
        match name {
            "READY" => parse_or_raw!(Ready),
            "MESSAGE_CREATE" => parse_or_raw!(MessageCreate),
            "MESSAGE_UPDATE" => parse_or_raw!(MessageUpdate),
            "MESSAGE_DELETE" => parse_or_raw!(MessageDelete),
            "GUILD_CREATE" => parse_or_raw!(GuildCreate, Box::new),
            "INTERACTION_CREATE" => parse_or_raw!(InteractionCreate, Box::new),
            _ => Event::Unknown {
                name: name.to_string(),
                data,
            },
        }
    }

    /// The event's route-matching kind.
    pub fn kind(&self) -> EventKind {
        match self {
            Event::Ready(_) => EventKind::Ready,
            Event::MessageCreate(_) => EventKind::MessageCreate,
            Event::MessageUpdate(_) => EventKind::MessageUpdate,
            Event::MessageDelete(_) => EventKind::MessageDelete,
            Event::GuildCreate(_) => EventKind::GuildCreate,
            Event::InteractionCreate(_) => EventKind::InteractionCreate,
            Event::Unknown { .. } => EventKind::Unknown,
        }
    }

    /// The contained message for message-shaped events.
    pub fn message(&self) -> Option<&Message> {
        match self {
            Event::MessageCreate(message) | Event::MessageUpdate(message) => Some(message),
            _ => None,
        }
    }

    /// The contained interaction, if any.
    pub fn interaction(&self) -> Option<&Interaction> {
        match self {
            Event::InteractionCreate(interaction) => Some(interaction),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parses_message_create() {
        let event = Event::parse(
            "MESSAGE_CREATE",
            json!({"id":"1","channel_id":"2","author":{"id":"3","username":"u"},"content":"hi"}),
        );
        assert_eq!(event.kind(), EventKind::MessageCreate);
        assert_eq!(event.message().unwrap().content, "hi");
    }

    #[test]
    fn unknown_event_keeps_raw_payload() {
        let event = Event::parse("TYPING_START", json!({"channel_id": "1"}));
        assert_eq!(event.kind(), EventKind::Unknown);
        match event {
            Event::Unknown { name, data } => {
                assert_eq!(name, "TYPING_START");
                assert_eq!(data["channel_id"], "1");
            }
            _ => panic!("expected raw event"),
        }
    }

    #[test]
    fn undecodable_known_event_falls_back_to_unknown() {
        // MESSAGE_UPDATE partials can lack author/content; those must not be dropped.
        let event = Event::parse("MESSAGE_UPDATE", json!({"id": "1", "channel_id": "2"}));
        assert_eq!(event.kind(), EventKind::Unknown);
    }
}
