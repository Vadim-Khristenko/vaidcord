# Python driver architecture

VaidCord keeps the Python side intentionally small in surface area and rich in composition. The runtime pipeline is:

Bot -> Dispatcher -> Routers -> Middleware -> Filters -> Handlers

`Dispatcher` is a router, but it is also the root of the tree. That matters because dependency injection, middleware, and FSM state all flow downward through the router hierarchy.

## What each piece does

- `Bot`: transport, HTTP API surface, gateway lifecycle, and convenience methods like `send_message`, `reply`, `send_poll`, and `trigger_typing`.
- `Dispatcher`: the root router and lifecycle coordinator. It wires FSM middleware automatically and starts or stops the full event pipeline.
- `Router`: a feature module. It keeps command handlers, message handlers, lifecycle hooks, middleware, and local dependencies together.
- `Middleware`: cross-cutting logic that can inspect or mutate an event before it reaches a handler.
- `Filters`: matching logic plus optional data extraction.
- `FSM`: scoped conversation state with pluggable storage.

## Routing tree rules

- Routers can be nested with `include_router` or `include_routers`.
- A dispatcher cannot be nested inside another dispatcher or router.
- Child routers inherit dependencies, middleware, and router-level filters from their parents.

## Dependency injection

Dependencies are resolved by name. The lookup walks from the current router up through its parents.

- `dispatcher.provide("service_name", value)` makes the value visible to all descendants.
- `router.provide("service_name", value)` keeps the value local to that subtree.
- Only handler parameters that appear in the function signature are injected.

Example:

```python
from vaidcord import F, Router

router = Router(name="support")
router.provide("service_name", "helpdesk")


@router.on_message(F.message.content.startswith("/ticket"))
async def open_ticket(event, service_name: str, startswith: str, matched_text: str):
    await event.message.answer(f"[{service_name}] matched {startswith}: {matched_text}")
```

The interesting part is that `startswith` and `matched_text` come from the filter, not from your own code. When a filter returns a dictionary, that dictionary is merged into the handler kwargs.

## Filters

VaidCord supports three common styles of filters:

- Built-in command shortcuts like `on_command_start`, `on_command_help`, and `on_command_settings`.
- Magic filters through `F`, which support composition with `&`, `|`, and `~`.
- Custom callables and classes that return `bool` or `dict[str, Any]`.

Filter data is available in two places:

- `event.context["filter_data"]` for advanced inspection.
- Handler keyword arguments, matched by name.

That makes patterns like this possible:

```python
from vaidcord import F, Router

router = Router()


@router.on_message(F.message.content.startswith("/order") & F.user.id.in_({10, 11}))
async def on_order(event, startswith: str, matched_text: str) -> None:
    await event.message.answer(f"Prefix: {startswith}, full text: {matched_text}")
```

The `F.message.content.startswith(...)` filter passes and injects a small payload. That is one of the nicest parts of the framework because it keeps parsing close to matching.

## Middleware

Middleware wraps handler execution. It is applied in priority order, highest first, and it also inherits downward through the router tree.

- Use `@router.middleware(priority=...)` for a quick decorator.
- Use `add_middleware` when you want to register middleware dynamically.
- Use `event_types=[...]` to scope middleware to specific event classes.

Middleware receives the event and the next handler in the chain. It can observe or augment `event.context` before or after the wrapped handler runs.

## FSM

`Dispatcher()` auto-registers `FSMMiddleware`.

- Default storage is `MemoryFSMStorage`.
- You can pass `Dispatcher(storage=SQLiteFSMStorage("fsm.sqlite3"))` or another backend.
- `event.context["fsm"]` holds the primary FSM context.
- `event.context["fsm_map"]` holds all resolved scopes such as `user`, `channel`, `guild`, `topic`, and `member`.

The FSM layer is intentionally scope-aware. That means the same message can be tracked per member, per channel, or per guild without changing the rest of the handler model.

## Startup and shutdown

Routers can register lifecycle hooks:

- `on_startup`
- `on_shutdown`
- `on_reconnect`

The dispatcher exposes three startup modes:

- `start_polling(bot)`
- `start_websocket(bot)`
- `start_webhook(bot, drop_pending_updates=True)`

`start_webhook` calls `bot.delete_webhook(...)` before startup so the bot can cleanly switch into webhook-style deployment.

## Practical patterns

- Keep transport thin and move behavior into routers.
- Put shared services in `provide`, not in module globals.
- Use specialized handlers like `on_private_message` or `on_topic_message` when channel type matters.
- Use `on_message_state` for multi-step conversations.
- Use `MockBot` and `MockDiscordServer` to test event flow without Discord.

## Example map

- [examples/hello_echo_bot.py](../examples/hello_echo_bot.py) - smallest end-to-end bot.
- [examples/advanced_router_di.py](../examples/advanced_router_di.py) - nested routers, DI, middleware, and command shortcuts.
- [examples/fsm_conversation.py](../examples/fsm_conversation.py) - a stateful conversation flow.
- [examples/mock_testing.py](../examples/mock_testing.py) - deterministic testing with the mock layer.
- [examples/oauth2_workflow.py](../examples/oauth2_workflow.py) - richer OAuth2 URL and token helpers.
