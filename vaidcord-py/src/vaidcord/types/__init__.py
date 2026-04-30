"""
Core types for VaidCord.

This module defines the fundamental data structures used throughout the framework,
including events, messages, users, guilds, and channels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vaidcord.bot import Bot


class EventType(Enum):
    """Discord event types."""

    READY = "READY"
    MESSAGE_CREATE = "MESSAGE_CREATE"
    MESSAGE_UPDATE = "MESSAGE_UPDATE"
    MESSAGE_DELETE = "MESSAGE_DELETE"
    GUILD_CREATE = "GUILD_CREATE"
    GUILD_UPDATE = "GUILD_UPDATE"
    GUILD_DELETE = "GUILD_DELETE"
    CHANNEL_CREATE = "CHANNEL_CREATE"
    CHANNEL_UPDATE = "CHANNEL_UPDATE"
    CHANNEL_DELETE = "CHANNEL_DELETE"
    MEMBER_JOIN = "MEMBER_JOIN"
    MEMBER_LEAVE = "MEMBER_LEAVE"
    REACTION_ADD = "REACTION_ADD"
    REACTION_REMOVE = "REACTION_REMOVE"
    INTERACTION_CREATE = "INTERACTION_CREATE"


class ChannelType(Enum):
    """Discord channel types."""

    TEXT = 0
    DM = 1
    VOICE = 2
    GROUP_DM = 3
    CATEGORY = 4
    ANNOUNCEMENT = 5
    NEWS_THREAD = 10
    PUBLIC_THREAD = 11
    PRIVATE_THREAD = 12
    STAGE = 13
    DIRECTORY = 14
    FORUM = 15


@dataclass(frozen=True)
class User:
    """Represents a Discord user."""

    id: int
    username: str
    discriminator: str = "0"
    global_name: str | None = None
    bot: bool = False
    system: bool = False
    mfa_enabled: bool | None = None
    locale: str | None = None
    verified: bool | None = None
    email: str | None = None
    flags: int | None = None
    premium_type: int | None = None
    public_flags: int | None = None
    avatar: str | None = None
    banner: str | None = None
    accent_color: int | None = None
    avatar_decoration_data: dict[str, Any] | None = None
    collectibles: dict[str, Any] | None = None
    primary_guild: dict[str, Any] | None = None

    @property
    def mention(self) -> str:
        """Get the user's mention string."""
        return f"<@{self.id}>"

    @property
    def display_name(self) -> str:
        """Get the user's display name (global_name or username)."""
        return self.global_name or self.username

    def __str__(self) -> str:
        if self.discriminator != "0":
            return f"{self.username}#{self.discriminator}"
        return self.username


@dataclass(frozen=True)
class Guild:
    """Represents a Discord guild (server)."""

    id: int
    name: str
    icon: str | None = None
    icon_hash: str | None = None
    splash: str | None = None
    discovery_splash: str | None = None
    owner: bool = False
    owner_id: int | None = None
    permissions: str | None = None
    region: str | None = None
    afk_channel_id: int | None = None
    afk_timeout: int | None = None
    widget_enabled: bool | None = None
    widget_channel_id: int | None = None
    verification_level: int | None = None
    default_message_notifications: int | None = None
    explicit_content_filter: int | None = None
    roles: list[dict[str, Any]] = field(default_factory=list)
    emojis: list[dict[str, Any]] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    mfa_level: int | None = None
    application_id: int | None = None
    system_channel_id: int | None = None
    system_channel_flags: int | None = None
    rules_channel_id: int | None = None
    joined_at: str | None = None
    large: bool | None = None
    unavailable: bool | None = None
    member_count: int | None = None
    voice_states: list[dict[str, Any]] = field(default_factory=list)
    members: list[dict[str, Any]] = field(default_factory=list)
    channels: list[dict[str, Any]] = field(default_factory=list)
    threads: list[dict[str, Any]] = field(default_factory=list)
    presences: list[dict[str, Any]] = field(default_factory=list)
    max_presences: int | None = None
    max_members: int | None = None
    vanity_url_code: str | None = None
    description: str | None = None
    banner: str | None = None
    premium_tier: int | None = None
    premium_subscription_count: int | None = None
    preferred_locale: str | None = None
    public_updates_channel_id: int | None = None
    max_video_channel_users: int | None = None
    approximate_member_count: int | None = None
    approximate_presence_count: int | None = None

    @property
    def mention(self) -> str:
        """Guilds cannot be mentioned, but this returns the name."""
        return self.name


@dataclass(frozen=True)
class Channel:
    """Represents a Discord channel."""

    id: int
    type: ChannelType
    name: str | None = None
    position: int | None = None
    permission_overwrites: list[dict[str, Any]] = field(default_factory=list)
    topic: str | None = None
    nsfw: bool | None = None
    last_message_id: int | None = None
    bitrate: int | None = None
    user_limit: int | None = None
    rate_limit_per_user: int | None = None
    recipients: list[User] = field(default_factory=list)
    icon: str | None = None
    owner_id: int | None = None
    application_id: int | None = None
    parent_id: int | None = None
    last_pin_timestamp: str | None = None
    rtc_region: str | None = None
    video_quality_mode: int | None = None
    message_count: int | None = None
    member_count: int | None = None
    thread_metadata: dict[str, Any] = field(default_factory=dict)
    member: dict[str, Any] = field(default_factory=dict)
    default_auto_archive_duration: int | None = None
    permissions: str | None = None
    flags: int | None = None

    @property
    def mention(self) -> str:
        """Get the channel's mention string."""
        return f"<#{self.id}>"


@dataclass(frozen=True)
class Message:
    """Represents a Discord message."""

    id: int
    channel: Channel
    author: User
    content: str
    timestamp: datetime
    edited_timestamp: datetime | None = None
    tts: bool = False
    mention_everyone: bool = False
    mentions: list[User] = field(default_factory=list)
    mention_roles: list[int] = field(default_factory=list)
    mention_channels: list[Channel] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    embeds: list[dict[str, Any]] = field(default_factory=list)
    reactions: list[dict[str, Any]] = field(default_factory=list)
    nonce: int | str | None = None
    pinned: bool = False
    webhook_id: int | None = None
    type: int | None = None
    activity: dict[str, Any] = field(default_factory=dict)
    application: dict[str, Any] = field(default_factory=dict)
    application_id: int | None = None
    message_reference: dict[str, Any] = field(default_factory=dict)
    flags: int | None = None
    referenced_message: Message | None = None
    interaction: dict[str, Any] = field(default_factory=dict)
    thread: Channel | None = None
    components: list[dict[str, Any]] = field(default_factory=list)
    sticker_items: list[dict[str, Any]] = field(default_factory=list)
    stickers: list[dict[str, Any]] = field(default_factory=list)
    guild: Guild | None = None
    member: dict[str, Any] = field(default_factory=dict)
    bot: Bot | None = field(default=None, repr=False, compare=False)

    @property
    def guild_id(self) -> int | None:
        """Get the guild ID if this message is from a guild."""
        return self.guild.id if self.guild else None

    @property
    def channel_id(self) -> int:
        """Get the channel ID."""
        return self.channel.id

    @property
    def author_id(self) -> int:
        """Get the author's user ID."""
        return self.author.id

    async def reply(self, content: str, **kwargs: Any) -> Message:
        """Reply to this message using Discord message reference."""
        if self.bot is None:
            raise RuntimeError("Message is not bound to a bot instance")
        return await self.bot.reply(self.channel_id, self.id, content, **kwargs)

    async def answer(self, content: str, **kwargs: Any) -> Message:
        """Send a regular message to the same channel without reply reference."""
        if self.bot is None:
            raise RuntimeError("Message is not bound to a bot instance")
        return await self.bot.send_message(self.channel_id, content, **kwargs)


@dataclass
class Event:
    """
    Base event class for all Discord events.

    This is the foundation of the event system, similar to Aiogram's event handling.
    """

    type: EventType
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    shard_id: int | None = None

    # Parsed objects (populated by the dispatcher)
    message: Message | None = None
    user: User | None = None
    guild: Guild | None = None
    channel: Channel | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def is_message_event(self) -> bool:
        """Check if this is a message-related event."""
        return self.type in (
            EventType.MESSAGE_CREATE,
            EventType.MESSAGE_UPDATE,
            EventType.MESSAGE_DELETE,
        )

    def __repr__(self) -> str:
        return f"<Event type={self.type.value} timestamp={self.timestamp}>"
