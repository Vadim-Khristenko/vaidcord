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

# Or using pip
pip install vaidcord
```

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

## Core Components

### Bot
The main entry point for your Discord bot. Handles WebSocket connections, event dispatching, and API interactions.

### Router
Modular event handler organization, similar to Aiogram's router system.

Now supports:
- Router-level middlewares (including parent->child middleware chaining)
- FSM-aware handlers via `on_message_state(...)`
- Middleware priorities and event-scoped middleware registration

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

## License

MIT License - See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- Inspired by the elegant architecture of [Aiogram 3.x](https://docs.aiogram.dev/)
- Built on the [Discord API](https://discord.com/developers/docs/intro)
