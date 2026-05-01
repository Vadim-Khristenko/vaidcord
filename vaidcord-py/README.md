# VaidCord Python SDK (`vaidcord`)

VaidCord is a Python Discord SDK built around a small set of composable pieces: Bot, Dispatcher, Router, filters, middleware, and FSM.

Current package status: **Beta** (`0.1.0b1`).

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

## Send DM to a user

`Bot.send_dm(user_id, content, **kwargs)` opens or reuses the DM channel via
`POST /users/@me/channels`, then sends the message with the same payload options
as `send_message` (`embeds`, `components`, etc.).

There is also an alias: `send_message_to_user(...)`.

```python
message = await bot.send_dm(
    user_id=123456789012345678,
    content="Hi from VaidCord!",
    embeds=[{"title": "DM"}],
)
```

See runnable example: [examples/send_dm_to_user.py](examples/send_dm_to_user.py).

## Filter composition semantics

- Filter may return `bool` or `dict`.
- `dict` means: filter passed and payload is injected into `event.context["filter_data"]` and handler kwargs (by parameter name).
- `A & B`: both filters must pass; dict payloads from both sides are merged left-to-right.
- `A | B`: first passing filter wins; payload from that branch is used.

```python
@router.on_message((F.message.content.startswith("!admin")) & my_role_filter)
async def admin_handler(event: Event, role: str | None = None):
    ...
```

## Runtime modes

```python
await dp.start_polling(bot)
await dp.start_websocket(bot)
await dp.start_webhook(bot, drop_pending_updates=True)
await dp.start_polling_many([bot_a, bot_b])
await dp.start_webhook_many([bot_a, bot_b], drop_pending_updates=True)
```

`Dispatcher()` auto-registers FSM middleware. If you do not pass storage, it uses in-memory storage by default.

## Support status

| Area | Status | Notes |
| --- | --- | --- |
| Gateway lifecycle | supported | Identify, heartbeat, reconnect-oriented runtime, typed common events. |
| Messages | supported | Send, reply, edit, delete, reactions, pins, polls, and typed message events. |
| Channels and threads | partial | Core channel, invite, permission overwrite, and thread helpers exist; keep checking Discord parity as new fields/routes land. |
| Guilds and users | partial | Common fetch/update/list helpers exist; advanced administration is still expanding. |
| Interactions | partial | Low-level interaction callback/follow-up helpers exist; high-level decorator command sync is planned. |
| OAuth2 | supported | URL, token, refresh, revoke, and userinfo helpers. |
| FSM | supported | Scoped storage with memory, SQLite, Redis, Mongo, and Postgres backends. |
| Mock server/testing | supported | Local mock server, mock bot, builders, and deterministic test helpers. |
| Multi-bot startup | experimental | `start_polling_many` and `start_webhook_many` are covered by regression tests, but large deployments should load-test their router/middleware mix. |
| Voice | planned | Voice event shortcuts exist; voice gateway, UDP, speaking state, and audio transport are not implemented yet. |

## Performance and memory notes

- Prefer one `Dispatcher` with feature routers over duplicating large router trees per bot.
- Use external FSM storage for long-lived or multi-process state; in-memory storage is fastest but process-local.
- Keep filters cheap on high-volume routes. Expensive I/O belongs in handlers or middleware after narrow filters pass.
- Avoid storing large Discord payloads in `event.context`; pass IDs or compact service objects instead.
- For benchmarks, measure event propagation with representative middleware/filter counts and HTTP concurrency with real route mixes.
- Contributors should avoid per-event introspection and avoid unnecessary object copies in parser, filter, and router hot paths.

## Feature map

- [docs/PYTHON_DRIVER.md](docs/PYTHON_DRIVER.md) - architecture, DI, filters, middleware, FSM, lifecycle
- [docs/FILTERS.md](docs/FILTERS.md) - class filters, MagicFilter, MagicData, BotFilter, composition examples
- [docs/MIDDLEWARE.md](docs/MIDDLEWARE.md) - outer/inner middleware model and FSM as system middleware
- [docs/APPLICATION_API.md](docs/APPLICATION_API.md) - Discord application resources and role connection metadata
- [docs/OAUTH2.md](docs/OAUTH2.md) - OAuth2 helpers and token workflows
- [docs/PUBLISHING.md](docs/PUBLISHING.md) - beta versioning and PyPI trusted publishing workflow
- [examples/README.md](examples/README.md) - quick index of runnable examples

## Typing guide

`Router` handlers and middleware are typed via `vaidcord.typing` protocols:

- `EventHandler`: `async def handler(event: Event, **kwargs: Any) -> object | None`
- `Middleware`: `async def middleware(event: Event, next_handler: NextHandler) -> object | None`
- `FilterDataMap`: alias for filter payload (`dict[str, Any]`) injected into handler kwargs.
- `AbstractEventHandler` / `AbstractMiddleware`: ABC-based option for class-style architecture.
- `DIEventCallable` / `DIWrapper`: generic helpers (`TypeVar`, `ParamSpec`, `Concatenate`) for advanced wrappers.

```python
from vaidcord.router import Router
from vaidcord.types import Event

router = Router()

@router.on_message()
async def echo(event: Event) -> None:
    await event.message.answer("pong")
```

```python
from vaidcord.filters import F
from vaidcord.router import Router
from vaidcord.types import Event

router = Router()

@router.on_message(F.message.content.startswith("/set "))
async def set_value(event: Event, matched_text: str) -> None:
    # `matched_text` comes from filter-return payload
    await event.message.answer(f"Got: {matched_text}")
```

```python
from vaidcord.router import Router
from vaidcord.typing import NextHandler
from vaidcord.types import Event

router = Router()

@router.middleware()
async def trace(event: Event, next_handler: NextHandler):
    print("before", event.type)
    result = await next_handler(event)
    print("after", event.type)
    return result
```

```python
from vaidcord.typing import AbstractEventHandler
from vaidcord.types import Event

class PingHandler(AbstractEventHandler[Event]):
    async def __call__(self, event: Event, **kwargs: object) -> None:
        await event.message.answer("pong")
```
