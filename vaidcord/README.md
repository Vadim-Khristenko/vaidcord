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
from vaincord import Bot, Formatter

bot = Bot(token="YOUR_BOT_TOKEN")

@bot.on_message()
async def handle_message(event):
    if event.message.content == "!hello":
        await event.message.channel.send(
            Formatter.bold(f"Hello, {event.message.author.mention}!")
        )

if __name__ == "__main__":
    bot.run()
```

## Core Components

### Bot
The main entry point for your Discord bot. Handles WebSocket connections, event dispatching, and API interactions.

### Router
Modular event handler organization, similar to Aiogram's router system.

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
from vaincord import Bot

bot = Bot(
    token="YOUR_TOKEN",
    intents=32767,  # All intents
    shard_count=1,
)
```

### Advanced Configuration with Proxy

```python
from vaincord import Bot
from vaincord.http import HTTPConfig, HTTPClient

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
from vaincord import MockBot, create_mock_message

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
