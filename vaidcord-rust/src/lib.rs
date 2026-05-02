pub mod client;
pub mod config;
pub mod error;
pub mod extract;
pub mod filters;
pub mod formatter;
pub mod models;
pub mod router;

pub use client::{Client, RequestParts};
pub use config::Config;
pub use error::{DiscordApiErrorBody, Error};
pub use extract::{Args, Bot, Captures, Command, Content, ExtractBag, FromHandlerArg};
pub use filters::{FilterOutcome, MessageFilter, and, command, not, or};
pub use formatter::{
    bold, code_block, escape_markdown, inline_code, italic, mention_channel, mention_role,
    mention_user,
};
pub use models::{Channel, Message, MessagePayload, User};
pub use router::{
    HandlerResult, MessageHandler, MessageHandlerDef, Router, author_id, content_starts_with,
};
pub use vaidcord_macros::on_message;

pub const LIBRARY_NAME: &str = "vaidcord-rust";
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
pub const USER_AGENT: &str = concat!(
    "DiscordBot (https://github.com/Vadim-Khristenko/vaidcord, ",
    env!("CARGO_PKG_VERSION"),
    ") vaidcord-rust/",
    env!("CARGO_PKG_VERSION")
);
