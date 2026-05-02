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
    let name = name.into();
    Box::new(move |message: &Message, _bag: &ExtractBag| {
        let prefix = format!("!{name}");
        if message.content == prefix || message.content.starts_with(&(prefix.clone() + " ")) {
            let raw = message.content[prefix.len()..].trim_start().to_string();
            let mut bag = ExtractBag::new();
            bag.insert(Command { name: name.clone() });
            bag.insert(Args { raw });
            Ok(FilterOutcome::Pass(bag))
        } else {
            Ok(FilterOutcome::Reject)
        }
    })
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
}
