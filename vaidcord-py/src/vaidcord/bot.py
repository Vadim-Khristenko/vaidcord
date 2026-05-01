"""
Bot client for VaidCord.

This module provides the main Bot class that serves as the entry point
for creating Discord bots with VaidCord.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntFlag
from typing import Any, cast

import aiohttp

from vaidcord.api_client import APIClient
from vaidcord.application import Application, ApplicationRoleConnectionMetadata
from vaidcord.errors import DiscordAPIError, ForbiddenError, RateLimitError
from vaidcord.gateway_runtime import GatewayRuntime
from vaidcord.http import DiscordError
from vaidcord.logging import set_default_bot_id
from vaidcord.metadata import __version__, build_user_agent
from vaidcord.router import Router
from vaidcord.types import (
    BulkDeletedMessages,
    Channel,
    ChannelType,
    DeletedMessage,
    Event,
    EventType,
    Guild,
    Message,
    MessagePin,
    PollVote,
    RawGatewayEvent,
    Reaction,
    Ready,
    Resume,
    TypingStart,
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
    ignore_self_messages: bool = True


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
        if not self.config.ignore_self_messages:
            logger.warning(
                "Self message handling is enabled; this can cause message loops. "
                "Set ignore_self_messages=True to avoid this behavior."
            )
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._sequence: int | None = None
        self._session_id: str | None = None
        self._resume_gateway_url: str | None = None
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
        self._drop_pending_updates = False

    def _log_extra(self) -> dict[str, str]:
        """Return logging context for this bot when its identity is known."""
        return {} if self.id is None else {"bot_id": str(self.id)}

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
    def id(self) -> int | None:
        """Get the bot user ID if available."""
        if self._user is None:
            return None
        return self._user.id

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
            headers = {
                "Authorization": f"Bot {self.config.token}",
                "User-Agent": build_user_agent(),
                "X-VaidCord-Version": __version__,
            }
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
            logger.debug(
                {
                    "event": "gateway.dispatch.unknown",
                    "gateway_event": event_type_str,
                    "sequence": s,
                },
                extra=self._log_extra(),
            )
            return

        if self._drop_pending_updates and not self._ready_event.is_set() and event_type != EventType.READY:
            return

        event = await self._parse_event(event_type, d)

        # Handle special events
        if event_type == EventType.READY:
            await self._handle_ready(d)
            if self._drop_pending_updates:
                self._drop_pending_updates = False
        elif event_type in {EventType.MESSAGE_CREATE, EventType.MESSAGE_UPDATE} and event.message is not None:
            await self._handle_message_create(event, d)
            if (
                event_type == EventType.MESSAGE_CREATE
                and
                self.config.ignore_self_messages
                and self._user is not None
                and event.message is not None
                and event.message.author.id == self._user.id
            ):
                return

        # Propagate event to handlers
        await self.propagate_event(event)

    async def _parse_event(self, event_type: EventType, data: dict[str, Any]) -> Event:
        """Parse raw event data into a typed Event object."""
        event = Event(type=event_type, data=data, shard_id=self.config.shard_id)
        event.event_id = str(data.get("id") or data.get("event_id") or uuid.uuid4())
        event.raw_data = dict(data)
        event.bot = self
        if "interaction" in data:
            event.interaction = data.get("interaction")

        if event_type == EventType.READY:
            event.ready = self._parse_ready(data)
            event.user = event.ready.user
            event.payload = event.object = event.ready
        elif event_type == EventType.RESUMED:
            event.resume = Resume(
                session_id=self._session_id,
                sequence=self._sequence,
                raw_data=dict(data),
            )
            event.payload = event.object = event.resume
        elif event_type in {EventType.MESSAGE_CREATE, EventType.MESSAGE_UPDATE}:
            event.message = self._parse_message(data)
            event.user = event.message.author
            event.channel = event.message.channel
            event.guild = event.message.guild
            event.payload = event.object = event.message
        elif event_type == EventType.MESSAGE_DELETE:
            deleted = DeletedMessage(
                id=int(data["id"]),
                channel_id=int(data["channel_id"]),
                guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
                raw_data=dict(data),
            )
            event.deleted_message = deleted
            event.payload = event.object = deleted
        elif event_type == EventType.MESSAGE_DELETE_BULK:
            deleted_many = BulkDeletedMessages(
                ids=[int(item) for item in data.get("ids", [])],
                channel_id=int(data["channel_id"]),
                guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
                raw_data=dict(data),
            )
            event.deleted_messages = deleted_many
            event.payload = event.object = deleted_many
        elif event_type in {
            EventType.MESSAGE_REACTION_ADD,
            EventType.MESSAGE_REACTION_REMOVE,
            EventType.MESSAGE_REACTION_REMOVE_ALL,
            EventType.MESSAGE_REACTION_REMOVE_EMOJI,
        }:
            reaction = Reaction(
                user_id=int(data["user_id"]) if data.get("user_id") else None,
                channel_id=int(data["channel_id"]),
                message_id=int(data["message_id"]),
                guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
                member=data.get("member"),
                emoji=data.get("emoji", {}),
                raw_data=dict(data),
            )
            event.reaction = reaction
            event.payload = event.object = reaction
        elif event_type == EventType.TYPING_START:
            typing = TypingStart(
                channel_id=int(data["channel_id"]),
                user_id=int(data["user_id"]),
                timestamp=int(data.get("timestamp", 0)),
                guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
                member=data.get("member"),
                raw_data=dict(data),
            )
            event.typing = typing
            event.payload = event.object = typing
        elif event_type in {EventType.MESSAGE_POLL_VOTE_ADD, EventType.MESSAGE_POLL_VOTE_REMOVE}:
            poll_vote = PollVote(
                user_id=int(data["user_id"]),
                channel_id=int(data["channel_id"]),
                message_id=int(data["message_id"]),
                answer_id=int(data["answer_id"]),
                guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
                raw_data=dict(data),
            )
            event.poll_vote = poll_vote
            event.payload = event.object = poll_vote
        elif event_type in {EventType.GUILD_CREATE, EventType.GUILD_UPDATE, EventType.GUILD_DELETE}:
            event.guild = self._parse_guild(data)
            event.payload = event.object = event.guild
        elif event_type in {
            EventType.CHANNEL_CREATE,
            EventType.CHANNEL_UPDATE,
            EventType.CHANNEL_DELETE,
            EventType.THREAD_CREATE,
            EventType.THREAD_UPDATE,
            EventType.THREAD_DELETE,
        }:
            event.channel = self._parse_channel(data)
            event.payload = event.object = event.channel
        else:
            event.payload = event.object = RawGatewayEvent(
                type=event_type,
                data=dict(data),
                raw_data=dict(data),
            )

        if "user" in data:
            event.user = self._parse_user(data["user"])
        if "guild_id" in data:
            guild_id = int(data["guild_id"])
            event.guild = event.guild or self._guilds.get(guild_id)
        if "channel_id" in data:
            channel_id = int(data["channel_id"])
            event.channel = event.channel or self._channels.get(channel_id)

        return event

    def _parse_ready(self, data: dict[str, Any]) -> Ready:
        shard_data = data.get("shard")
        shard = (int(shard_data[0]), int(shard_data[1])) if shard_data else None
        return Ready(
            version=data.get("v"),
            user=self._parse_user(data["user"]) if data.get("user") else None,
            guilds=[self._parse_guild(item) for item in data.get("guilds", [])],
            session_id=data.get("session_id"),
            resume_gateway_url=data.get("resume_gateway_url"),
            shard=shard,
            application=data.get("application"),
            raw_data=dict(data),
        )

    async def _handle_ready(self, data: dict[str, Any]) -> None:
        """Handle the READY event."""
        user_data = data.get("user", {})
        bot_user = self._parse_user(user_data)
        self._remember_bot_user(bot_user)

        # Cache guilds
        for guild_data in data.get("guilds", []):
            guild = self._parse_guild(guild_data)
            self._guilds[guild.id] = guild

        self._session_id = data.get("session_id")
        self._resume_gateway_url = data.get("resume_gateway_url")
        self._state = BotState.READY
        self._ready_event.set()
        getattr(logger, "success", logger.info)(
            "Bot logged in as %s (id=%s)",
            bot_user.username,
            bot_user.id,
            extra=self._log_extra(),
        )

    async def _handle_message_create(self, event: Event, data: dict[str, Any]) -> None:
        """Handle MESSAGE_CREATE event."""
        message = self._parse_message(data)
        event.message = message

        # Cache author and channel
        if data.get("author") is not None:
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
            avatar_decoration_data=data.get("avatar_decoration_data"),
            collectibles=data.get("collectibles"),
            primary_guild=data.get("primary_guild"),
        )

    def _remember_bot_user(self, user: User) -> None:
        """Cache current bot user and propagate its id to log contexts."""
        self._user = user
        self._users[user.id] = user
        self.api_client.set_bot_id(user.id)
        set_default_bot_id(user.id)

    def _parse_guild(self, data: dict[str, Any]) -> Guild:
        """Parse guild data into a Guild object."""
        return Guild(
            id=int(data["id"]),
            name=data.get("name", ""),
            icon=data.get("icon"),
            icon_hash=data.get("icon_hash"),
            splash=data.get("splash"),
            discovery_splash=data.get("discovery_splash"),
            owner=data.get("owner", False),
            owner_id=int(data["owner_id"]) if data.get("owner_id") else None,
            permissions=data.get("permissions"),
            region=data.get("region"),
            afk_channel_id=int(data["afk_channel_id"]) if data.get("afk_channel_id") else None,
            afk_timeout=data.get("afk_timeout"),
            widget_enabled=data.get("widget_enabled"),
            widget_channel_id=int(data["widget_channel_id"]) if data.get("widget_channel_id") else None,
            verification_level=data.get("verification_level"),
            default_message_notifications=data.get("default_message_notifications"),
            explicit_content_filter=data.get("explicit_content_filter"),
            roles=data.get("roles", []),
            emojis=data.get("emojis", []),
            features=data.get("features", []),
            mfa_level=data.get("mfa_level"),
            application_id=int(data["application_id"]) if data.get("application_id") else None,
            system_channel_id=int(data["system_channel_id"]) if data.get("system_channel_id") else None,
            system_channel_flags=data.get("system_channel_flags"),
            rules_channel_id=int(data["rules_channel_id"]) if data.get("rules_channel_id") else None,
            joined_at=data.get("joined_at"),
            large=data.get("large"),
            unavailable=data.get("unavailable"),
            member_count=data.get("member_count"),
            voice_states=data.get("voice_states", []),
            members=data.get("members", []),
            channels=data.get("channels", []),
            threads=data.get("threads", []),
            presences=data.get("presences", []),
            max_presences=data.get("max_presences"),
            max_members=data.get("max_members"),
            vanity_url_code=data.get("vanity_url_code"),
            description=data.get("description"),
            banner=data.get("banner"),
            premium_tier=data.get("premium_tier"),
            premium_subscription_count=data.get("premium_subscription_count"),
            preferred_locale=data.get("preferred_locale"),
            public_updates_channel_id=int(data["public_updates_channel_id"]) if data.get("public_updates_channel_id") else None,
            max_video_channel_users=data.get("max_video_channel_users"),
            approximate_member_count=data.get("approximate_member_count"),
            approximate_presence_count=data.get("approximate_presence_count"),
            welcome_screen=data.get("welcome_screen"),
            nsfw_level=data.get("nsfw_level"),
            stickers=data.get("stickers", []),
            premium_progress_bar_enabled=data.get("premium_progress_bar_enabled"),
            safety_alerts_channel_id=int(data["safety_alerts_channel_id"]) if data.get("safety_alerts_channel_id") else None,
            incidents_data=data.get("incidents_data"),
            raw_data=dict(data),
        )

    def _parse_channel(self, data: dict[str, Any]) -> Channel:
        """Parse channel data into a Channel object."""
        try:
            channel_type = ChannelType(data.get("type", 0))
        except ValueError:
            channel_type = ChannelType.TEXT
        return Channel(
            id=int(data["id"]),
            type=channel_type,
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            name=data.get("name"),
            topic=data.get("topic"),
            position=data.get("position"),
            permission_overwrites=data.get("permission_overwrites", []),
            nsfw=data.get("nsfw", False),
            last_message_id=int(data["last_message_id"]) if data.get("last_message_id") else None,
            bitrate=data.get("bitrate"),
            user_limit=data.get("user_limit"),
            rate_limit_per_user=data.get("rate_limit_per_user"),
            recipients=[self._parse_user(item) for item in data.get("recipients", [])],
            icon=data.get("icon"),
            owner_id=int(data["owner_id"]) if data.get("owner_id") else None,
            application_id=int(data["application_id"]) if data.get("application_id") else None,
            managed=data.get("managed"),
            parent_id=int(data["parent_id"]) if data.get("parent_id") else None,
            last_pin_timestamp=data.get("last_pin_timestamp"),
            rtc_region=data.get("rtc_region"),
            video_quality_mode=data.get("video_quality_mode"),
            message_count=data.get("message_count"),
            member_count=data.get("member_count"),
            thread_metadata=data.get("thread_metadata", {}),
            member=data.get("member", {}),
            default_auto_archive_duration=data.get("default_auto_archive_duration"),
            permissions=data.get("permissions"),
            flags=data.get("flags"),
            total_message_sent=data.get("total_message_sent"),
            available_tags=data.get("available_tags", []),
            applied_tags=[int(item) for item in data.get("applied_tags", [])],
            default_reaction_emoji=data.get("default_reaction_emoji"),
            default_thread_rate_limit_per_user=data.get("default_thread_rate_limit_per_user"),
            default_sort_order=data.get("default_sort_order"),
            default_forum_layout=data.get("default_forum_layout"),
            raw_data=dict(data),
        )

    def _parse_message(self, data: dict[str, Any]) -> Message:
        """Parse message data into a Message object."""
        # Parse timestamp
        ts_str = data.get("timestamp", "")
        timestamp = (
            datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts_str
            else datetime.now()
        )
        edited_ts_str = data.get("edited_timestamp")
        edited_timestamp = (
            datetime.fromisoformat(edited_ts_str.replace("Z", "+00:00"))
            if edited_ts_str
            else None
        )

        channel_id = int(data.get("channel_id", data.get("id", 0)))
        channel = self._channels.get(channel_id)
        if channel is None:
            default_type = ChannelType.TEXT if data.get("guild_id") else ChannelType.DM
            channel = Channel(id=channel_id, type=default_type, guild_id=int(data["guild_id"]) if data.get("guild_id") else None)

        author_data = data.get("author") or {"id": "0", "username": "", "discriminator": "0"}
        author = self._parse_user(author_data)

        # Parse guild if present
        guild = None
        if "guild_id" in data:
            guild_id = int(data["guild_id"])
            guild = self._guilds.get(guild_id)

        mentions = [self._parse_user(u) for u in data.get("mentions", [])]
        mention_channels = [self._parse_channel(item) for item in data.get("mention_channels", [])]
        referenced_message = None
        if isinstance(data.get("referenced_message"), dict):
            referenced_message = self._parse_message(data["referenced_message"])
        thread = self._parse_channel(data["thread"]) if isinstance(data.get("thread"), dict) else None

        return Message(
            id=int(data["id"]),
            channel=channel,
            author=author,
            content=data.get("content", ""),
            timestamp=timestamp,
            edited_timestamp=edited_timestamp,
            tts=data.get("tts", False),
            mention_everyone=data.get("mention_everyone", False),
            mentions=mentions,
            mention_roles=[int(r) for r in data.get("mention_roles", [])],
            mention_channels=mention_channels,
            attachments=data.get("attachments", []),
            embeds=data.get("embeds", []),
            reactions=data.get("reactions", []),
            nonce=data.get("nonce"),
            pinned=data.get("pinned", False),
            webhook_id=int(data["webhook_id"]) if data.get("webhook_id") else None,
            type=data.get("type"),
            activity=data.get("activity", {}),
            application=data.get("application", {}),
            application_id=int(data["application_id"]) if data.get("application_id") else None,
            message_reference=data.get("message_reference", {}),
            message_snapshots=data.get("message_snapshots", []),
            flags=data.get("flags"),
            referenced_message=referenced_message,
            interaction_metadata=data.get("interaction_metadata", {}),
            interaction=data.get("interaction", {}),
            thread=thread,
            components=data.get("components", []),
            sticker_items=data.get("sticker_items", []),
            stickers=data.get("stickers", []),
            position=data.get("position"),
            role_subscription_data=data.get("role_subscription_data", {}),
            resolved=data.get("resolved", {}),
            poll=data.get("poll"),
            call=data.get("call"),
            shared_client_theme=data.get("shared_client_theme"),
            guild=guild,
            member=data.get("member", {}),
            raw_data=dict(data),
            bot=self,
        )

    def _parse_message_pin(self, data: dict[str, Any]) -> MessagePin:
        pinned_at = datetime.fromisoformat(data["pinned_at"].replace("Z", "+00:00"))
        return MessagePin(
            pinned_at=pinned_at,
            message=self._parse_message(data["message"]),
            raw_data=dict(data),
        )

    async def _receive_messages(self) -> None:
        await self.runtime.run()

    async def start(self) -> None:
        """Start the bot client."""
        if self._running:
            raise RuntimeError("Bot is already running")

        self._running = True
        self._state = BotState.CONNECTING
        logger.info(
            {
                "event": "bot.starting",
                "shard_id": self.config.shard_id,
                "shard_count": self.config.shard_count,
                "intents": int(self.config.intents),
                "drop_pending_updates": self._drop_pending_updates,
            },
            extra=self._log_extra(),
        )

        try:
            await self._connect_gateway()
            await self._receive_messages()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except asyncio.CancelledError:
            logger.info("Bot start task cancelled")
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
        logger.info({"event": "bot.stopped"}, extra=self._log_extra())

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
        return await self.request("POST", f"/channels/{channel_id}/messages", json=payload)

    async def reply(
        self,
        channel_id: int,
        message_id: int,
        content: str,
        *,
        tts: bool = False,
        allowed_mentions: dict[str, Any] | None = None,
        mention_author: bool = True,
    ) -> dict[str, Any]:
        """Reply to an existing message."""
        message_reference = {"message_id": str(message_id)}
        if not mention_author:
            allowed_mentions = {**(allowed_mentions or {}), "replied_user": False}
        return await self.send_message(
            channel_id=channel_id,
            content=content,
            tts=tts,
            allowed_mentions=allowed_mentions,
            message_reference=message_reference,
        )

    async def send_dm(self, user_id: int, content: str, **kwargs: Any) -> Message:
        """Open (or fetch) a DM channel with a user and send a message."""
        try:
            dm_channel = await self.request(
                "POST",
                "/users/@me/channels",
                json={"recipient_id": str(user_id)},
            )
        except DiscordAPIError as exc:
            if exc.status == 429:
                raise RateLimitError(
                    "Rate limited while opening DM channel",
                    retry_after=0.0,
                    global_limit=False,
                    raw_data=exc.raw_data,
                ) from exc
            if exc.status == 403:
                raise ForbiddenError(
                    "Cannot open DM channel. User may have DMs disabled or no shared server/permissions.",
                    raw_data=exc.raw_data,
                ) from exc
            raise

        channel_id = int(dm_channel["id"])
        try:
            message_data = await self.send_message(
                channel_id=channel_id,
                content=content,
                **kwargs,
            )
        except DiscordAPIError as exc:
            if exc.status == 429:
                raise RateLimitError(
                    "Rate limited while sending DM message",
                    retry_after=0.0,
                    global_limit=False,
                    raw_data=exc.raw_data,
                ) from exc
            if exc.status == 403:
                raise ForbiddenError(
                    "Cannot send DM. User may have DMs disabled or no shared server/permissions.",
                    raw_data=exc.raw_data,
                ) from exc
            raise

        message = self._parse_message(message_data)
        self._channels[message.channel.id] = message.channel
        self._users[message.author.id] = message.author
        return message

    async def send_message_to_user(self, user_id: int, content: str, **kwargs: Any) -> Message:
        """Alias for send_dm for semantic readability."""
        return await self.send_dm(user_id=user_id, content=content, **kwargs)

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

    async def list_messages(
        self,
        channel_id: int,
        *,
        limit: int = 50,
        before: int | None = None,
        after: int | None = None,
        around: int | None = None,
    ) -> list[Message]:
        """List and parse messages for a channel."""
        items = await self.api_client.list_messages(
            channel_id,
            limit=limit,
            before=before,
            after=after,
            around=around,
        )
        return [self._parse_message(item) for item in items]

    async def fetch_message(self, channel_id: int, message_id: int) -> Message:
        """Fetch and parse a single message from a channel."""
        data = await self.api_client.fetch_message(channel_id, message_id)
        return self._parse_message(data)

    async def edit_message(self, channel_id: int, message_id: int, **payload: Any) -> Message:
        """Edit a previously sent message."""
        data = await self.api_client.edit_message(channel_id, message_id, payload)
        return self._parse_message(data)

    async def delete_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        """Delete a message and clear it from the local cache path if present."""
        return await self.api_client.delete_message(channel_id, message_id)

    async def crosspost_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.api_client.crosspost_message(channel_id, message_id)

    async def add_reaction(self, channel_id: int, message_id: int, emoji: str) -> dict[str, Any]:
        return await self.api_client.add_reaction(channel_id, message_id, emoji)

    async def delete_own_reaction(self, channel_id: int, message_id: int, emoji: str) -> dict[str, Any]:
        return await self.api_client.delete_own_reaction(channel_id, message_id, emoji)

    async def delete_user_reaction(
        self,
        channel_id: int,
        message_id: int,
        emoji: str,
        user_id: int,
    ) -> dict[str, Any]:
        return await self.api_client.delete_user_reaction(channel_id, message_id, emoji, user_id)

    async def list_reactions(self, channel_id: int, message_id: int, emoji: str, **params: Any) -> list[User]:
        items = await self.api_client.list_reactions(channel_id, message_id, emoji, **params)
        return [self._parse_user(item) for item in items]

    async def clear_reactions(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.api_client.clear_reactions(channel_id, message_id)

    async def clear_reaction(self, channel_id: int, message_id: int, emoji: str) -> dict[str, Any]:
        return await self.api_client.clear_reaction(channel_id, message_id, emoji)

    async def bulk_delete_messages(self, channel_id: int, message_ids: list[int]) -> dict[str, Any]:
        return await self.api_client.bulk_delete_messages(channel_id, message_ids)

    async def list_pins(self, channel_id: int) -> list[Message]:
        items = await self.api_client.list_pins(channel_id)
        return [self._parse_message(item) for item in items]

    async def get_channel_pins(
        self,
        channel_id: int,
        *,
        before: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Fetch channel pins using Discord's modern paginated pins endpoint."""
        data = await self.api_client.get_channel_pins(
            channel_id,
            before=before,
            limit=limit,
        )
        items = data.get("items", [])
        return {
            **data,
            "items": [self._parse_message_pin(item) for item in items],
        }

    async def pin_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.api_client.pin_message(channel_id, message_id)

    async def unpin_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.api_client.unpin_message(channel_id, message_id)

    async def pin_channel_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        """Pin a message using Discord's modern /messages/pins route."""
        return await self.api_client.pin_channel_message(channel_id, message_id)

    async def unpin_channel_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        """Unpin a message using Discord's modern /messages/pins route."""
        return await self.api_client.unpin_channel_message(channel_id, message_id)

    async def get_poll_answer_voters(
        self,
        channel_id: int,
        message_id: int,
        answer_id: int,
        **params: Any,
    ) -> list[User]:
        """Get users who voted for a poll answer."""
        data = await self.api_client.get_poll_answer_voters(
            channel_id,
            message_id,
            answer_id,
            **params,
        )
        return [self._parse_user(item) for item in data.get("users", [])]

    async def end_poll(self, channel_id: int, message_id: int) -> Message:
        """Immediately end a poll owned by the current bot user."""
        data = await self.api_client.end_poll(channel_id, message_id)
        return self._parse_message(data)

    async def delete_webhook(self, *, drop_pending_updates: bool = False) -> dict[str, Any]:
        """Compatibility helper for aiogram-like startup flows."""
        if "discord.com/api" in self.config.base_url:
            logger.debug("Discord gateway bots do not use webhooks; delete_webhook is a no-op.")
            return {}
        try:
            return await self.request(
                "POST",
                "/webhooks",
                json={"drop_pending_updates": drop_pending_updates},
            )
        except DiscordError as exc:
            if "404" in exc.message:
                logger.debug("Webhook deletion is not supported by this API endpoint.")
                return {}
            raise

    def enable_drop_pending_updates(self) -> None:
        """Drop gateway events until READY is received."""
        self._drop_pending_updates = True
        logger.info({"event": "bot.drop_pending_updates.enabled"}, extra=self._log_extra())

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
        items = cast(list[dict[str, Any]], data)
        return [ApplicationRoleConnectionMetadata.from_dict(item) for item in items]

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
        items = cast(list[dict[str, Any]], data)
        return [ApplicationRoleConnectionMetadata.from_dict(item) for item in items]

    async def fetch_channel(self, channel_id: int) -> Channel:
        """Fetch and parse a channel from the API."""
        data = await self.api_client.fetch_channel(channel_id)
        channel = self._parse_channel(data)
        self._channels[channel.id] = channel
        return channel

    async def modify_channel(self, channel_id: int, **payload: Any) -> Channel:
        """Modify and parse a channel from the API."""
        data = await self.api_client.modify_channel(channel_id, payload)
        channel = self._parse_channel(data)
        self._channels[channel.id] = channel
        return channel

    async def delete_channel(self, channel_id: int) -> dict[str, Any]:
        """Delete a channel and clear it from the local cache."""
        result = await self.api_client.delete_channel(channel_id)
        self._channels.pop(channel_id, None)
        return result

    async def list_channel_invites(self, channel_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_channel_invites(channel_id)

    async def create_channel_invite(self, channel_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.create_channel_invite(channel_id, payload)

    async def edit_channel_permissions(
        self,
        channel_id: int,
        overwrite_id: int,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.edit_channel_permissions(channel_id, overwrite_id, payload)

    async def delete_channel_permission(self, channel_id: int, overwrite_id: int) -> dict[str, Any]:
        return await self.api_client.delete_channel_permission(channel_id, overwrite_id)

    async def follow_news_channel(self, channel_id: int, webhook_channel_id: int) -> dict[str, Any]:
        return await self.api_client.follow_news_channel(channel_id, webhook_channel_id)

    async def start_thread_from_message(self, channel_id: int, message_id: int, **payload: Any) -> Channel:
        data = await self.api_client.start_thread_from_message(channel_id, message_id, payload)
        return self._parse_channel(data)

    async def start_thread_without_message(self, channel_id: int, **payload: Any) -> Channel:
        data = await self.api_client.start_thread_without_message(channel_id, payload)
        return self._parse_channel(data)

    async def join_thread(self, channel_id: int) -> dict[str, Any]:
        return await self.api_client.join_thread(channel_id)

    async def leave_thread(self, channel_id: int) -> dict[str, Any]:
        return await self.api_client.leave_thread(channel_id)

    async def add_thread_member(self, channel_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.add_thread_member(channel_id, user_id)

    async def remove_thread_member(self, channel_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.remove_thread_member(channel_id, user_id)

    async def list_public_archived_threads(self, channel_id: int, **params: Any) -> dict[str, Any]:
        return await self.api_client.list_public_archived_threads(channel_id, **params)

    async def list_private_archived_threads(self, channel_id: int, **params: Any) -> dict[str, Any]:
        return await self.api_client.list_private_archived_threads(channel_id, **params)

    async def list_joined_private_archived_threads(self, channel_id: int, **params: Any) -> dict[str, Any]:
        return await self.api_client.list_joined_private_archived_threads(channel_id, **params)

    async def fetch_guild(self, guild_id: int) -> Guild:
        """Fetch and parse a guild from the API."""
        data = await self.api_client.fetch_guild(guild_id)
        guild = self._parse_guild(data)
        self._guilds[guild.id] = guild
        return guild

    async def fetch_guild_preview(self, guild_id: int) -> dict[str, Any]:
        return await self.api_client.fetch_guild_preview(guild_id)

    async def list_guild_channels(self, guild_id: int) -> list[Channel]:
        """List and parse guild channels from the API."""
        items = await self.api_client.list_guild_channels(guild_id)
        channels = [self._parse_channel(item) for item in items]
        for channel in channels:
            self._channels[channel.id] = channel
        return channels

    async def list_guild_roles(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_roles(guild_id)

    async def create_guild_role(self, guild_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.create_guild_role(guild_id, payload)

    async def modify_guild_role_positions(
        self,
        guild_id: int,
        positions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return await self.api_client.modify_guild_role_positions(guild_id, positions)

    async def modify_guild_role(self, guild_id: int, role_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.modify_guild_role(guild_id, role_id, payload)

    async def delete_guild_role(self, guild_id: int, role_id: int) -> dict[str, Any]:
        return await self.api_client.delete_guild_role(guild_id, role_id)

    async def get_guild_member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.get_guild_member(guild_id, user_id)

    async def list_guild_members(self, guild_id: int, **params: Any) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_members(guild_id, **params)

    async def add_guild_member(self, guild_id: int, user_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.add_guild_member(guild_id, user_id, payload)

    async def modify_guild_member(self, guild_id: int, user_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.modify_guild_member(guild_id, user_id, payload)

    async def remove_guild_member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.remove_guild_member(guild_id, user_id)

    async def ban_guild_member(self, guild_id: int, user_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.ban_guild_member(guild_id, user_id, **payload)

    async def unban_guild_member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.unban_guild_member(guild_id, user_id)

    async def list_guild_bans(self, guild_id: int, **params: Any) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_bans(guild_id, **params)

    async def get_guild_ban(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.get_guild_ban(guild_id, user_id)

    async def list_guild_emojis(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_emojis(guild_id)

    async def list_guild_stickers(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_stickers(guild_id)

    async def list_scheduled_events(self, guild_id: int, **params: Any) -> list[dict[str, Any]]:
        return await self.api_client.list_scheduled_events(guild_id, **params)

    async def create_scheduled_event(self, guild_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.create_scheduled_event(guild_id, payload)

    async def fetch_scheduled_event(self, guild_id: int, event_id: int, **params: Any) -> dict[str, Any]:
        return await self.api_client.fetch_scheduled_event(guild_id, event_id, **params)

    async def modify_scheduled_event(
        self,
        guild_id: int,
        event_id: int,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.modify_scheduled_event(guild_id, event_id, payload)

    async def delete_scheduled_event(self, guild_id: int, event_id: int) -> dict[str, Any]:
        return await self.api_client.delete_scheduled_event(guild_id, event_id)

    async def fetch_user(self, user_id: int) -> User:
        """Fetch and parse a user from the API."""
        data = await self.api_client.fetch_user(user_id)
        user = self._parse_user(data)
        self._users[user.id] = user
        return user

    async def get_current_user(self) -> User:
        """Get the current bot user via REST."""
        data = await self.api_client.get_current_user()
        user = self._parse_user(data)
        self._remember_bot_user(user)
        return user

    async def modify_current_user(self, **payload: Any) -> User:
        """Modify the current user settings (username/avatar/banner)."""
        data = await self.api_client.modify_current_user(payload)
        user = self._parse_user(data)
        self._remember_bot_user(user)
        return user

    async def get_current_user_guilds(self, **params: Any) -> list[Guild]:
        """Get current user guild list (/users/@me/guilds)."""
        data = await self.api_client.get_current_user_guilds(**params)
        guilds = [self._parse_guild(item) for item in data]
        for guild in guilds:
            self._guilds[guild.id] = guild
        return guilds

    async def get_current_user_guild_member(self, guild_id: int) -> dict[str, Any]:
        """Get current user guild member object for a guild."""
        return await self.api_client.get_current_user_guild_member(guild_id)

    async def leave_guild(self, guild_id: int) -> dict[str, Any]:
        """Leave a guild as current user."""
        result = await self.api_client.leave_guild(guild_id)
        self._guilds.pop(guild_id, None)
        return result

    async def create_group_dm(self, access_tokens: list[str], nicks: dict[str, str]) -> Channel:
        data = await self.api_client.create_group_dm(access_tokens, nicks)
        return self._parse_channel(data)

    async def get_current_user_connections(self) -> list[dict[str, Any]]:
        return await self.api_client.get_current_user_connections()

    async def get_current_user_application_role_connection(self, application_id: int) -> dict[str, Any]:
        return await self.api_client.get_current_user_application_role_connection(application_id)

    async def update_current_user_application_role_connection(
        self,
        application_id: int,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.update_current_user_application_role_connection(application_id, payload)

    async def fetch_invite(self, invite_code: str, **params: Any) -> dict[str, Any]:
        return await self.api_client.fetch_invite(invite_code, **params)

    async def delete_invite(self, invite_code: str) -> dict[str, Any]:
        return await self.api_client.delete_invite(invite_code)

    async def create_webhook(self, channel_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.create_webhook(channel_id, payload)

    async def list_channel_webhooks(self, channel_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_channel_webhooks(channel_id)

    async def list_guild_webhooks(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_webhooks(guild_id)

    async def execute_webhook(
        self,
        webhook_id: int,
        token: str,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.execute_webhook(webhook_id, token, payload)

    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.create_interaction_response(
            interaction_id,
            interaction_token,
            payload,
        )

    async def create_followup_message(
        self,
        application_id: int,
        interaction_token: str,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.create_followup_message(
            application_id,
            interaction_token,
            payload,
        )

    def run(self, *, drop_pending_updates: bool = False) -> None:
        """Run the bot (blocking)."""
        try:
            if drop_pending_updates:
                self.enable_drop_pending_updates()
            asyncio.run(self.start())
        except KeyboardInterrupt:
            pass

    def __repr__(self) -> str:
        return f"<Bot name='{self.name}' ready={self.is_ready}>"
