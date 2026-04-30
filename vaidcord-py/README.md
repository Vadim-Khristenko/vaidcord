# VaidCord Python SDK (`vaidcord`)

VaidCord is a Python Discord SDK built around a small set of composable pieces: Bot, Dispatcher, Router, filters, middleware, and FSM.

## Why it exists

- Predictable routing with feature-oriented routers.
- Hierarchical dependency injection.
- Filter-driven handlers that can also extract data.
- Middleware for cross-cutting behavior.
- Pluggable FSM storage for conversational workflows.
- Mock utilities for fast, deterministic tests.

## Installation

```bash
uv add vaidcord
uv add "vaidcord[redis]"
uv add "vaidcord[mongo]"
uv add "vaidcord[postgres]"
```

## Recommended entry points

1. Start with [examples/hello_echo_bot.py](examples/hello_echo_bot.py) for the smallest runnable bot.
2. Read [docs/PYTHON_DRIVER.md](docs/PYTHON_DRIVER.md) for the architecture and runtime model.
3. Browse [examples/README.md](examples/README.md) for feature-focused examples.
4. Use [docs/OAUTH2.md](docs/OAUTH2.md) and [docs/APPLICATION_API.md](docs/APPLICATION_API.md) when you need auth or application resources.

## Mental model

- `Bot` is a facade/orchestrator that wires runtime + REST client + routers.
- `GatewayRuntime` owns websocket lifecycle (`connect/identify/heartbeat/dispatch loop`).
- `APIClient` owns Discord REST calls and delegates HTTP details to `HTTPClient`.
- `Dispatcher` is the root router and runtime coordinator.
- `Router` groups features into reusable modules.
- `Middleware` wraps event handling.
- `Filters` decide whether a handler runs and can inject data.
- `FSM` stores scoped state for conversations and workflows.

## Core patterns

- Use `dispatcher.provide("name", value)` for global services.
- Use `router.provide("name", value)` for feature-local services.
- Use `F` for expressive filters like `F.message.content.startswith("/start")`.
- Use `@router.on_message_state(...)` when a flow depends on FSM state.
- Use `MockBot` or `MockDiscordServer` for deterministic tests.

## Runtime modes

```python
await dp.start_polling(bot)
await dp.start_websocket(bot)
await dp.start_webhook(bot, drop_pending_updates=True)
```

`Dispatcher()` auto-registers FSM middleware. If you do not pass storage, it uses in-memory storage by default.

## Feature map

- [docs/PYTHON_DRIVER.md](docs/PYTHON_DRIVER.md) - architecture, DI, filters, middleware, FSM, lifecycle
- [docs/APPLICATION_API.md](docs/APPLICATION_API.md) - Discord application resources and role connection metadata
- [docs/OAUTH2.md](docs/OAUTH2.md) - OAuth2 helpers and token workflows
- [examples/README.md](examples/README.md) - quick index of runnable examples
