"""
Mock utilities for testing VaidCord applications.

Provides comprehensive mocking capabilities for:
- HTTP API responses
- Gateway events
- Bot state
- Rate limiting simulation
- Error injection
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from vaidcord.types import (
    Channel,
    ChannelType,
    Event,
    EventType,
    Guild,
    Message,
    User,
)


@dataclass
class MockEvent:
    """Represents a mock event for testing."""

    event_type: EventType
    data: dict[str, Any]
    delay: float = 0.0  # Delay before emitting this event


@dataclass
class MockHTTPResponse:
    """Represents a mock HTTP response."""

    status: int = 200
    data: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    error_code: int | None = None
    error_message: str | None = None
    delay: float = 0.0  # Simulate network latency


class MockGateway:
    """
    Mock Discord Gateway for testing.

    Allows simulating gateway events without connecting to Discord.
    """

    def __init__(self) -> None:
        self._events: list[MockEvent] = []
        self._event_index = 0
        self._connected = False
        self._sequence = 0
        self._session_id = "mock_session_123"

    def add_event(self, event: MockEvent) -> None:
        """Add an event to the mock gateway queue."""
        self._events.append(event)

    def add_events(self, events: list[MockEvent]) -> None:
        """Add multiple events to the queue."""
        self._events.extend(events)

    def clear_events(self) -> None:
        """Clear all queued events."""
        self._events.clear()
        self._event_index = 0

    async def receive_event(self) -> dict[str, Any] | None:
        """Receive the next event from the queue."""
        if not self._connected or self._event_index >= len(self._events):
            return None

        mock_event = self._events[self._event_index]
        self._event_index += 1

        # Simulate delay
        if mock_event.delay > 0:
            await asyncio.sleep(mock_event.delay)

        self._sequence += 1
        return {
            "op": 0,  # Dispatch
            "t": mock_event.event_type.value,
            "s": self._sequence,
            "d": mock_event.data,
        }

    async def connect(self) -> None:
        """Simulate gateway connection."""
        self._connected = True
        self._sequence = 0

        # Add READY event automatically
        ready_event = MockEvent(
            event_type=EventType.READY,
            data={
                "user": {
                    "id": "999999999999999999",
                    "username": "TestBot",
                    "discriminator": "0000",
                    "bot": True,
                },
                "session_id": self._session_id,
                "guilds": [],
            },
        )
        self._events.insert(0, ready_event)

    async def disconnect(self) -> None:
        """Simulate gateway disconnection."""
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if gateway is connected."""
        return self._connected


class MockHTTPClient:
    """
    Mock HTTP client for testing API interactions.

    Allows configuring mock responses for different endpoints.
    """

    def __init__(self) -> None:
        self._responses: dict[str, MockHTTPResponse] = {}
        self._default_response = MockHTTPResponse(status=200, data={})
        self._request_history: list[dict[str, Any]] = []
        self._rate_limit_remaining = 5
        self._rate_limit_reset = datetime.now()

    def set_response(
        self,
        method: str,
        endpoint: str,
        response: MockHTTPResponse,
    ) -> None:
        """Set a mock response for a specific endpoint."""
        key = f"{method.upper()}:{endpoint}"
        self._responses[key] = response

    def set_default_response(self, response: MockHTTPResponse) -> None:
        """Set default response for unmatched endpoints."""
        self._default_response = response

    def clear_responses(self) -> None:
        """Clear all configured responses."""
        self._responses.clear()
        self._request_history.clear()

    def get_request_history(self) -> list[dict[str, Any]]:
        """Get history of all requests made."""
        return self._request_history.copy()

    async def request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Mock API request."""
        # Record request
        self._request_history.append(
            {
                "method": method,
                "endpoint": endpoint,
                "kwargs": kwargs,
                "timestamp": datetime.now(),
            }
        )

        # Find matching response
        key = f"{method.upper()}:{endpoint}"
        response = self._responses.get(key, self._default_response)

        # Simulate delay
        if response.delay > 0:
            await asyncio.sleep(response.delay)

        # Handle rate limiting simulation
        if response.headers.get("X-RateLimit-Remaining") is None:
            response.headers["X-RateLimit-Remaining"] = str(self._rate_limit_remaining)
            response.headers["X-RateLimit-Limit"] = "5"

        # Handle error responses
        if response.status >= 400:
            error_data = {
                "code": response.error_code or response.status,
                "message": response.error_message or "Mock error",
            }
            raise Exception(
                f"Mock HTTP Error {response.status}: {json.dumps(error_data)}"
            )

        return response.data


class MockBot:
    """
    Mock Bot for testing handlers and middleware.

    Provides a fully functional bot instance without network connections.
    """

    def __init__(self) -> None:
        from vaidcord.router import Router

        self._router = Router(name="mock_bot")
        self._gateway = MockGateway()
        self._http = MockHTTPClient()
        self._state: dict[str, Any] = {}
        self._users: dict[int, User] = {}
        self._guilds: dict[int, Guild] = {}
        self._channels: dict[int, Channel] = {}

        # Create mock bot user
        self._bot_user = User(
            id=999999999999999999,
            username="TestBot",
            discriminator="0000",
            bot=True,
        )
        self._users[self._bot_user.id] = self._bot_user

    @property
    def gateway(self) -> MockGateway:
        """Get the mock gateway."""
        return self._gateway

    @property
    def http(self) -> MockHTTPClient:
        """Get the mock HTTP client."""
        return self._http

    @property
    def user(self) -> User:
        """Get the bot's user object."""
        return self._bot_user

    @property
    def is_ready(self) -> bool:
        """Check if bot is ready."""
        return self._gateway.is_connected

    def on_message(self, *args: Any, **kwargs: Any) -> Callable:
        """Decorator for message handlers."""
        return self._router.on_message(*args, **kwargs)

    def on_event(self, event_type: EventType, *args: Any, **kwargs: Any) -> Callable:
        """Decorator for event handlers."""
        return self._router.on_event(event_type, *args, **kwargs)

    async def emit_event(self, event: Event) -> None:
        """Manually emit an event for testing."""
        await self._router.propagate_event(event)

    async def simulate_message(
        self,
        content: str,
        author: User | None = None,
        channel: Channel | None = None,
        guild: Guild | None = None,
    ) -> Event:
        """
        Simulate a MESSAGE_CREATE event.

        Args:
            content: Message content
            author: Message author (defaults to test user)
            channel: Channel (defaults to test channel)
            guild: Guild (optional)

        Returns:
            The created Event object
        """
        if author is None:
            author = User(
                id=123456789012345678, username="TestUser", discriminator="0000"
            )

        if channel is None:
            channel = Channel(
                id=111111111111111111, type=ChannelType.TEXT, name="test-channel"
            )

        message = Message(
            id=222222222222222222,
            channel=channel,
            author=author,
            content=content,
            timestamp=datetime.now(),
        )

        event = Event(
            type=EventType.MESSAGE_CREATE,
            data={"content": content},
            message=message,
            user=author,
            channel=channel,
            guild=guild,
        )

        await self.emit_event(event)
        return event

    def create_test_user(
        self,
        user_id: int | None = None,
        username: str = "TestUser",
        is_bot: bool = False,
    ) -> User:
        """Create and cache a test user."""
        if user_id is None:
            user_id = 123456789012345678 + len(self._users)

        user = User(
            id=user_id,
            username=username,
            discriminator="0000",
            bot=is_bot,
        )
        self._users[user.id] = user
        return user

    def create_test_guild(
        self,
        guild_id: int | None = None,
        name: str = "Test Guild",
    ) -> Guild:
        """Create and cache a test guild."""
        if guild_id is None:
            guild_id = 333333333333333333 + len(self._guilds)

        guild = Guild(id=guild_id, name=name)
        self._guilds[guild.id] = guild
        return guild

    def create_test_channel(
        self,
        channel_id: int | None = None,
        name: str = "test-channel",
        channel_type: ChannelType = ChannelType.TEXT,
    ) -> Channel:
        """Create and cache a test channel."""
        if channel_id is None:
            channel_id = 444444444444444444 + len(self._channels)

        channel = Channel(id=channel_id, type=channel_type, name=name)
        self._channels[channel.id] = channel
        return channel

    async def start(self) -> None:
        """Start the mock bot (connects gateway)."""
        await self._gateway.connect()

    async def stop(self) -> None:
        """Stop the mock bot (disconnects gateway)."""
        await self._gateway.disconnect()


def create_mock_message(
    content: str = "Test message",
    author_id: int = 123456789012345678,
    channel_id: int = 111111111111111111,
    guild_id: int | None = None,
) -> Message:
    """Create a mock message for testing."""
    author = User(id=author_id, username="TestUser", discriminator="0000")
    channel = Channel(id=channel_id, type=ChannelType.TEXT, name="test")
    guild = Guild(id=guild_id, name="Test Guild") if guild_id else None

    return Message(
        id=555555555555555555,
        channel=channel,
        author=author,
        content=content,
        timestamp=datetime.now(),
        guild=guild,
    )


def create_mock_event(
    event_type: EventType = EventType.MESSAGE_CREATE,
    content: str = "Test",
) -> Event:
    """Create a mock event for testing."""
    message = create_mock_message(content=content)
    return Event(
        type=event_type,
        data={"content": content},
        message=message,
        user=message.author,
        channel=message.channel,
        guild=message.guild,
    )


class MockResponseBuilder:
    """Helper class for building mock API responses."""

    @staticmethod
    def user(
        user_id: int = 123456789012345678,
        username: str = "TestUser",
        is_bot: bool = False,
    ) -> dict[str, Any]:
        """Build a mock user response."""
        return {
            "id": str(user_id),
            "username": username,
            "discriminator": "0000",
            "public_flags": 0,
            "bot": is_bot,
        }

    @staticmethod
    def guild(
        guild_id: int = 333333333333333333,
        name: str = "Test Guild",
        member_count: int = 100,
    ) -> dict[str, Any]:
        """Build a mock guild response."""
        return {
            "id": str(guild_id),
            "name": name,
            "icon": None,
            "owner_id": str(123456789012345678),
            "member_count": member_count,
            "features": [],
        }

    @staticmethod
    def channel(
        channel_id: int = 111111111111111111,
        name: str = "test",
        channel_type: int = 0,
    ) -> dict[str, Any]:
        """Build a mock channel response."""
        return {
            "id": str(channel_id),
            "name": name,
            "type": channel_type,
            "position": 0,
        }

    @staticmethod
    def message(
        message_id: int = 555555555555555555,
        content: str = "Test message",
        author_id: int = 123456789012345678,
        channel_id: int = 111111111111111111,
    ) -> dict[str, Any]:
        """Build a mock message response."""
        return {
            "id": str(message_id),
            "content": content,
            "channel_id": str(channel_id),
            "author": MockResponseBuilder.user(author_id),
            "timestamp": datetime.now().isoformat(),
            "edited_timestamp": None,
            "tts": False,
            "mention_everyone": False,
            "mentions": [],
            "mention_roles": [],
            "attachments": [],
            "embeds": [],
            "pinned": False,
            "type": 0,
        }

    @staticmethod
    def error(
        code: int = 50035,
        message: str = "Invalid Form Body",
        errors: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a mock error response."""
        response = {"code": code, "message": message}
        if errors:
            response["errors"] = errors
        return response
