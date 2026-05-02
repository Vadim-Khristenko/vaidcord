# VaidCord Rust

Early Rust SDK scaffold for VaidCord.

Status: **scaffold only**. The first committed surface is intentionally small:

- Cargo package metadata
- crate constants
- config defaults for Discord API v10
- optional HTTP proxy configuration
- async `reqwest` HTTP client with Discord headers
- JSON request/response helpers
- typed Discord API errors
- typed `User`, `Channel`, and `Message` response models
- first REST helpers: `get_current_user`, `fetch_channel`, `send_message`
- formatter helpers for Discord markdown and mentions
- extractor-aware filters and router primitives: `command!`, `ExtractBag`, `FilterOutcome`, `register_on_message!`, `#[vaidcord::on_message(...)]`

```rust
let client = vaidcord::Client::new(vaidcord::Config::new("BOT_TOKEN"));
let request = client.request_parts("GET", "/users/@me", false);
let payload = vaidcord::MessagePayload::text("pong");
```

```rust
let client = vaidcord::Client::new(
    vaidcord::Config::new("BOT_TOKEN").with_proxy_url("http://127.0.0.1:8080"),
);
```

```rust
let mut router = vaidcord::Router::new();

#[vaidcord::on_message(filter = vaidcord::content_starts_with("!ping"))]
fn ping(message: &vaidcord::Message) -> vaidcord::HandlerResult {
    println!("{}", vaidcord::bold(&message.content));
    Ok(())
}

router.add_message_handler(ping_message_handler());
```

```rust
#[vaidcord::on_message(filter = vaidcord::command!("echo"))]
fn echo(message: &vaidcord::Message) -> vaidcord::HandlerResult {
    println!("{}", message.content);
    Ok(())
}
```

Runnable examples live in `examples/basic.rs`, `examples/router.rs`, and `examples/decorator_router.rs`.

Next steps:

- richer REST resources
- gateway identify/heartbeat loop
- richer router and filter primitives compatible with the Python SDK mental model
