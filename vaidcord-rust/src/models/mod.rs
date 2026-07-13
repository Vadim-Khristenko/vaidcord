//! Typed gateway/REST models. All deserializers ignore unknown fields so the
//! SDK stays tolerant of Discord API additions.

pub mod channel;
pub mod embed;
pub mod guild;
pub mod interaction;
pub mod message;
pub mod ready;
pub mod user;

pub use channel::Channel;
pub use embed::{Embed, EmbedAuthor, EmbedField, EmbedFooter, EmbedMedia, EmbedProvider};
pub use guild::{Guild, Member, Role};
pub use interaction::{Interaction, InteractionData, InteractionResponse};
pub use message::{BulkDeletedMessages, DeletedMessage, EditedMessage, Message, MessagePayload};
pub use ready::Ready;
pub use user::User;
