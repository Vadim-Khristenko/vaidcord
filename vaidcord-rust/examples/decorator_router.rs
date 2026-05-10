//! Multi-filter decorator example.
//!
//! Shows the three documented filter styles in turn:
//!
//! * Single positional filter (legacy single-filter form).
//! * Multiple positional filters AND'd together (the new mainstream style).
//! * `any = [...]` for OR composition.
//!
//! Run with `cargo run --example decorator_router`.

use vaidcord::{HandlerResult, Message, Router, command, content_starts_with};

#[vaidcord::on_message(command!("age"))]
fn age(message: &Message) -> HandlerResult {
    println!("/age | {} sent {}", message.author.username, message.content);
    Ok(())
}

// Multiple filters AND'd together — every filter must pass before the
// handler runs. This is the mainstream pattern; the macro accepts as many
// positional filters as you like.
#[vaidcord::on_message(content_starts_with("!"), command!("ping"))]
fn ping(message: &Message) -> HandlerResult {
    println!("!ping | {} sent {}", message.author.username, message.content);
    Ok(())
}

// `any = [..]` accepts at least one filter and combines them with OR.
#[vaidcord::on_message(any = [command!("hello"), command!("hi")])]
fn greet(message: &Message) -> HandlerResult {
    println!("/hello|hi | {} sent {}", message.author.username, message.content);
    Ok(())
}

// `filters = [..]` and `any = [..]` can also be combined explicitly. Every
// filter in `filters` plus at least one filter in `any` must match.
#[vaidcord::on_message(
    filters = [content_starts_with("/")],
    any = [command!("settings"), command!("help")]
)]
fn admin(message: &Message) -> HandlerResult {
    println!("/settings|help | admin route fired for {}", message.author.username);
    Ok(())
}

fn sample(content: &str) -> Message {
    vaidcord::Message {
        id: "1".to_string(),
        channel_id: "2".to_string(),
        guild_id: None,
        author: vaidcord::User {
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

fn main() -> Result<(), vaidcord::Error> {
    let mut router = Router::new();
    router.add_message_handler(age_message_handler());
    router.add_message_handler(ping_message_handler());
    router.add_message_handler(greet_message_handler());
    router.add_message_handler(admin_message_handler());

    for content in ["/age 30", "!ping", "/hi there", "/settings audio", "noise"] {
        println!("dispatching: {content:?}");
        router.dispatch_message(&sample(content))?;
    }
    Ok(())
}
