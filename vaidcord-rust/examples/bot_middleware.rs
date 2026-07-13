//! Middleware + dispatcher demo (no network needed).
//!
//! Shows the full parity surface with the Go/Python SDKs:
//!
//! * `(event, next)` middleware on the dispatcher, a parent router and a
//!   nested child router — outer wraps inner wraps the handler.
//! * Router nesting via `Router::include`.
//! * A standalone `Dispatcher` with middleware chains precomposed at
//!   include-time.
//!
//! Run with `cargo run --example bot_middleware`.

use vaidcord::{
    Dispatcher, Event, ExtractBag, HandlerResult, Message, Next, Router, User, command,
};

fn make_message(content: &str) -> Message {
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

fn logging(label: &'static str) -> impl for<'a> Fn(&Event, &ExtractBag, Next<'a>) -> HandlerResult {
    move |event, bag, next| {
        println!("-> {label} (before)");
        let result = next.run(event, bag);
        println!("<- {label} (after)");
        result
    }
}

fn main() -> Result<(), vaidcord::Error> {
    // Child router with its own middleware + a filtered handler.
    let mut commands = Router::named("commands");
    commands.use_middleware(logging("commands middleware"));
    commands.on_message_filtered(
        |message: &Message| {
            println!("   handler: pong! ({})", message.content);
            Ok(())
        },
        vec![command("ping")],
    );

    // Parent router: middleware here wraps *around* the child's middleware.
    let mut root = Router::named("root");
    root.use_middleware(logging("root middleware"));
    // An auth-gate middleware that short-circuits by not calling `next`.
    root.use_middleware(|event: &Event, bag: &ExtractBag, next: Next<'_>| {
        if let Some(message) = event.message()
            && message.author.bot
        {
            println!("   blocked a bot message");
            return Ok(());
        }
        next.run(event, bag)
    });
    root.include(commands);

    // The dispatcher composes every middleware chain once, at include-time.
    let mut dispatcher = Dispatcher::new();
    dispatcher.use_middleware(logging("dispatcher middleware"));
    dispatcher.include(&root);
    println!("dispatcher has {} route(s)\n", dispatcher.route_count());

    println!("== dispatching '/ping' ==");
    dispatcher.dispatch_message(&make_message("/ping"))?;

    println!("\n== dispatching 'hello' (filter rejects; no chain runs) ==");
    dispatcher.dispatch_message(&make_message("hello"))?;

    Ok(())
}
