# VaidCord Rust

Early Rust SDK scaffold for VaidCord.

Status: **scaffold only**. The first committed surface is intentionally small:

- Cargo package metadata
- crate constants
- config defaults for Discord API v10
- request metadata builder for Discord REST calls

```rust
let client = vaidcord::Client::new(vaidcord::Config::new("BOT_TOKEN"));
let request = client.request_parts("GET", "/users/@me");
```

Next steps:

- async HTTP transport selection
- Discord-aware error mapping
- gateway identify/heartbeat loop
- message/channel/user models
- router and filter primitives compatible with the Python SDK mental model
