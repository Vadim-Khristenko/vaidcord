use std::any::{Any, TypeId};
use std::collections::HashMap;
use std::sync::Arc;

use crate::error::Error;
use crate::models::Message;

#[derive(Clone, Default)]
pub struct ExtractBag {
    by_type: HashMap<TypeId, Arc<dyn Any + Send + Sync>>,
    by_name: HashMap<&'static str, Arc<dyn Any + Send + Sync>>,
}

impl ExtractBag {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn insert<T: Send + Sync + 'static>(&mut self, value: T) {
        self.by_type.insert(TypeId::of::<T>(), Arc::new(value));
    }

    pub fn insert_named<T: Send + Sync + 'static>(&mut self, name: &'static str, value: T) {
        self.by_name.insert(name, Arc::new(value));
    }

    pub fn get<T: Send + Sync + 'static>(&self) -> Option<Arc<T>> {
        self.by_type
            .get(&TypeId::of::<T>())
            .and_then(|value| Arc::clone(value).downcast::<T>().ok())
    }

    pub fn get_named<T: Send + Sync + 'static>(&self, name: &'static str) -> Option<Arc<T>> {
        self.by_name
            .get(name)
            .and_then(|value| Arc::clone(value).downcast::<T>().ok())
    }

    pub fn merge(&mut self, other: ExtractBag) {
        self.by_type.extend(other.by_type);
        self.by_name.extend(other.by_name);
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Bot {
    pub token: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Command {
    pub name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Args {
    pub raw: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Content {
    pub raw: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Captures {
    pub values: Vec<String>,
}

pub trait FromHandlerArg<E>: Sized + Send + 'static {
    fn from_handler_arg(bot: &Bot, event: &E, bag: &ExtractBag) -> Result<Self, Error>;
}

impl FromHandlerArg<Message> for Bot {
    fn from_handler_arg(bot: &Bot, _event: &Message, _bag: &ExtractBag) -> Result<Self, Error> {
        Ok(bot.clone())
    }
}

impl FromHandlerArg<Message> for Message {
    fn from_handler_arg(_bot: &Bot, event: &Message, _bag: &ExtractBag) -> Result<Self, Error> {
        Ok(event.clone())
    }
}

impl FromHandlerArg<Message> for Args {
    fn from_handler_arg(_bot: &Bot, _event: &Message, bag: &ExtractBag) -> Result<Self, Error> {
        bag.get::<Args>()
            .map(|value| (*value).clone())
            .ok_or_else(|| Error::MissingExtractor("Args"))
    }
}

impl FromHandlerArg<Message> for Command {
    fn from_handler_arg(_bot: &Bot, _event: &Message, bag: &ExtractBag) -> Result<Self, Error> {
        bag.get::<Command>()
            .map(|value| (*value).clone())
            .ok_or_else(|| Error::MissingExtractor("Command"))
    }
}

impl FromHandlerArg<Message> for Content {
    fn from_handler_arg(_bot: &Bot, event: &Message, _bag: &ExtractBag) -> Result<Self, Error> {
        Ok(Self {
            raw: event.content.clone(),
        })
    }
}

impl<T> FromHandlerArg<Message> for Option<T>
where
    T: FromHandlerArg<Message>,
{
    fn from_handler_arg(bot: &Bot, event: &Message, bag: &ExtractBag) -> Result<Self, Error> {
        Ok(T::from_handler_arg(bot, event, bag).ok())
    }
}
