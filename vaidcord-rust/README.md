# VaidCord Rust

Early Rust SDK scaffold for VaidCord.

Status: **scaffold only**. The first committed surface is intentionally small:

- Cargo package metadata
- crate constants
- config defaults for Discord API v10

```rust
let cfg = vaidcord::Config::new("BOT_TOKEN");
```

Next steps:

- async HTTP client with Discord-aware headers and error mapping
- gateway identify/heartbeat loop
- message/channel/user models
- router and filter primitives compatible with the Python SDK mental model
