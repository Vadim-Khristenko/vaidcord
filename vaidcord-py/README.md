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

## Feature map

- [docs/PYTHON_DRIVER.md](docs/PYTHON_DRIVER.md) - architecture, DI, filters, middleware, FSM, lifecycle
- [docs/FILTERS.md](docs/FILTERS.md) - class filters, MagicFilter, MagicData, BotFilter, composition examples
- [docs/MIDDLEWARE.md](docs/MIDDLEWARE.md) - outer/inner middleware model and FSM as system middleware
- [docs/APPLICATION_API.md](docs/APPLICATION_API.md) - Discord application resources and role connection metadata
- [docs/OAUTH2.md](docs/OAUTH2.md) - OAuth2 helpers and token workflows
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
    await event.message.channel.send("pong")
```

```python
from vaidcord.filters import F
from vaidcord.router import Router
from vaidcord.types import Event

router = Router()

@router.on_message(F.message.content.startswith("/set "))
async def set_value(event: Event, matched_text: str) -> None:
    # `matched_text` comes from filter-return payload
    await event.message.channel.send(f"Got: {matched_text}")
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
        await event.message.channel.send("pong")
```
