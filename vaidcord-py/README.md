# VaidCord Python SDK (`vaidcord`)

VaidCord is a Python Discord SDK focused on clarity, composability, and testability.

## What this library is for

VaidCord helps you build Discord bots with a layered architecture:

- **Bot** handles Discord HTTP/Gateway transport.
- **Dispatcher** is the root router and runtime coordinator.
- **Router** organizes feature modules.
- **Filters + DI + Middleware** make handlers expressive.
- **FSM** provides durable, scoped conversational state.

## Installation

```bash
uv add vaidcord
# optional FSM backends
uv add "vaidcord[redis]"
uv add "vaidcord[mongo]"
uv add "vaidcord[postgres]"
```

## Core mental model

### 1) Bot + Dispatcher + Routers

- `Dispatcher` is always the **root router**.
- You include routers into dispatcher (or routers into routers).
- You **cannot** mount a dispatcher inside another dispatcher/router.

### 2) DI scope rules

Dependency providers are hierarchical:

- `dispatcher.provide("x", value)` → available to **all descendant routers**.
- `router.provide("x", value)` → available only inside that router subtree.

### 3) FSM defaults

`Dispatcher()` auto-registers FSM middleware.
If no storage is passed, it uses in-memory storage.

## Quick start (polling)

```python
import asyncio
from vaidcord import Bot, Dispatcher, Router, F

router = Router(name="main")

@router.message(F.message.content)
async def on_text(event):
    await event.message.answer("I got a text message")

@router.on_command("start")
async def on_start(event):
    await event.message.answer("Welcome to VaidCord")

async def main() -> None:
    bot = Bot(token="TOKEN")
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## Runtime modes

```python
await dp.start_polling(bot)
await dp.start_websocket(bot)
await dp.start_webhook(bot, drop_pending_updates=True)
```

## Detailed examples

### Feature routers

```python
from vaidcord import Router

admin_router = Router(name="admin")
public_router = Router(name="public")

dp.include_routers(admin_router, public_router)
```

### DI at dispatcher level (global)

```python
dp.provide("service_name", "billing")

@public_router.message()
async def handler(event, service_name: str):
    await event.message.answer(f"Service: {service_name}")
```

### DI at router level (local subtree)

```python
admin_router.provide("admin_tag", "[ADMIN]")

@admin_router.message()
async def admin_handler(event, admin_tag: str):
    await event.message.answer(f"{admin_tag} command accepted")
```

### Filters returning handler parameters

```python
from vaidcord import F

@router.message(F.message.content.startswith("/order"))
async def on_order(event, startswith: str, matched_text: str):
    await event.message.answer(f"Matched prefix: {startswith}")
```

### FSM storage configuration

```python
from vaidcord import Dispatcher
from vaidcord.fsm.storage.sqlite import SQLiteFSMStorage

dp = Dispatcher(storage=SQLiteFSMStorage("fsm.sqlite3"))
```

## Bot convenience methods

Common high-level bot calls:

- `send_message(...)`
- `reply(channel_id, message_id, content, ...)`
- `send_poll(...)`
- `trigger_typing(channel_id)`
- `fetch_channel(channel_id)`
- `fetch_guild(guild_id)`
- `fetch_user(user_id)`

Application API calls:

- `get_current_application()`
- `edit_current_application(...)`
- `get_application_role_connection_metadata(application_id)`
- `update_application_role_connection_metadata(application_id, records)`

## Mock/testing

Use `MockBot`, `MockGateway`, `MockHTTPClient`, and `MockDiscordServer` for deterministic tests.

```python
import asyncio
from vaidcord.mock import MockDiscordServer

async def run_mock_server():
    server = MockDiscordServer(host="127.0.0.1", port=8081)
    await server.start()
    try:
        print(server.base_url)
    finally:
        await server.stop()

asyncio.run(run_mock_server())
```

## Documentation map

- `docs/PYTHON_DRIVER.md` — architecture, runtime model, DI/FSM.
- `docs/APPLICATION_API.md` — Discord Application + Role Metadata resources.
- `docs/OAUTH2.md` — OAuth2 utilities.
