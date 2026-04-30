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

Today, the Python SDK is the active implementation.

## Getting started (Python)

```bash
cd vaidcord-py
uv sync
uv run python -m pytest -q
```

Then read `vaidcord-py/README.md` and `vaidcord-py/docs/`.
