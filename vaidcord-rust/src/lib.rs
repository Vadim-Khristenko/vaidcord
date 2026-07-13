//! VaidCord — Rust SDK.
//!
//! Layers (see `UNITED.md` at the repository root):
//!
//! 1. [`gateway`] — resilient websocket client (heartbeat task, RESUME,
//!    backoff reconnect, typed [`Intents`]).
//! 2. [`bot`] — the high-level [`Bot`] facade wiring gateway dispatch ->
//!    parsed [`Event`]s -> the [`Dispatcher`].
//! 3. [`router`] / [`dispatcher`] — handler registry with filters,
//!    middleware (`(event, next)` semantics) and router nesting; middleware
//!    chains are precomposed at include-time.
//! 4. [`filters`] — small predicates AND'd per route, with value extraction.
//! 5. [`middleware`] — runs around the matched handler.
//! 6. [`models`] — typed serde models (unknown fields ignored).
//! 7. [`voice`] — voice gateway v8, UDP/IP discovery, RTP, transport
//!    encryption, frame pacing, audio sources and the receive path.

pub mod bot;
pub mod client;
pub mod config;
pub mod dispatcher;
pub mod error;
pub mod events;
pub mod extract;
pub mod filters;
pub mod formatter;
pub mod gateway;
pub mod http;
pub mod middleware;
pub mod models;
pub mod router;
pub mod voice;

pub use bot::{Bot, BotBuilder};
pub use client::{Client, RequestParts};
pub use config::Config;
pub use dispatcher::Dispatcher;
pub use error::{DiscordApiErrorBody, Error};
pub use events::{Event, EventKind};
pub use extract::{Args, Captures, Command, Content, ExtractBag, FromHandlerArg};
pub use middleware::{Middleware, Next, middleware};
pub use filters::{
    FilterOutcome, MessageFilter, and, command, command_help, command_help_with_prefixes,
    command_settings, command_settings_with_prefixes, command_start, command_start_with_prefixes,
    command_with_prefixes, not, or,
};
pub use formatter::{
    bold, code_block, escape_markdown, inline_code, italic, mention_channel, mention_role,
    mention_user,
};
pub use gateway::{
    GatewayClient, GatewayCloseAction, GatewayConnection, GatewayDispatch, GatewayEvent,
    GatewayHandle, GuildMembersRequest, Intents, PresenceUpdate, classify_gateway_close_code,
};
pub use http::{RateLimitInfo, parse_rate_limit_headers, route_bucket_key};
pub use models::{
    Channel, Embed, Guild, Interaction, InteractionResponse, Member, Message, MessagePayload,
    Ready, Role, User,
};
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
