# VaidCord Rust

Rust SDK for VaidCord. Status: **alpha** — the core layers described in
`UNITED.md` are implemented: gateway, bot facade, router + middleware +
dispatcher, rate-limited REST client, typed models, and voice transport
foundations that are wire-compatible with the Python SDK.

## Feature overview

### Bot facade

`Bot` wires gateway dispatch -> parsed models -> the dispatcher:

```rust,no_run
use vaidcord::{Bot, Intents, Message, Router};

#[tokio::main]
async fn main() -> Result<(), vaidcord::Error> {
    let mut router = Router::new();
    router.on_message(|message: &Message| {
        println!("{}: {}", message.author.username, message.content);
        Ok(())
    });

    Bot::builder()
        .token(std::env::var("DISCORD_TOKEN").unwrap())
        .intents(Intents::GUILDS | Intents::GUILD_MESSAGES | Intents::MESSAGE_CONTENT)
        .router(router)
        .run()
        .await
}
```

### Gateway

- Heartbeat runs on an independent tokio task (interval from HELLO, jittered
  first beat); a missed heartbeat ACK forces a reconnect.
- RESUME support (`session_id` + `resume_gateway_url` + sequence replay) and
  automatic reconnect with exponential backoff.
- Close-code policy per the Discord docs (`classify_gateway_close_code`):
  fatal (4004/4010-4014) vs re-identify (4007/4009/1000/1001) vs resume.
- Typed `Intents` bitflags, op 3 presence updates and op 8 guild-member
  requests via the cloneable `GatewayHandle`.

### Router, middleware, dispatcher

Middleware has `(event, next)` semantics; outer middleware wraps inner
middleware and the innermost wraps the handler. Routers nest via
`Router::include`, and the standalone `Dispatcher` precomposes each route's
middleware chain at include-time so the dispatch hot path is O(1) in
allocations (UNITED.md §7):

```rust
use vaidcord::{Dispatcher, Router, command};

let mut child = Router::named("commands");
child.use_middleware(|event, bag, next| {
    // before handler
    let result = next.run(event, bag);
    // after handler
    result
});
child.on_message_filtered(|message| { println!("pong {}", message.content); Ok(()) },
                          vec![command("ping")]);

let mut root = Router::named("root");
root.include(child); // root middleware would wrap child middleware

let mut dispatcher = Dispatcher::new();
dispatcher.include(&root);
```

Filters are unchanged: multi-filter AND routing, `any = [..]` OR composition,
`command!`, `ExtractBag` extraction, `register_on_message!` and
`#[vaidcord::on_message(...)]` all keep working.

### REST client

- Per-route rate-limit buckets parsed from `X-RateLimit-*` headers, with
  sleep-and-retry on 429 (`retry_after`, route or global) and exponential
  backoff on 5xx/transport errors.
- Endpoints: messages (send/get/edit/delete + reactions), channels
  (get/modify/delete), guilds (roles/members CRUD basics, bans), interactions
  (create response, followups, edit original), webhooks (execute), threads
  (start/join/leave), and application command sync.

### Models

Typed `User`, `Channel`, `Message`, `Guild`, `Role`, `Member`, `Embed`
(with a fluent builder), `Interaction`, `Ready`. All deserializers ignore
unknown fields.

### Voice transport foundations

The `voice` module mirrors `vaidcord-py/src/vaidcord/voice/` and is verified
wire-compatible (byte-for-byte known-answer tests generated from the Python
implementation):

- Voice gateway v8 websocket client: identify/resume/heartbeat with
  `seq_ack`, READY, session description, SSRC->user map from op 5/12/13, and
  the close-code policy (`classify_voice_close_code`: resume / rejoin /
  fatal). The protocol state machine (`VoiceGatewayState`) is synchronous and
  fully unit-tested.
- UDP socket with 74-byte IP discovery packets.
- RTP packet builder/parser (`_rtpsize` unencrypted prefix: 12-byte header +
  CSRCs + 4-byte extension preamble when the X bit is set).
- Transport encryption in both directions for `aead_aes256_gcm_rtpsize`,
  `aead_xchacha20_poly1305_rtpsize` and `xsalsa20_poly1305_lite_rtpsize`
  (RustCrypto). Wire format: `prefix || ciphertext || 4-byte BE nonce
  counter`; AEAD nonce = zero-padded counter; AAD = the unencrypted prefix.
- Drift-corrected 20 ms `FramePacer` (`MissedTickBehavior::Delay`),
  `speaking_payload` helpers, an `AudioSource` trait yielding opus packets,
  and a `VoiceReceiver` that decrypts inbound RTP into `(user_id, opus)`
  frames.
- DAVE opcode/close-code constants and `DaveIdentifyConfig` carrier.

Opus encode/decode is optional:

```toml
vaidcord = { version = "0.1", features = ["opus"] }  # needs system libopus
```

Without the `opus` feature the SDK is opus-passthrough: you feed pre-encoded
opus packets in and receive opus packets out.

## Examples

| Example | What it shows |
|---|---|
| `examples/basic.rs` | REST request parts + formatting helpers |
| `examples/router.rs` | imperative router registration |
| `examples/decorator_router.rs` | every `#[on_message]` filter form |
| `examples/bot_middleware.rs` | middleware ordering, nesting, dispatcher |
| `examples/voice_transport.rs` | no-network voice packet seal/open + IP discovery |

Run with `cargo run --example bot_middleware` etc.

## Development

```bash
cargo test                       # unit + doc tests
cargo test --features opus       # includes Opus encode/decode tests
cargo clippy --all-targets       # lint (warning-free)
cargo doc --open --no-deps       # API reference
```
