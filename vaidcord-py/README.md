# VaidCord

**High-performance Discord framework inspired by Aiogram 3.x architecture**

VaidCord is a modern, type-safe, and performant Python framework for building Discord bots. Built from the ground up with Python 3.12+ in mind, it combines the architectural elegance of Aiogram 3.x with native Discord API support.

## Features

- 🚀 **Maximum Performance**: Lightweight architecture without external Discord library dependencies
- 🎯 **Type-Safe**: Full type hints for better IDE support and fewer runtime errors
- 🏗️ **Aiogram-Inspired Architecture**: Familiar router-based event handling system
- 🔧 **Proxy Support**: Built-in HTTP client with proxy configuration
- 🧪 **Advanced Mocking**: Comprehensive testing utilities out of the box
- 📝 **Full Formatting Support**: Complete Discord markdown formatting utilities
- 🌐 **Custom Endpoints**: Support for alternative API endpoints and self-hosted instances
- ⚡ **Python 3.12+**: Leverages latest Python features for optimal performance

## Installation

```bash
# Using uv (recommended)
uv add vaidcord
uv add "vaidcord[mongo]"      # like aiogram[mongo]
uv add "vaidcord[redis]"
uv add "vaidcord[postgres]"
uv add "vaidcord[all-backends]"

# Or using pip
pip install vaidcord
```

`vaidcord[mongo]` uses `pymongo` asynchronous API (not Motor).

## Quick Start

```python
import asyncio
from vaidcord import Bot, Formatter, GatewayIntent

bot = Bot(
    token="YOUR_BOT_TOKEN",
    intents=GatewayIntent.GUILDS | GatewayIntent.GUILD_MESSAGES,
)

@bot.on_message()
async def handle_message(event):
    if event.message.content == "!hello":
        await bot.reply(
            channel_id=event.message.channel_id,
            message_id=event.message.id,
            content=Formatter.bold(f"Hello, {event.message.author.mention}!"),
        )

if __name__ == "__main__":
    bot.run()
```

## Aiogram-like architecture example (Bot + Dispatcher + Routers)

```python
import asyncio
from vaidcord import Bot, Dispatcher, Router, F

questions = Router(name="questions")
different_types = Router(name="different_types")

@different_types.message(F.message.content)
async def message_with_text(event):
    await event.message.answer("This is a text message!")

@questions.on_command("start")
async def cmd_start(event):
    await event.message.answer("Are you enjoying your work today?")

async def main():
    bot = Bot(token="TOKEN")
    dp = Dispatcher()
    dp.include_routers(questions, different_types)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## Core Components

### Bot
The main entry point for your Discord bot. Handles WebSocket connections, event dispatching, and API interactions.

### Router
Modular event handler organization, similar to Aiogram's router system.

Now supports:
- Router-level middlewares (including parent->child middleware chaining)
- FSM-aware handlers via `on_message_state(...)`
- Middleware priorities and event-scoped middleware registration
- Powerful filters (Magic filters, Regex/User filters, custom filters, command shortcuts)
- Specialized handlers: `on_topic_message`, `on_guild_message`, `on_private_message`
- Router-wide global filters via `add_filter(...)` / `@router.router_filter(...)`

### HTTP Client
High-performance HTTP client with:
- Automatic rate limit handling
- Proxy support
- Retry logic with exponential backoff
- Detailed error handling

### Formatting
Complete Discord formatting utilities:
- Text styles (bold, italic, underline, strikethrough, spoiler)
- Code blocks with syntax highlighting
- Mentions (users, roles, channels)
- Timestamps with various formats
- Links, quotes, and more

### Mocking
Advanced testing utilities:
- `MockBot`: Fully functional bot instance without network connections
- `MockGateway`: Simulate gateway events
- `MockHTTPClient`: Mock API responses
- `MockSettings`: easy runtime tuning for deterministic tests
- Helper functions for creating test data

## Configuration

### Basic Configuration

```python
from vaidcord import Bot

bot = Bot(
    token="YOUR_TOKEN",
    intents=32767,  # All intents
    shard_count=1,
)
```

### Advanced Configuration with Proxy

```python
from vaidcord import Bot
from vaidcord.http import HTTPConfig, HTTPClient

config = HTTPConfig(
    token="YOUR_TOKEN",
    proxy="http://proxy.example.com:8080",
    proxy_auth=aiohttp.BasicAuth("user", "password"),
    base_url="https://custom-discord-api.com/api",  # Custom endpoint
    timeout=30.0,
    max_retries=3,
)

client = HTTPClient(config)
```

## Testing

```python
import pytest
from vaidcord import MockBot, create_mock_message

@pytest.mark.asyncio
async def test_handler():
    bot = MockBot()
    await bot.start()
    
    @bot.on_message()
    async def handler(event):
        assert "hello" in event.message.content.lower()
    
    await bot.simulate_message("Hello, World!")
    await bot.stop()
```


## Async API & Lifecycle State Machine

VaidCord now includes a higher-level async API on `Bot` and an explicit lifecycle state machine (`BotState`) to make orchestration easier in production apps.

```python
from vaidcord import Bot, BotState

bot = Bot(token="YOUR_BOT_TOKEN")

# Async convenience API
async def send_startup_message() -> None:
    if await bot.wait_until_ready(wait_timeout=15) and bot.user is not None:
        await bot.send_message(channel_id=1234567890, content="Bot is online ✅")

# Typing indicators and richer message payloads are supported, too:
# await bot.trigger_typing(1234567890)
# await bot.send_poll(
#     channel_id=1234567890,
#     question="Ship this release?",
#     answers=["Yes", "No"],
#     duration_hours=24,
# )
# await bot.send_message(
#     1234567890,
#     components=[{"type": 1, "components": [...]}],
#     allowed_mentions={"parse": []},
# )

# You can also fetch and cache channels
# channel = await bot.fetch_channel(1234567890)
```

State progression is designed to be explicit: `IDLE -> CONNECTING -> IDENTIFYING -> READY`, with `RECONNECTING` and `STOPPING/STOPPED` available for resilient runtime control flows.

## FSM + Middleware Routing

```python
from vaidcord import Bot, FSMMiddleware, FSMScope, Router

bot = Bot(token="YOUR_BOT_TOKEN")
form_router = Router(name="form")
form_router.add_middleware(FSMMiddleware())
bot.include_router(form_router)

@form_router.on_message()
async def start_form(event):
    if event.message.content == "!start":
        fsm = event.context["fsm"]
        await fsm.set_state("form:name")
        await bot.send_message(event.message.channel_id, "What's your name?")

@form_router.on_message_state("form:name")
async def capture_name(event):
    fsm = event.context["fsm"]
    await fsm.update_data(name=event.message.content)
    await fsm.set_state("form:done")

# You also get multiple policy scopes in event.context["fsm_map"]:
# - FSMScope.USER
# - FSMScope.CHANNEL
# - FSMScope.TOPIC
# - FSMScope.GUILD
# - FSMScope.MEMBER
#
# Example of channel-scoped state handler:
# @form_router.on_message_state("maintenance", scope=FSMScope.CHANNEL)
# async def on_locked_channel(event):
#     ...
```

FSM is now package-structured for extensibility:
- `vaidcord.fsm.storage.base`
- `vaidcord.fsm.storage.memory`
- `vaidcord.fsm.storage.sqlite`
- `vaidcord.fsm.storage.redis` *(optional integration stub)*
- `vaidcord.fsm.storage.mongo` *(optional integration stub)*
- `vaidcord.fsm.storage.postgres` *(optional integration stub)*

## Powerful Filters (Aiogram-style)

```python
from vaidcord import F, RegexFilter, Router, UserFilter

router = Router(name="filters")

# Router-wide filter (applies to ALL handlers in this router)
router.add_filter(F.user.bot.equals(False))

# Magic filter expression
@router.on_message(F.message.content.startswith("!admin") & ~F.user.bot.equals(True))
async def admin_cmd(event):
    ...

# More aiogram-style expressions:
# F.user.id == 42
# F.message.content.regexp(r"^/item_(\\d+)$")
# F.message.content.lower() == "ping"

# Default command shortcuts
@router.on_command_start()
async def start(event):
    ...

@router.on_command_help()
async def help_cmd(event):
    ...

@router.on_command_settings()
async def settings(event):
    ...

# Generic command + extra filters
@router.on_command("ban", "kick", filters=[UserFilter(user_ids={123456789})])
async def moderation(event):
    ...

# Topic/thread-only messages
@router.on_topic_message()
async def topic_handler(event):
    ...

# Private messages only
@router.on_private_message()
async def dm_handler(event):
    ...

# Regex filter
@router.on_message(RegexFilter(r"^https?://"))
async def links(event):
    ...
```

## Requirements

- Python 3.12 or higher
- aiohttp (for HTTP/WebSocket transport)
- typing-extensions (for latest typing features)

## Development

```bash
# Clone the repository
git clone https://github.com/vaidcord/vaidcord.git
cd vaidcord

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check src/vaidcord
```

## Example Bots

- `examples/hello_echo_bot.py` — minimal `/start` hello-world + non-command echo flow.

## License

MIT License - See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- Inspired by the elegant architecture of [Aiogram 3.x](https://docs.aiogram.dev/)
- Built on the [Discord API](https://discord.com/developers/docs/intro)

## Mock server quick guide

Use `MockDiscordServer` when you want HTTP-level integration checks without hitting Discord.

```python
import asyncio
from vaidcord.mock import MockDiscordServer

async def main():
    server = MockDiscordServer(host="127.0.0.1", port=8081)
    await server.start()
    try:
        print("Mock server running at", server.base_url)
        # Run your test client/bot against server.base_url
    finally:
        await server.stop()

asyncio.run(main())
```

Recommended flow:
1. Start `MockDiscordServer` in test setup.
2. Point `BotConfig.base_url` and gateway URL to mock endpoints.
3. Use `MockGateway` events to simulate READY / MESSAGE_CREATE.
4. Assert outgoing API calls through mock HTTP history.
