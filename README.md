# VaidCord Community SDK

VaidCord is a community-driven Discord SDK initiative designed to provide a clean, modern developer experience across multiple languages.

## Repository layout

- `vaidcord-py/` — production Python SDK (`import vaidcord`).
- `vaidcord-go/` — Go SDK placeholder.
- `vaidcord-rust/` — Rust SDK placeholder.

## Vision

- **Developer-first architecture** inspired by mature bot frameworks.
- **Composable routing** with filter-driven handler dispatch.
- **Stateful workflows** with FSM middleware and pluggable storage.
- **Testability by default** with first-class mock components.

Today the Python SDK is the most complete; the Rust and Go SDKs share the
same router / filter / dispatcher contract and grow toward parity with each
release.

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
