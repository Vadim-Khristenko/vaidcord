"""Tests for VaidCord mock utilities."""

import pytest

from vaidcord import (
    MockBot,
    create_mock_event,
    create_mock_message,
)
from vaidcord.formatting import Formatter
from vaidcord.types import ChannelType, EventType


@pytest.mark.asyncio
async def test_mock_bot_creation():
    """Test creating a mock bot instance."""
    bot = MockBot()
    assert bot.user is not None
    assert bot.user.username == "TestBot"
    assert bot.is_ready is False


@pytest.mark.asyncio
async def test_mock_bot_start_stop():
    """Test starting and stopping mock bot."""
    bot = MockBot()
    await bot.start()
    assert bot.is_ready is True
    await bot.stop()
    assert bot.is_ready is False


@pytest.mark.asyncio
async def test_mock_bot_simulate_message():
    """Test simulating a message event."""
    bot = MockBot()
    await bot.start()

    handler_called = False

    @bot.on_message()
    async def test_handler(event):
        nonlocal handler_called
        handler_called = True
        assert event.message is not None
        assert event.message.content == "Hello, World!"

    await bot.simulate_message("Hello, World!")
    assert handler_called is True

    await bot.stop()


@pytest.mark.asyncio
async def test_mock_http_client():
    """Test mock HTTP client functionality."""
    bot = MockBot()
    http = bot.http

    # Set up mock response
    from vaidcord.mock import MockHTTPResponse

    http.set_response(
        "GET",
        "/users/123",
        MockHTTPResponse(status=200, data={"id": "123", "username": "test"}),
    )

    # Make request
    result = await http.request("GET", "/users/123")
    assert result["username"] == "test"

    # Check request history
    history = http.get_request_history()
    assert len(history) == 1
    assert history[0]["method"] == "GET"
    assert history[0]["endpoint"] == "/users/123"


@pytest.mark.asyncio
async def test_mock_gateway_events():
    """Test mock gateway event queuing."""
    from vaidcord.mock import MockEvent

    bot = MockBot()
    gateway = bot.gateway

    # Add custom events
    gateway.add_event(
        MockEvent(
            event_type=EventType.MESSAGE_CREATE,
            data={"content": "Test message", "channel_id": "123"},
        )
    )

    await gateway.connect()
    event = await gateway.receive_event()

    assert event is not None
    assert event["t"] == "READY"  # First event is always READY

    event = await gateway.receive_event()
    assert event is not None
    assert event["t"] == "MESSAGE_CREATE"
    assert event["d"]["content"] == "Test message"

    await gateway.disconnect()


def test_create_mock_message():
    """Test create_mock_message helper function."""
    msg = create_mock_message(content="Test content")
    assert msg.content == "Test content"
    assert msg.author.username == "TestUser"
    assert msg.channel.type == ChannelType.TEXT


def test_create_mock_event():
    """Test create_mock_event helper function."""
    evt = create_mock_event(content="Test event")
    assert evt.type == EventType.MESSAGE_CREATE
    assert evt.message is not None
    assert evt.message.content == "Test event"


def test_formatter_basic():
    """Test basic formatting functions."""
    assert Formatter.bold("text") == "**text**"
    assert Formatter.italic("text") == "*text*"
    assert Formatter.underline("text") == "__text__"
    assert Formatter.strikethrough("text") == "~~text~~"
    assert Formatter.spoiler("text") == "||text||"


def test_formatter_mentions():
    """Test mention formatting."""
    assert Formatter.mention_user(123) == "<@123>"
    assert Formatter.mention_role(456) == "<@&456>"
    assert Formatter.mention_channel(789) == "<#789>"


def test_formatter_code():
    """Test code formatting."""
    assert Formatter.inline_code("code") == "`code`"
    assert "```python" in Formatter.code_block("print('hi')", "python")
    assert "print('hi')" in Formatter.code_block("print('hi')", "python")


def test_formatter_timestamp():
    """Test timestamp formatting."""
    from vaidcord.formatting import TimestampStyle

    result = Formatter.timestamp(timestamp=1618953630, style=TimestampStyle.SHORT_TIME)
    assert result == "<t:1618953630:t>"


def test_formatter_link():
    """Test link formatting."""
    result = Formatter.link("Google", "https://google.com")
    assert result == "[Google](https://google.com)"

    with pytest.raises(ValueError):
        Formatter.link("Invalid", "not-a-url")


def test_formatter_combine_styles():
    """Test combining multiple styles."""
    from vaidcord.formatting import TextStyle

    result = Formatter.combine_styles("text", TextStyle.BOLD, TextStyle.ITALIC)
    assert result == "***text***"

    result = Formatter.combine_styles("text", TextStyle.BOLD, TextStyle.UNDERLINE)
    assert result == "__**text**__"
