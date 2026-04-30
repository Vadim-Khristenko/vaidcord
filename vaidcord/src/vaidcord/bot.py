"""
Bot client for VaidCord.

This module provides the main Bot class that serves as the entry point
for creating Discord bots with VaidCord.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum, IntFlag
from typing import Any

import aiohttp

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
    intents: int | GatewayIntent = GatewayIntent.all()
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
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._running = False
        self._sequence: int | None = None
        self._session_id: str | None = None
        self._heartbeat_interval: float | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._state = BotState.IDLE

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
        # Will be implemented with heartbeat ack tracking
        return 0.0

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
        """
        Make an API request to Discord.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint (e.g., "/channels/123/messages")
            **kwargs: Additional arguments for the request

        Returns:
            JSON response from the API
        """
        session = await self._create_session()
        url = f"{self.config.base_url}/v{self.config.api_version}{endpoint}"

        async with session.request(method, url, **kwargs) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise RuntimeError(f"API error {response.status}: {error_text}")
            return await response.json()

    async def _connect_gateway(self) -> None:
        """Connect to the Discord gateway."""
        self._state = BotState.CONNECTING
        if self._session is None:
            await self._create_session()

        # Use authenticated endpoint so we can track shard recommendations.
        gateway_info = await self.request("GET", "/gateway/bot")
        ws_url = gateway_info.get("url", self.config.gateway_url)
        recommended_shards = gateway_info.get("shards")
        if isinstance(recommended_shards, int) and recommended_shards > 0:
            if self.config.shard_count < recommended_shards:
                logger.info(
                    "Gateway recommends %s shard(s); current config uses %s",
                    recommended_shards,
                    self.config.shard_count,
                )

        # Connect to WebSocket
        self._ws = await self._session.ws_connect(
            f"{ws_url}?v={self.config.api_version}&encoding=json"
        )
        logger.info("Connected to Discord gateway")

    async def _send_payload(self, payload: dict[str, Any]) -> None:
        """Send a payload to the gateway."""
        if self._ws and not self._ws.closed:
            await self._ws.send_json(payload)

    async def _identify(self) -> None:
        """Send the identify payload to authenticate."""
        self._state = BotState.IDENTIFYING
        payload = {
            "op": 2,  # Identify
            "d": {
                "token": self.config.token,
                "intents": int(self.config.intents),
                "properties": {
                    "os": "linux",
                    "browser": "VaidCord",
                    "device": "VaidCord",
                },
                "compress": False,
                "large_threshold": 250,
            },
        }

        if self.config.shard_count > 1:
            payload["d"]["shard"] = [self.config.shard_id, self.config.shard_count]

        if self.config.presence:
            payload["d"]["presence"] = self.config.presence

        await self._send_payload(payload)
        logger.info("Sent identify payload")

    async def _heartbeat(self) -> None:
        """Send heartbeats to keep the connection alive."""
        while self._running and self._heartbeat_interval is not None:
            await asyncio.sleep(self._heartbeat_interval / 1000)
            await self._send_payload({"op": 1, "d": self._sequence})
            logger.debug("Sent heartbeat")

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
        """Receive and process messages from the gateway."""
        if not self._ws:
            return

        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                op = data.get("op")

                if op == 0:  # Dispatch
                    await self._handle_dispatch(data)
                elif op == 9:  # Invalid Session
                    logger.warning("Invalid session, reidentifying...")
                    self._state = BotState.RECONNECTING
                    await asyncio.sleep(5)
                    await self._identify()
                elif op == 10:  # Hello
                    self._heartbeat_interval = data["d"]["heartbeat_interval"]
                    logger.info(f"Heartbeat interval: {self._heartbeat_interval}ms")
                    await self._identify()
                    if self._heartbeat_task:
                        self._heartbeat_task.cancel()
                    self._heartbeat_task = asyncio.create_task(self._heartbeat())
                elif op == 11:  # Heartbeat ACK
                    logger.debug("Received heartbeat ACK")

            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                logger.warning(f"WebSocket closed/error: {msg.type}")
                break

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

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        if self._ws and not self._ws.closed:
            await self._ws.close()
            self._ws = None

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
        return await self.request(
            "POST",
            f"/channels/{channel_id}/messages",
            json=payload,
        )

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
        await self.request("POST", f"/channels/{channel_id}/typing")

    async def fetch_channel(self, channel_id: int) -> Channel:
        """Fetch and parse a channel from the API."""
        data = await self.request("GET", f"/channels/{channel_id}")
        channel = self._parse_channel(data)
        self._channels[channel.id] = channel
        return channel

    def run(self) -> None:
        """Run the bot (blocking)."""
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            pass

    def __repr__(self) -> str:
        return f"<Bot name='{self.name}' ready={self.is_ready}>"
