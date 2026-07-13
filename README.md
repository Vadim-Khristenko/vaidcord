# VaidCord Community SDK

VaidCord is a community-driven Discord SDK initiative designed to provide a clean, modern developer experience across multiple languages.

## Repository layout

- `vaidcord-py/` — production Python SDK (`import vaidcord`): full
  Discord API v10 REST coverage, resilient gateway (RESUME, zlib-stream
  compression), complete voice protocol (playback **and** receive, all
  encryption modes, bundled libopus binding), FSM, and a mock Discord
  server with a real websocket gateway and browser ops console.
- `vaidcord-go/` — Go SDK: Bot facade, resilient gateway, rate-limited
  REST client, full voice transport (wire-compatible with Python), FSM.
- `vaidcord-rust/` — Rust SDK: middleware + dispatcher, `Bot::builder()`
  runner, resilient gateway, rate-limited REST client, full voice
  transport (wire-compatible with Python, optional `opus` feature).

## Vision

- **Developer-first architecture** inspired by mature bot frameworks.
- **Composable routing** with filter-driven handler dispatch.
- **Stateful workflows** with FSM middleware and pluggable storage.
- **Voice as a first-class citizen** — bots can join, play (files or live
  streams), and listen, with an identical wire format across languages.
- **Testability by default** with first-class mock components, including
  a self-hosted mock Discord (REST + gateway websocket + chaos tools).

The Python SDK is the most complete; the Rust and Go SDKs share the same
router / filter / dispatcher contract and the same voice wire format,
verified by cross-language known-answer tests.

## Documentation

- [`UNITED.md`](UNITED.md) — single, cross-language description of the
  framework's architecture and conventions. Start here.
- `vaidcord-py/docs/` — Python-specific reference (filters, middleware,
  voice, OAuth2, DAVE).
- `vaidcord-rust/` — inline rustdoc; run `cargo doc --open --no-deps` from
  inside the directory.
- `vaidcord-go/` — inline godoc; run `go doc ./...` from inside the
  directory.

## Getting started (Python)

```bash
cd vaidcord-py
uv sync
uv run python -m pytest -q
uv run python examples/mock_server_ui.py   # then open http://127.0.0.1:18080
```

Then read [`vaidcord-py/README.md`](vaidcord-py/README.md) and the docs in
[`vaidcord-py/docs/`](vaidcord-py/docs/).

## Getting started (Rust)

```bash
cd vaidcord-rust
cargo test
cargo run --example decorator_router
```

## Getting started (Go)

```bash
cd vaidcord-go
go test ./...
go run ./examples/router-middleware
```
