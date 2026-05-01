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
- In real projects, feature routers usually live at module level in separate files. The application entrypoint imports those routers and only assembles them into the dispatcher.

Example project shape:

```python
# features/profile.py
from vaidcord import Router

profile_router = Router(name="profile")


@profile_router.on_message_create()
async def handle_profile(event) -> None:
    ...
```

```python
# main.py
from vaidcord import Dispatcher
from features.profile import profile_router


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(profile_router)
    return dispatcher
```

Creating routers inside a dispatcher factory is still valid for tiny scripts, but it is not required and is not the preferred shape once features are split across files.

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
- Handlers can request `fsm: FSMContext` directly through dependency injection.
- State factories follow the aiogram-style shape: subclass `StatesGroup` and assign `State()` descriptors.

The FSM layer is intentionally scope-aware. That means the same message can be tracked per member, per channel, or per guild without changing the rest of the handler model.

Example:

```python
from vaidcord import Router, State, StatesGroup
from vaidcord.fsm import FSMContext


class OrderFood(StatesGroup):
    choosing_food_name = State()
    choosing_food_size = State()


router = Router(name="orders")


@router.on_message_state(OrderFood.choosing_food_name)
async def capture_food(event, fsm: FSMContext) -> None:
    await fsm.update_data(food=event.message.content)
    await fsm.set_state(OrderFood.choosing_food_size)
```

## Gateway event shortcuts

Every documented Discord receive event has a router decorator with the event name converted to snake case:

- `@router.on_message_create()`
- `@router.on_guild_member_add()`
- `@router.on_message_poll_vote_add()`
- `@router.on_voice_state_update()`

Common short aliases are available for the events people write most often:

- `@router.on_message()` is an alias for `MESSAGE_CREATE`.
- `@router.on_reaction_add()` is an alias for `MESSAGE_REACTION_ADD`.
- `@router.on_member_join()` is an alias for `GUILD_MEMBER_ADD`.
- `@router.on_typing()` is an alias for `TYPING_START`.
- `@router.on_interaction()` is an alias for `INTERACTION_CREATE`.

`@router.on_reconnect()` remains the lifecycle hook for the router tree, so the Discord Gateway `RECONNECT` receive event uses `@router.on_reconnect_event()`.

Discord only sends many of these events when the matching Gateway intent is present in `Bot(intents=...)`, and privileged intents such as `MESSAGE_CONTENT`, `GUILD_MEMBERS`, and `GUILD_PRESENCES` must also be enabled in the Developer Portal.

## Intents and permissions

Gateway intents and Discord permissions are different checks:

- Gateway intents control which events and fields arrive over the websocket.
- Guild/channel permissions control what the bot can read, send, manage, or moderate inside Discord.

For guild text commands that inspect `event.message.content`, configure both sides:

```python
from vaidcord import Bot
from vaidcord.bot import GatewayIntent

bot = Bot(
    token="...",
    intents=int(GatewayIntent.default() | GatewayIntent.MESSAGE_CONTENT),
)
```

`MESSAGE_CONTENT` is privileged. It must be enabled in the Discord Developer Portal before the bot identifies with it. Without it, Discord may still send `MESSAGE_CREATE`, but guild message content fields can be empty. With it requested but not enabled/approved, Discord can close the Gateway with close code `4014`.

`GUILD_MEMBERS` and `GUILD_PRESENCES` are also privileged. Keep them out of default examples and production configs unless the bot actually needs them. Member join/leave/update handlers require `GUILD_MEMBERS`; presence handlers require `GUILD_PRESENCES`.

Common channel permissions needed by examples:

- Text replies: `View Channel`, `Send Messages`, `Read Message History`.
- Embeds: `Embed Links`.
- Attachments: `Attach Files`.
- Reactions: `Add Reactions`, and sometimes `Read Message History`.
- Polls: `Send Messages` and `Send Polls`.
- Message moderation: `Manage Messages`.
- Thread workflows: `Create Public Threads`, `Create Private Threads`, `Send Messages in Threads`, or `Manage Threads` depending on the action.

When diagnosing a bot that starts and immediately stops, check the Gateway close code first. `4013` means invalid intents; `4014` means a privileged intent was requested without the required Developer Portal toggle or approval.

## Webhook event shortcuts

Discord outgoing webhook events use a separate `WebhookEventType` namespace because they arrive over HTTP and can share names with Gateway events. Router helpers are prefixed with `on_webhook_`:

- `@router.on_webhook_application_authorized()`
- `@router.on_webhook_entitlement_create()`
- `@router.on_webhook_lobby_message_create()`
- `@router.on_webhook_game_direct_message_delete()`

This keeps Gateway `ENTITLEMENT_CREATE` and Webhook `ENTITLEMENT_CREATE` separate for routing and type checks.

## Logging

`configure_logging()` installs a formatter that shows category, bot id, event id, and request id. HTTP logs promote the structured Discord request id into the visible `Request id="..."` field.

Bot identity is remembered globally after `READY`, `get_current_user()`, or `modify_current_user()`. After that point, contextless API and helper logs also get `Bot id="..."` instead of `"-"`.

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
- Make privileged intents opt-in through config or environment variables, especially `GUILD_MEMBERS` and `GUILD_PRESENCES`.
- Use `StatesGroup`, `State`, and injected `FSMContext` for multi-step conversations.
- Use event-specific shortcuts instead of raw `on_event(EventType.X)` when a documented Discord receive event exists.
- Use `MockBot` and `MockDiscordServer` to test event flow without Discord.

## Example map

- [examples/hello_echo_bot.py](../examples/hello_echo_bot.py) - smallest end-to-end bot.
- [examples/intents_permissions_bot.py](../examples/intents_permissions_bot.py) - explicit intents plus permission checklist.
- [examples/advanced_router_di.py](../examples/advanced_router_di.py) - nested routers, DI, middleware, poll helpers, and gateway-event shortcuts.
- [examples/fsm_conversation.py](../examples/fsm_conversation.py) - a stateful conversation flow.
- [examples/mock_testing.py](../examples/mock_testing.py) - deterministic testing with the mock layer.
- [examples/mock_server_ui.py](../examples/mock_server_ui.py) - local mock server with browser UI.
- [examples/oauth2_workflow.py](../examples/oauth2_workflow.py) - richer OAuth2 URL and token helpers.
