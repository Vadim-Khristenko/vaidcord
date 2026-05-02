# VaidCord Rust

Early Rust SDK scaffold for VaidCord.

Status: **scaffold only**. The first committed surface is intentionally small:

- Cargo package metadata
- crate constants
- config defaults for Discord API v10
- async `reqwest` HTTP client with Discord headers
- JSON request/response helpers
- typed Discord API errors
- typed `User`, `Channel`, and `Message` response models
- first REST helpers: `get_current_user`, `fetch_channel`, `send_message`

```rust
let client = vaidcord::Client::new(vaidcord::Config::new("BOT_TOKEN"));
let request = client.request_parts("GET", "/users/@me", false);
let payload = vaidcord::MessagePayload::text("pong");
```

Next steps:

- richer REST resources
- gateway identify/heartbeat loop
- router and filter primitives compatible with the Python SDK mental model
