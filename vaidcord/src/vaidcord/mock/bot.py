from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from vaidcord.router import Router
from vaidcord.types import Channel, ChannelType, Event, EventType, Guild, Message, User

from .config import MockSettings
from .gateway import MockGateway
from .http import MockHTTPClient


class MockBot:
    def __init__(self, settings: MockSettings | None = None) -> None:
        self.settings = settings or MockSettings()
        self._router = Router(name="mock_bot")
        self._gateway = MockGateway(settings=self.settings)
        self._http = MockHTTPClient(settings=self.settings)
        self._state: dict[str, Any] = {}
        self._users: dict[int, User] = {}
        self._guilds: dict[int, Guild] = {}
        self._channels: dict[int, Channel] = {}

        self._bot_user = User(
            id=999999999999999999,
            username="TestBot",
            discriminator="0000",
            bot=True,
        )
        self._users[self._bot_user.id] = self._bot_user

    @property
    def gateway(self) -> MockGateway:
        return self._gateway

    @property
    def http(self) -> MockHTTPClient:
        return self._http

    @property
    def user(self) -> User:
        return self._bot_user

    @property
    def is_ready(self) -> bool:
        return self._gateway.is_connected

    def configure(self, **kwargs: Any) -> None:
        """Quick runtime tuning for mock subsystem."""
        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)

    def on_message(self, *args: Any, **kwargs: Any) -> Callable:
        return self._router.on_message(*args, **kwargs)

    def on_event(self, event_type: EventType, *args: Any, **kwargs: Any) -> Callable:
        return self._router.on_event(event_type, *args, **kwargs)

    async def emit_event(self, event: Event) -> None:
        await self._router.propagate_event(event)

    async def simulate_message(
        self,
        content: str,
        author: User | None = None,
        channel: Channel | None = None,
        guild: Guild | None = None,
    ) -> Event:
        if author is None:
            author = User(id=123456789012345678, username="TestUser", discriminator="0000")

        if channel is None:
            channel = Channel(id=111111111111111111, type=ChannelType.TEXT, name="test-channel")

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
        if user_id is None:
            user_id = 123456789012345678 + len(self._users)

        user = User(id=user_id, username=username, discriminator="0000", bot=is_bot)
        self._users[user.id] = user
        return user

    def create_test_guild(self, guild_id: int | None = None, name: str = "Test Guild") -> Guild:
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
        if channel_id is None:
            channel_id = 444444444444444444 + len(self._channels)
        channel = Channel(id=channel_id, type=channel_type, name=name)
        self._channels[channel.id] = channel
        return channel

    async def start(self) -> None:
        await self._gateway.connect()

    async def stop(self) -> None:
        await self._gateway.disconnect()
