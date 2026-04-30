"""
Bot client for VaidCord.

This module provides the main Bot class that serves as the entry point
for creating Discord bots with VaidCord.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum, IntFlag
from typing import Any

import aiohttp

from vaidcord.application import Application, ApplicationRoleConnectionMetadata
from vaidcord.api_client import APIClient
from vaidcord.gateway_runtime import GatewayRuntime
from vaidcord.router import Router
from vaidcord.types import (
    Channel,
    ChannelType,
    Event,
    EventType,
    Guild,
    Message,
    User,
)

logger = logging.getLogger(__name__)


class BotState(Enum):
    """Lifecycle states for the bot connection."""

    IDLE = "idle"
    CONNECTING = "connecting"
    IDENTIFYING = "identifying"
    READY = "ready"
    RECONNECTING = "reconnecting"
    STOPPING = "stopping"
    STOPPED = "stopped"


class GatewayIntent(IntFlag):
    """Gateway intents bitfield values from the Discord Gateway docs."""

    GUILDS = 1 << 0
    GUILD_MEMBERS = 1 << 1
    GUILD_MODERATION = 1 << 2
    GUILD_EMOJIS_AND_STICKERS = 1 << 3
    GUILD_INTEGRATIONS = 1 << 4
    GUILD_WEBHOOKS = 1 << 5
    GUILD_INVITES = 1 << 6
    GUILD_VOICE_STATES = 1 << 7
    GUILD_PRESENCES = 1 << 8
    GUILD_MESSAGES = 1 << 9
    GUILD_MESSAGE_REACTIONS = 1 << 10
    GUILD_MESSAGE_TYPING = 1 << 11
    DIRECT_MESSAGES = 1 << 12
    DIRECT_MESSAGE_REACTIONS = 1 << 13
    DIRECT_MESSAGE_TYPING = 1 << 14
    MESSAGE_CONTENT = 1 << 15
    GUILD_SCHEDULED_EVENTS = 1 << 16
    AUTO_MODERATION_CONFIGURATION = 1 << 20
    AUTO_MODERATION_EXECUTION = 1 << 21
    GUILD_MESSAGE_POLLS = 1 << 24
    DIRECT_MESSAGE_POLLS = 1 << 25

    @classmethod
    def default(cls) -> int:
        """Sensible default intents for common bot workloads."""
        return int(cls.GUILDS | cls.GUILD_MESSAGES | cls.DIRECT_MESSAGES)

    @classmethod
    def all(cls) -> int:
        """All currently documented intents."""
        return int(sum(intent.value for intent in cls))


@dataclass
class BotConfig:
    """Configuration for the Bot client."""

    token: str
    intents: int | GatewayIntent = GatewayIntent.default()
    shard_count: int = 1
    shard_id: int = 0
    presence: dict[str, Any] | None = None
    activity: dict[str, Any] | None = None
    api_version: str = "10"
    base_url: str = "https://discord.com/api"
    gateway_url: str = "wss://gateway.discord.gg"


class Bot(Router):
    """
    Main bot client for VaidCord.

    The Bot class is the central point for managing your Discord bot.
    It handles WebSocket connections, event dispatching, and API interactions.

    Example:
        bot = Bot(token="YOUR_TOKEN")

        @bot.on_message()
        async def handle_message(event: Event):
            print(f"Message from {event.message.author}: {event.message.content}")

        bot.run()
    """

    def __init__(
        self,
        token: str | None = None,
        config: BotConfig | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name="bot")

        if config is None:
            if token is None:
                raise ValueError("Either 'token' or 'config' must be provided")
            config = BotConfig(token=token, **kwargs)

        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._sequence: int | None = None
        self._session_id: str | None = None
        self._state = BotState.IDLE
        self.api_client = APIClient(
            token=self.config.token,
            base_url=self.config.base_url,
            api_version=self.config.api_version,
        )
        self.runtime = GatewayRuntime(self)

        # Cache for guilds, users, channels
        self._guilds: dict[int, Guild] = {}
        self._users: dict[int, User] = {}
        self._channels: dict[int, Channel] = {}
        self._user: User | None = None

        # Event handlers for internal events
        self._ready_event = asyncio.Event()

    @property
    def is_ready(self) -> bool:
        """Check if the bot is ready and connected."""
        return self._ready_event.is_set()

    @property
    def state(self) -> BotState:
        """Current lifecycle state."""
        return self._state

    @property
    def user(self) -> User | None:
        """Get the bot's user object."""
        return self._user

    @property
    def guilds(self) -> list[Guild]:
        """Get all cached guilds."""
        return list(self._guilds.values())

    @property
    def latency(self) -> float:
        """Get the WebSocket latency in seconds."""
        return self.runtime.latency

    async def _create_session(self) -> aiohttp.ClientSession:
        """Create an aiohttp session for API requests."""
        if self._session is None or self._session.closed:
            headers = {"Authorization": f"Bot {self.config.token}"}
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def _close_session(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an API request to Discord."""
        return await self.api_client.request(method, endpoint, **kwargs)


    async def _connect_gateway(self) -> None:
        await self.runtime.connect()

    async def _send_payload(self, payload: dict[str, Any]) -> None:
        await self.runtime.send_payload(payload)

    async def _identify(self) -> None:
        await self.runtime.identify()

    async def _heartbeat(self) -> None:
        return None

    async def _handle_dispatch(self, data: dict[str, Any]) -> None:
        """Handle a dispatch event from the gateway."""
        t = data.get("t")  # Event type
        d = data.get("d")  # Event data
        s = data.get("s")  # Sequence number

        if s is not None:
            self._sequence = s

        if t is None or d is None:
            return

        event_type_str = t.upper()
        try:
            event_type = EventType[event_type_str]
        except KeyError:
            logger.debug(f"Unknown event type: {event_type_str}")
            return

        # Parse event data into typed objects
        event = await self._parse_event(event_type, d)

        # Handle special events
        if event_type == EventType.READY:
            await self._handle_ready(d)
        elif event_type == EventType.MESSAGE_CREATE:
            await self._handle_message_create(event, d)

        # Propagate event to handlers
        await self.propagate_event(event)

    async def _parse_event(self, event_type: EventType, data: dict[str, Any]) -> Event:
        """Parse raw event data into a typed Event object."""
        event = Event(type=event_type, data=data, shard_id=self.config.shard_id)

        # Parse common objects if present
        if "user" in data:
            event.user = self._parse_user(data["user"])
        if "guild_id" in data:
            guild_id = int(data["guild_id"])
            event.guild = self._guilds.get(guild_id)
        if "channel_id" in data:
            channel_id = int(data["channel_id"])
            event.channel = self._channels.get(channel_id)

        return event

    async def _handle_ready(self, data: dict[str, Any]) -> None:
        """Handle the READY event."""
        user_data = data.get("user", {})
        bot_user = self._parse_user(user_data)
        self._user = bot_user
        self._users[bot_user.id] = bot_user

        # Cache guilds
        for guild_data in data.get("guilds", []):
            guild = self._parse_guild(guild_data)
            self._guilds[guild.id] = guild

        self._session_id = data.get("session_id")
        self._state = BotState.READY
        self._ready_event.set()
        logger.info(f"Bot logged in as {bot_user.username}")

    async def _handle_message_create(self, event: Event, data: dict[str, Any]) -> None:
        """Handle MESSAGE_CREATE event."""
        message = self._parse_message(data)
        event.message = message

        # Cache author and channel
        self._users[message.author.id] = message.author
        self._channels[message.channel.id] = message.channel

        if message.guild:
            self._guilds[message.guild.id] = message.guild

    def _parse_user(self, data: dict[str, Any]) -> User:
        """Parse user data into a User object."""
        return User(
            id=int(data["id"]),
            username=data.get("username", ""),
            discriminator=data.get("discriminator", "0"),
            global_name=data.get("global_name"),
            bot=data.get("bot", False),
            system=data.get("system", False),
            avatar=data.get("avatar"),
            banner=data.get("banner"),
            accent_color=data.get("accent_color"),
        )

    def _parse_guild(self, data: dict[str, Any]) -> Guild:
        """Parse guild data into a Guild object."""
        return Guild(
            id=int(data["id"]),
            name=data.get("name", ""),
            icon=data.get("icon"),
            owner=data.get("owner", False),
            owner_id=int(data["owner_id"]) if data.get("owner_id") else None,
            features=data.get("features", []),
            member_count=data.get("member_count"),
        )

    def _parse_channel(self, data: dict[str, Any]) -> Channel:
        """Parse channel data into a Channel object."""
        channel_type = ChannelType(data.get("type", 0))
        return Channel(
            id=int(data["id"]),
            type=channel_type,
            name=data.get("name"),
            topic=data.get("topic"),
            position=data.get("position"),
            nsfw=data.get("nsfw", False),
            parent_id=int(data["parent_id"]) if data.get("parent_id") else None,
        )

    def _parse_message(self, data: dict[str, Any]) -> Message:
        """Parse message data into a Message object."""
        from datetime import datetime

        # Parse timestamp
        ts_str = data.get("timestamp", "")
        timestamp = (
            datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts_str
            else datetime.now()
        )

        # Parse channel
        channel_id = int(data["channel_id"])
        channel = self._channels.get(channel_id)
        if channel is None:
            channel = Channel(id=channel_id, type=ChannelType.TEXT)

        # Parse author
        author = self._parse_user(data["author"])

        # Parse guild if present
        guild = None
        if "guild_id" in data:
            guild_id = int(data["guild_id"])
            guild = self._guilds.get(guild_id)

        # Parse mentions
        mentions = [self._parse_user(u) for u in data.get("mentions", [])]

        return Message(
            id=int(data["id"]),
            channel=channel,
            author=author,
            content=data.get("content", ""),
            timestamp=timestamp,
            tts=data.get("tts", False),
            mention_everyone=data.get("mention_everyone", False),
            mentions=mentions,
            mention_roles=[int(r) for r in data.get("mention_roles", [])],
            pinned=data.get("pinned", False),
            type=data.get("type"),
            guild=guild,
            bot=self,
        )

    async def _receive_messages(self) -> None:
        await self.runtime.run()

    async def start(self) -> None:
        """Start the bot client."""
        if self._running:
            raise RuntimeError("Bot is already running")

        self._running = True
        self._state = BotState.CONNECTING
        logger.info("Starting bot...")

        try:
            await self._connect_gateway()
            await self._receive_messages()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            await self.stop()

    async def wait_until_ready(self, wait_timeout: float | None = None) -> bool:
        """
        Wait for the bot to become ready.

        Returns:
            True if ready was reached before timeout, otherwise False.
        """
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=wait_timeout)
        except TimeoutError:
            return False
        return True

    async def stop(self) -> None:
        """Stop the bot client."""
        self._running = False
        self._state = BotState.STOPPING
        self._ready_event.clear()

        await self.runtime.stop()
        await self.api_client.close()
        await self._close_session()
        self._state = BotState.STOPPED
        logger.info("Bot stopped")

    async def send_message(
        self,
        channel_id: int,
        content: str | None = None,
        *,
        tts: bool = False,
        embeds: list[dict[str, Any]] | None = None,
        allowed_mentions: dict[str, Any] | None = None,
        components: list[dict[str, Any]] | None = None,
        sticker_ids: list[int] | None = None,
        message_reference: dict[str, Any] | None = None,
        flags: int | None = None,
        poll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Send a message with a convenient async API.

        This method is a higher-level wrapper around the raw HTTP request.
        """
        payload: dict[str, Any] = {"tts": tts}
        if content is not None:
            payload["content"] = content
        if embeds:
            payload["embeds"] = embeds
        if allowed_mentions is not None:
            payload["allowed_mentions"] = allowed_mentions
        if components:
            payload["components"] = components
        if sticker_ids:
            payload["sticker_ids"] = sticker_ids
        if message_reference is not None:
            payload["message_reference"] = message_reference
        if flags is not None:
            payload["flags"] = flags
        if poll is not None:
            payload["poll"] = poll
        has_sendable_content = any(
            payload.get(field)
            for field in ("content", "embeds", "components", "sticker_ids", "poll")
        ) or message_reference is not None
        if not has_sendable_content:
            raise ValueError(
                "send_message requires at least one of content/embeds/components/"
                "sticker_ids/message_reference"
            )
        return await self.api_client.send_message(channel_id, payload)

    async def reply(
        self,
        channel_id: int,
        message_id: int,
        content: str,
        *,
        tts: bool = False,
        allowed_mentions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reply to an existing message."""
        message_reference = {"message_id": str(message_id)}
        return await self.send_message(
            channel_id=channel_id,
            content=content,
            tts=tts,
            allowed_mentions=allowed_mentions,
            message_reference=message_reference,
        )

    async def send_poll(
        self,
        channel_id: int,
        question: str,
        answers: list[str],
        *,
        duration_hours: int = 24,
        allow_multiselect: bool = False,
        content: str | None = None,
    ) -> dict[str, Any]:
        """
        Send a Discord poll message.

        Based on Discord poll create request object:
        - up to 10 answers
        - duration in hours (max 32 days = 768h)
        """
        if not question.strip():
            raise ValueError("Poll question cannot be empty")
        if len(answers) < 2:
            raise ValueError("Poll requires at least 2 answers")
        if len(answers) > 10:
            raise ValueError("Poll supports at most 10 answers")
        if duration_hours < 1 or duration_hours > 768:
            raise ValueError("Poll duration must be between 1 and 768 hours")

        normalized_answers = []
        for answer in answers:
            value = answer.strip()
            if not value:
                raise ValueError("Poll answers cannot be empty")
            normalized_answers.append({"poll_media": {"text": value}})

        poll_payload: dict[str, Any] = {
            "question": {"text": question.strip()},
            "answers": normalized_answers,
            "duration": duration_hours,
            "allow_multiselect": allow_multiselect,
        }

        return await self.send_message(
            channel_id=channel_id,
            content=content,
            poll=poll_payload,
        )

    async def trigger_typing(self, channel_id: int) -> None:
        """Trigger a typing indicator in a channel."""
        await self.api_client.trigger_typing(channel_id)

    async def delete_webhook(self, *, drop_pending_updates: bool = False) -> dict[str, Any]:
        """Compatibility helper for aiogram-like startup flows."""
        return await self.request(
            "POST",
            "/webhooks",
            json={"drop_pending_updates": drop_pending_updates},
        )

    async def get_current_application(self) -> Application:
        data = await self.request("GET", "/applications/@me")
        return Application.from_dict(data)

    async def edit_current_application(self, **payload: Any) -> Application:
        data = await self.request("PATCH", "/applications/@me", json=payload)
        return Application.from_dict(data)

    async def get_application_role_connection_metadata(
        self,
        application_id: int,
    ) -> list[ApplicationRoleConnectionMetadata]:
        data = await self.request(
            "GET",
            f"/applications/{application_id}/role-connections/metadata",
        )
        return [ApplicationRoleConnectionMetadata.from_dict(item) for item in data]

    async def update_application_role_connection_metadata(
        self,
        application_id: int,
        records: list[ApplicationRoleConnectionMetadata],
    ) -> list[ApplicationRoleConnectionMetadata]:
        if len(records) > 5:
            raise ValueError("Discord allows at most 5 role connection metadata records")
        data = await self.request(
            "PUT",
            f"/applications/{application_id}/role-connections/metadata",
            json=[item.to_dict() for item in records],
        )
        return [ApplicationRoleConnectionMetadata.from_dict(item) for item in data]

    async def fetch_channel(self, channel_id: int) -> Channel:
        """Fetch and parse a channel from the API."""
        data = await self.api_client.fetch_channel(channel_id)
        channel = self._parse_channel(data)
        self._channels[channel.id] = channel
        return channel

    async def fetch_guild(self, guild_id: int) -> Guild:
        """Fetch and parse a guild from the API."""
        data = await self.api_client.fetch_guild(guild_id)
        guild = self._parse_guild(data)
        self._guilds[guild.id] = guild
        return guild

    async def fetch_user(self, user_id: int) -> User:
        """Fetch and parse a user from the API."""
        data = await self.api_client.fetch_user(user_id)
        user = self._parse_user(data)
        self._users[user.id] = user
        return user

    def run(self) -> None:
        """Run the bot (blocking)."""
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            pass

    def __repr__(self) -> str:
        return f"<Bot name='{self.name}' ready={self.is_ready}>"
