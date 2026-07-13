# VaidCord — Unified Documentation

VaidCord is a high-performance Discord framework available for three host
languages from a single repository:

| SDK         | Path              | Status   |
|-------------|-------------------|----------|
| Python      | `vaidcord-py/`    | Beta     |
| Rust        | `vaidcord-rust/`  | Beta     |
| Go          | `vaidcord-go/`    | Beta     |

This document is the single point of truth for the framework's architecture
and conventions. Each section ends with quick links to the more detailed,
language-specific docs in the respective subproject.

---

## 1. Mental model

Every SDK exposes the same conceptual layers:

1. **Gateway** — websocket pipe to Discord. Speaks opcodes, sequence ids,
   IDENTIFY/RESUME, heartbeats, sharding.
2. **Bot / Client** — high-level facade. Owns the gateway, REST client,
   cache, voice manager, command sync.
3. **Router** — handler registry + filter pipeline. Multiple routers can be
   nested; each router contributes filters and middleware.
4. **Filters** — small, side-effect-free predicates run before the handler.
   Filters can also extract values into the dependency-injection bag.
5. **Middleware** — runs around the matched handler with `(event, next)`
   semantics. Useful for auth, logging, rate limiting.
6. **Models** — typed dataclasses / structs for `User`, `Guild`, `Channel`,
   `Message`, plus the various event payloads.
7. **Voice** — gateway, UDP transport, audio frame pipeline, and the DAVE
   E2EE protocol stack.

The same flow holds in every language: an event arrives at the gateway,
the bot parses it into a typed model, the router walks its routes in
order, each route's filters either pass or reject, and a matched handler
runs through the middleware chain.

---

## 2. Filters — the mainstream pattern

Filters are functions of `(event) -> bool` (or `(event, bag) -> outcome`
when they extract values). The current best-practice is **multi-filter
routing**: list every filter the handler needs, the framework AND's them
together. OR composition is available via `any = [..]`.

### Python

```python
from vaidcord import F, Router

router = Router()

@router.on_message(
    F.message.content.startswith("!"),
    F.message.guild_id.is_not_(None),
)
async def guild_bang(event):
    await event.message.answer(f"got: {event.message.content}")
```

See `vaidcord-py/docs/FILTERS.md` for the full filter reference.

### Rust

```rust
use vaidcord::{HandlerResult, Message, Router, command, content_starts_with};

#[vaidcord::on_message(content_starts_with("!"), command!("ping"))]
fn ping(message: &Message) -> HandlerResult {
    println!("{} -> ping", message.author.username);
    Ok(())
}

#[vaidcord::on_message(any = [command!("hello"), command!("hi")])]
fn greet(_: &Message) -> HandlerResult { Ok(()) }
```

The macro accepts:

* Any number of positional filters — combined with logical AND.
* `filter = expr` — single-filter named form (back-compat).
* `filters = [a, b, c]` — explicit multi-filter form.
* `any = [a, b]` — at least one must match (OR composition).
* `filters = [..]` and `any = [..]` together.

The same syntax is available on the imperative path through the
`register_on_message!` macro_rules. See `vaidcord-rust/examples/decorator_router.rs`
for a runnable demo of every filter form.

### Go

```go
router := vaidcord.NewRouter("hello")
router.
    OnMessageCreate(vaidcord.ContentStartsWith("!"), vaidcord.Command("ping")).
    Handle(func(ctx context.Context, msg vaidcord.Message) error {
        log.Println(msg.Content)
        return nil
    })
```

---

## 3. Models, events, and parser performance (issue #26)

The Python SDK ships `__slots__`-frozen dataclasses for every hot-path
gateway model (`User`, `Guild`, `Channel`, `Message`, `Ready`, etc.).
Issue #26 added two new `BotConfig` flags to control how `raw_data` is
populated:

| Flag             | Default | Effect                                                   |
|------------------|---------|----------------------------------------------------------|
| `keep_raw_data`  | `True`  | Populate the `raw_data` field on parsed models.          |
| `share_raw_data` | `True`  | Share the source dict reference rather than copying it.  |

Setting `share_raw_data=True` (the new default) eliminates the per-parse
`dict()` copy that issue #26 identified as a major source of GC pressure
without changing the public API. Set `keep_raw_data=False` to skip
`raw_data` entirely; parsed models will reference a single shared empty
mapping.

Reproduce the numbers locally:

```bash
uv run python vaidcord-py/benchmarks/model_parse.py --iterations 50000
```

---

## 4. Voice + DAVE/MLS

All three SDKs now implement the Discord voice protocol end to end:

* **Handshake** — voice gateway v8 (identify/resume with `seq_ack`,
  heartbeats on a dedicated task), UDP IP discovery, protocol selection,
  and a shared close-code policy (`resume` / `rejoin` / `fatal`) with the
  same code table in every language.
* **Transport encryption** — `aead_aes256_gcm_rtpsize`,
  `aead_xchacha20_poly1305_rtpsize`, and `xsalsa20_poly1305_lite_rtpsize`
  in **both directions**. The wire format is byte-identical across SDKs:
  `unencrypted RTP prefix || ciphertext || 4-byte BE nonce counter`, AEAD
  AAD = the prefix, decrypted extension words stripped. Rust and Go pin
  compatibility with known-answer vectors generated from the Python
  implementation.
* **Playback** — drift-corrected 20 ms pacing (absolute deadlines, never
  cumulative sleeps) and an `AudioSource` abstraction in each language.
  Python additionally ships a bundled ctypes libopus binding, FFmpeg
  PCM/Opus sources (with a pure-Python Ogg demuxer), volume transform,
  and an `AudioPlayer` with pause/resume/stop. Go ports the Ogg demuxer
  and an ffmpeg-pipe Opus source; Rust offers an optional `opus` cargo
  feature backed by `audiopus`.
* **Receive** — inbound RTP is decrypted, demultiplexed by SSRC→user
  (fed from speaking events), and surfaced as per-user frames. Python
  decodes to PCM with per-speaker decoders and ships sinks
  (`WaveSink`, `BufferSink`, `CallbackSink`); Rust and Go yield
  `(user_id, opus)` frames.

The Python SDK exposes the DAVE protocol as a stand-alone subpackage,
laid out so it can be lifted into its own library without depending on the
rest of vaidcord:

```
vaidcord/voice/dave/
  errors.py        # DaveError hierarchy
  opcodes.py       # DaveOpcode (21-31) + server/client subsets
  models.py        # DaveTransition, DaveOutboundPayload, ...
  state.py         # DaveProtocolState
  controller.py    # DaveProtocolController (state machine)
  backend.py       # DaveCryptoBackend Protocol + UnsupportedDaveBackend
  crypto/          # HKDF, AES-128-GCM, frame nonce/AAD, forward-secure ratchet
  mls/             # MLSProvider Protocol + InProcessMLSProvider reference
  reference.py     # ReferenceDaveBackend (working end-to-end pipeline)
```

`ReferenceDaveBackend` plus `InProcessMLSProvider` give CI a working
end-to-end E2EE round-trip without depending on a heavyweight MLS library;
plug your own `MLSProvider` implementation in to bridge to a real
multi-party MLS stack (`mls-rs`, `openmls`, libdave). The runnable demo at
`vaidcord-py/examples/voice_dave_reference.py` walks the gateway opcode
flow end-to-end.

The Rust and Go voice layers ship matching opcode/close-code constants and
`DaveIdentifyConfig` carriers so backends can be wired in once MLS
backends land; DAVE gateway opcodes (21-31) pass through their voice
gateway state machines.

---

## 5. Mock Discord workspace

`vaidcord-py/examples/mock_server_ui.py` boots a self-hosted mock with a
browser ops console (guild/channel sidebar, message timeline + composer,
request inspector, gateway/chaos/rate-limit/scenario panels, live stats,
state export/import). Use it to:

* Connect a real `Bot` end-to-end: the mock serves an actual `/gateway`
  websocket (HELLO/IDENTIFY/READY, heartbeat ACKs, RESUME with event
  replay) and `GET /gateway/bot` points at it.
* Inspect every REST call your bot issues, in real time.
* Exercise failure paths: opt-in rate-limit simulation with
  `X-RateLimit-*` headers and Discord-shaped 429s, latency/error chaos
  injection, forced op 7/op 9 gateway events.
* Script timed scenarios and snapshot/restore the whole simulation.
* Switch between multiple "bot profiles" without restarting.

See `vaidcord-py/docs/MOCK.md` for the endpoint and control-plane
reference.

Run:

```bash
uv run python vaidcord-py/examples/mock_server_ui.py
# then open http://127.0.0.1:18080 in a browser
```

The mock server is intentionally network-free. Every endpoint and every
event resolves locally so unit tests (`uv run pytest`) and CI stay
deterministic.

---

## 6. Filesystem / package layout per SDK

### `vaidcord-py/`

* `src/vaidcord/bot.py` — `Bot`, `BotConfig`, gateway parser entry point.
* `src/vaidcord/router.py` — `Router`, decorators, filter pipeline.
* `src/vaidcord/http.py` — `HTTPClient`, retries, rate limits.
* `src/vaidcord/types/__init__.py` — slotted typed gateway models.
* `src/vaidcord/voice/` — voice gateway, UDP, audio, DAVE.
* `src/vaidcord/voice/dave/` — DAVE protocol stack (see §4).
* `src/vaidcord/mock/` — mock REST/Gateway server.
* `examples/` — runnable demos (see `examples/README.md`).
* `benchmarks/` — `router_hot_path.py`, `model_parse.py`.

### `vaidcord-rust/`

* `src/router.rs`, `src/filters.rs` — router + multi-filter machinery,
  nesting, per-router middleware.
* `src/middleware.rs`, `src/dispatcher.rs` — `(event, bag, next)`
  middleware and a standalone dispatcher with include-time chain
  precomposition.
* `src/bot.rs`, `src/gateway.rs`, `src/events.rs` — `Bot::builder()`
  runner facade over a resilient gateway (dedicated heartbeat task,
  RESUME, backoff, close-code policy, typed `Intents`).
* `src/http.rs`, `src/client.rs` — rate-limit buckets + retrying REST
  client with the common endpoint set.
* `src/extract.rs` — DI bag (`ExtractBag`) + `FromHandlerArg`.
* `src/voice/` — voice gateway v8 payloads/state machine, UDP IP
  discovery, RTP, all `_rtpsize` encryption modes both directions,
  drift-corrected pacer, receiver; optional `opus` feature (audiopus).
* `macros/src/lib.rs` — `#[on_message]` proc-macro (multi-filter, AND/OR).

### `vaidcord-go/`

* `router.go`, `dispatcher.go` — router + dispatcher hot path with
  precomputed middleware chains.
* `bot.go`, `gateway.go`, `intents.go` — `Bot` facade over a resilient
  gateway (heartbeat goroutine, RESUME, backoff, close-code policy).
* `client.go`, `ratelimit.go` — rate-limited, retrying REST client.
* `voice_*.go` — voice gateway v8 client, UDP IP discovery, RTP, all
  `_rtpsize` encryption modes both directions, drift-corrected `Play`,
  `Listen` receive path, pure-Go Ogg demuxer + ffmpeg Opus source.
* `fsm.go` — FSM manager/context with pluggable storage.

---

## 7. Cross-language contract guarantees

The three SDKs intentionally share these guarantees:

* **Filter ordering.** Filters run in the order written; the first reject
  short-circuits the route. Handlers run only when every filter passes.
* **Middleware composition.** Outer middleware wraps inner middleware; the
  innermost middleware wraps the handler. Per-event allocation is O(1) in
  the dispatch hot path (precomputed in Python via lambda chain, in Go via
  `composeMiddleware` at `Dispatcher.Include`, in Rust via `Box<dyn Fn>`
  routes).
* **Typed events first, raw payload second.** Parsed events expose typed
  fields (`event.message`, `message.author`, etc.). The `raw_data` /
  payload escape hatch is available for custom parsing but should not be
  the primary access path.
* **Voice wire compatibility.** All three SDKs produce byte-identical
  encrypted voice packets for every `_rtpsize` mode (Rust and Go pin this
  with known-answer vectors generated from the Python implementation) and
  share the same close-code policy table (fatal {4001-4005, 4011, 4012,
  4014, 4016, 4017}, rejoin {4006, 4009}, resume otherwise).
* **Voice DAVE compatibility.** All three SDKs use the same opcode
  numeric values and treat close code 4017 as "DAVE required but
  unavailable". The Python SDK ships a working reference backend; Rust and
  Go expose the constants and configuration carriers.

---

## 8. Where to go next

* **API reference** — generated per-language via `pdoc` (Python),
  `cargo doc` (Rust), and `go doc` (Go).
* **Issue tracker** — https://github.com/Vadim-Khristenko/vaidcord/issues
* **Per-language docs**:
  * Python: `vaidcord-py/docs/` (filters, middleware, voice, OAuth2, ...).
  * Rust: inline `///` rustdoc; `cargo doc --open --no-deps`.
  * Go: inline godoc; `go doc ./...`.
