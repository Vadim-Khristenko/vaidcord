# VaidCord Python SDK (`vaidcord`)

A community-driven Discord SDK inspired by Aiogram-style architecture.

## Install

```bash
uv add vaidcord
# optional storage backends
uv add "vaidcord[redis]"
uv add "vaidcord[mongo]"
uv add "vaidcord[postgres]"
```

## Core architecture

- `Bot` — Discord gateway/API client.
- `Dispatcher` — top-level router/runtime coordinator.
- `Router` — modular handler composition.
- `F` + filters — composable filtering and handler data injection.
- FSM middleware/storage — stateful workflows.

## Quick start (polling)

```python
import asyncio
from vaidcord import Bot, Dispatcher, Router, F

router = Router(name="main")

@router.message(F.message.content)
async def on_text(event):
    await event.message.answer("Got text message")

@router.on_command("start")
async def on_start(event):
    await event.message.answer("Hello from VaidCord")

async def main():
    bot = Bot(token="TOKEN")
    dp = Dispatcher()  # default FSM storage is in-memory
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## Runtime modes

- `await dp.start_polling(bot)`
- `await dp.start_websocket(bot)`
- `await dp.start_webhook(bot, drop_pending_updates=True)`

## Mock server quick guide

```python
import asyncio
from vaidcord.mock import MockDiscordServer

async def main():
    server = MockDiscordServer(host="127.0.0.1", port=8081)
    await server.start()
    try:
        print(server.base_url)
    finally:
        await server.stop()

asyncio.run(main())
```

## New HTTP resources included

- Current Application API (`GET/PATCH /applications/@me`)
- Role Connection Metadata API:
  - `GET /applications/{application.id}/role-connections/metadata`
  - `PUT /applications/{application.id}/role-connections/metadata`

See `docs/PYTHON_DRIVER.md` and `docs/APPLICATION_API.md`.
