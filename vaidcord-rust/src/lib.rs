pub mod client;
pub mod config;
pub mod error;
pub mod models;

pub use client::{Client, RequestParts};
pub use config::Config;
pub use error::{DiscordApiErrorBody, Error};
pub use models::MessagePayload;

pub const LIBRARY_NAME: &str = "vaidcord-rust";
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
pub const USER_AGENT: &str = concat!(
    "DiscordBot (https://github.com/Vadim-Khristenko/vaidcord, ",
    env!("CARGO_PKG_VERSION"),
    ") vaidcord-rust/",
    env!("CARGO_PKG_VERSION")
);
