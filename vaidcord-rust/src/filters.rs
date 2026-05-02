use crate::error::Error;
use crate::extract::{Args, Command, ExtractBag};
use crate::models::Message;

#[derive(Clone, Default)]
pub enum FilterOutcome {
    Pass(ExtractBag),
    #[default]
    Reject,
}

pub type MessageFilter =
    Box<dyn Fn(&Message, &ExtractBag) -> Result<FilterOutcome, Error> + Send + Sync>;

pub fn command(name: impl Into<String>) -> MessageFilter {
    command_with_prefixes(name, &["/", "!", "."])
}

pub fn command_with_prefixes(name: impl Into<String>, prefixes: &[&str]) -> MessageFilter {
    let command_name = name.into().trim().to_ascii_lowercase();
    let prefixes = normalize_prefixes(prefixes);
    Box::new(move |message: &Message, _bag: &ExtractBag| {
        let text = message.content.trim();
        if text.is_empty() {
            return Ok(FilterOutcome::Reject);
        }
        let token = text.split_once(' ').map_or(text, |(head, _)| head);
        let Some(matched_prefix) = prefixes
            .iter()
            .find(|prefix| token.starts_with(prefix.as_str()))
        else {
            return Ok(FilterOutcome::Reject);
        };
        let mut name_part = &token[matched_prefix.len()..];
        if let Some((before, _)) = name_part.split_once('@') {
            name_part = before;
        }
        if !name_part.eq_ignore_ascii_case(&command_name) {
            return Ok(FilterOutcome::Reject);
        }

        let raw = text
            .split_once(char::is_whitespace)
            .map_or_else(String::new, |(_, tail)| tail.trim_start().to_string());
        let mut bag = ExtractBag::new();
        bag.insert(Command {
            name: command_name.clone(),
        });
        bag.insert(Args { raw });
        Ok(FilterOutcome::Pass(bag))
    })
}

pub fn command_start() -> MessageFilter {
    command("start")
}

pub fn command_start_with_prefixes(prefixes: &[&str]) -> MessageFilter {
    command_with_prefixes("start", prefixes)
}

pub fn command_help() -> MessageFilter {
    command("help")
}

pub fn command_help_with_prefixes(prefixes: &[&str]) -> MessageFilter {
    command_with_prefixes("help", prefixes)
}

pub fn command_settings() -> MessageFilter {
    command("settings")
}

pub fn command_settings_with_prefixes(prefixes: &[&str]) -> MessageFilter {
    command_with_prefixes("settings", prefixes)
}

pub fn content_starts_with(prefix: impl Into<String>) -> MessageFilter {
    let prefix = prefix.into();
    Box::new(move |message: &Message, _bag: &ExtractBag| {
        if message.content.starts_with(&prefix) {
            Ok(FilterOutcome::Pass(ExtractBag::new()))
        } else {
            Ok(FilterOutcome::Reject)
        }
    })
}

pub fn author_id(user_id: impl Into<String>) -> MessageFilter {
    let user_id = user_id.into();
    Box::new(move |message: &Message, _bag: &ExtractBag| {
        if message.author.id == user_id {
            Ok(FilterOutcome::Pass(ExtractBag::new()))
        } else {
            Ok(FilterOutcome::Reject)
        }
    })
}

pub fn and(left: MessageFilter, right: MessageFilter) -> MessageFilter {
    Box::new(
        move |message: &Message, bag: &ExtractBag| match left(message, bag)? {
            FilterOutcome::Reject => Ok(FilterOutcome::Reject),
            FilterOutcome::Pass(left_bag) => {
                let mut merged = bag.clone();
                merged.merge(left_bag.clone());
                match right(message, &merged)? {
                    FilterOutcome::Reject => Ok(FilterOutcome::Reject),
                    FilterOutcome::Pass(right_bag) => {
                        let mut out = left_bag;
                        out.merge(right_bag);
                        Ok(FilterOutcome::Pass(out))
                    }
                }
            }
        },
    )
}

pub fn or(left: MessageFilter, right: MessageFilter) -> MessageFilter {
    Box::new(
        move |message: &Message, bag: &ExtractBag| match left(message, bag)? {
            FilterOutcome::Pass(left_bag) => Ok(FilterOutcome::Pass(left_bag)),
            FilterOutcome::Reject => right(message, bag),
        },
    )
}

pub fn not(filter: MessageFilter) -> MessageFilter {
    Box::new(
        move |message: &Message, bag: &ExtractBag| match filter(message, bag)? {
            FilterOutcome::Pass(_) => Ok(FilterOutcome::Reject),
            FilterOutcome::Reject => Ok(FilterOutcome::Pass(ExtractBag::new())),
        },
    )
}

#[macro_export]
macro_rules! command {
    ($name:literal) => {
        $crate::command($name)
    };
    ($name:literal, [$($prefix:literal),+ $(,)?]) => {
        $crate::command_with_prefixes($name, &[$($prefix),+])
    };
}

fn normalize_prefixes(prefixes: &[&str]) -> Vec<String> {
    if prefixes.is_empty() {
        return vec!["/".to_string(), "!".to_string(), ".".to_string()];
    }
    let filtered: Vec<String> = prefixes
        .iter()
        .filter_map(|prefix| {
            let trimmed = prefix.trim();
            if trimmed.is_empty() {
                None
            } else {
                Some(trimmed.to_string())
            }
        })
        .collect();
    if filtered.is_empty() {
        vec!["/".to_string(), "!".to_string(), ".".to_string()]
    } else {
        filtered
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::User;

    fn message(content: &str) -> Message {
        Message {
            id: "1".to_string(),
            channel_id: "2".to_string(),
            guild_id: None,
            author: User {
                id: "42".to_string(),
                username: "tester".to_string(),
                discriminator: None,
                global_name: None,
                bot: false,
                system: false,
                avatar: None,
                banner: None,
                public_flags: None,
            },
            content: content.to_string(),
            timestamp: None,
            edited_timestamp: None,
            tts: false,
            mention_everyone: false,
            mentions: Vec::new(),
            embeds: Vec::new(),
            attachments: Vec::new(),
            components: Vec::new(),
            flags: None,
        }
    }

    #[test]
    fn command_filter_matches_python_style_prefixes() {
        let filter = command("start");
        let bag = ExtractBag::new();

        assert!(matches!(
            filter(&message("/start"), &bag).unwrap(),
            FilterOutcome::Pass(_)
        ));
        assert!(matches!(
            filter(&message("!start payload"), &bag).unwrap(),
            FilterOutcome::Pass(_)
        ));
        assert!(matches!(
            filter(&message(".StArT@mybot now"), &bag).unwrap(),
            FilterOutcome::Pass(_)
        ));
        assert!(matches!(
            filter(&message("/other"), &bag).unwrap(),
            FilterOutcome::Reject
        ));
        let custom = command_with_prefixes("start", &["#"]);
        assert!(matches!(
            custom(&message("#start"), &bag).unwrap(),
            FilterOutcome::Pass(_)
        ));
        assert!(matches!(
            custom(&message("/start"), &bag).unwrap(),
            FilterOutcome::Reject
        ));
    }
}
