pub mod client;
pub mod config;
pub mod error;
pub mod extract;
pub mod filters;
pub mod formatter;
pub mod gateway;
pub mod models;
pub mod router;
pub mod voice;

pub use client::{Client, RequestParts};
pub use config::Config;
pub use error::{DiscordApiErrorBody, Error};
pub use extract::{Args, Bot, Captures, Command, Content, ExtractBag, FromHandlerArg};
pub use filters::{
    FilterOutcome, MessageFilter, and, command, command_help, command_help_with_prefixes,
    command_settings, command_settings_with_prefixes, command_start, command_start_with_prefixes,
    command_with_prefixes, not, or,
};
pub use formatter::{
    bold, code_block, escape_markdown, inline_code, italic, mention_channel, mention_role,
    mention_user,
};
pub use gateway::{GatewayClient, GatewayDispatch};
pub use models::{Channel, Message, MessagePayload, User};
pub use router::{
    HandlerResult, MessageHandler, MessageHandlerDef, Router, author_id, content_starts_with,
};
pub use vaidcord_macros::on_message;
pub use voice::{DaveIdentifyConfig, VoiceGatewayCloseCode, VoiceGatewayOpcode};

pub const LIBRARY_NAME: &str = "vaidcord-rust";
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
pub const USER_AGENT: &str = concat!(
    "DiscordBot (https://github.com/Vadim-Khristenko/vaidcord, ",
    env!("CARGO_PKG_VERSION"),
    ") vaidcord-rust/",
    env!("CARGO_PKG_VERSION")
);
