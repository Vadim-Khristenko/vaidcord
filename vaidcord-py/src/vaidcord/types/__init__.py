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

    HELLO = "HELLO"
    READY = "READY"
    RESUMED = "RESUMED"
    RECONNECT = "RECONNECT"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_SESSION = "INVALID_SESSION"

    APPLICATION_COMMAND_PERMISSIONS_UPDATE = "APPLICATION_COMMAND_PERMISSIONS_UPDATE"

    AUTO_MODERATION_RULE_CREATE = "AUTO_MODERATION_RULE_CREATE"
    AUTO_MODERATION_RULE_UPDATE = "AUTO_MODERATION_RULE_UPDATE"
    AUTO_MODERATION_RULE_DELETE = "AUTO_MODERATION_RULE_DELETE"
    AUTO_MODERATION_ACTION_EXECUTION = "AUTO_MODERATION_ACTION_EXECUTION"

    CHANNEL_CREATE = "CHANNEL_CREATE"
    CHANNEL_UPDATE = "CHANNEL_UPDATE"
    CHANNEL_DELETE = "CHANNEL_DELETE"
    CHANNEL_INFO = "CHANNEL_INFO"
    CHANNEL_PINS_UPDATE = "CHANNEL_PINS_UPDATE"

    THREAD_CREATE = "THREAD_CREATE"
    THREAD_UPDATE = "THREAD_UPDATE"
    THREAD_DELETE = "THREAD_DELETE"
    THREAD_LIST_SYNC = "THREAD_LIST_SYNC"
    THREAD_MEMBER_UPDATE = "THREAD_MEMBER_UPDATE"
    THREAD_MEMBERS_UPDATE = "THREAD_MEMBERS_UPDATE"

    ENTITLEMENT_CREATE = "ENTITLEMENT_CREATE"
    ENTITLEMENT_UPDATE = "ENTITLEMENT_UPDATE"
    ENTITLEMENT_DELETE = "ENTITLEMENT_DELETE"

    GUILD_CREATE = "GUILD_CREATE"
    GUILD_UPDATE = "GUILD_UPDATE"
    GUILD_DELETE = "GUILD_DELETE"
    GUILD_AUDIT_LOG_ENTRY_CREATE = "GUILD_AUDIT_LOG_ENTRY_CREATE"
    GUILD_BAN_ADD = "GUILD_BAN_ADD"
    GUILD_BAN_REMOVE = "GUILD_BAN_REMOVE"
    GUILD_EMOJIS_UPDATE = "GUILD_EMOJIS_UPDATE"
    GUILD_STICKERS_UPDATE = "GUILD_STICKERS_UPDATE"
    GUILD_INTEGRATIONS_UPDATE = "GUILD_INTEGRATIONS_UPDATE"
    GUILD_MEMBER_ADD = "GUILD_MEMBER_ADD"
    GUILD_MEMBER_REMOVE = "GUILD_MEMBER_REMOVE"
    GUILD_MEMBER_UPDATE = "GUILD_MEMBER_UPDATE"
    GUILD_MEMBERS_CHUNK = "GUILD_MEMBERS_CHUNK"
    GUILD_ROLE_CREATE = "GUILD_ROLE_CREATE"
    GUILD_ROLE_UPDATE = "GUILD_ROLE_UPDATE"
    GUILD_ROLE_DELETE = "GUILD_ROLE_DELETE"
    GUILD_SCHEDULED_EVENT_CREATE = "GUILD_SCHEDULED_EVENT_CREATE"
    GUILD_SCHEDULED_EVENT_UPDATE = "GUILD_SCHEDULED_EVENT_UPDATE"
    GUILD_SCHEDULED_EVENT_DELETE = "GUILD_SCHEDULED_EVENT_DELETE"
    GUILD_SCHEDULED_EVENT_USER_ADD = "GUILD_SCHEDULED_EVENT_USER_ADD"
    GUILD_SCHEDULED_EVENT_USER_REMOVE = "GUILD_SCHEDULED_EVENT_USER_REMOVE"
    GUILD_SOUNDBOARD_SOUND_CREATE = "GUILD_SOUNDBOARD_SOUND_CREATE"
    GUILD_SOUNDBOARD_SOUND_UPDATE = "GUILD_SOUNDBOARD_SOUND_UPDATE"
    GUILD_SOUNDBOARD_SOUND_DELETE = "GUILD_SOUNDBOARD_SOUND_DELETE"
    GUILD_SOUNDBOARD_SOUNDS_UPDATE = "GUILD_SOUNDBOARD_SOUNDS_UPDATE"

    SOUNDBOARD_SOUNDS = "SOUNDBOARD_SOUNDS"

    INTEGRATION_CREATE = "INTEGRATION_CREATE"
    INTEGRATION_UPDATE = "INTEGRATION_UPDATE"
    INTEGRATION_DELETE = "INTEGRATION_DELETE"

    INTERACTION_CREATE = "INTERACTION_CREATE"
    INVITE_CREATE = "INVITE_CREATE"
    INVITE_DELETE = "INVITE_DELETE"

    MESSAGE_CREATE = "MESSAGE_CREATE"
    MESSAGE_UPDATE = "MESSAGE_UPDATE"
    MESSAGE_DELETE = "MESSAGE_DELETE"
    MESSAGE_DELETE_BULK = "MESSAGE_DELETE_BULK"
    MESSAGE_REACTION_ADD = "MESSAGE_REACTION_ADD"
    MESSAGE_REACTION_REMOVE = "MESSAGE_REACTION_REMOVE"
    MESSAGE_REACTION_REMOVE_ALL = "MESSAGE_REACTION_REMOVE_ALL"
    MESSAGE_REACTION_REMOVE_EMOJI = "MESSAGE_REACTION_REMOVE_EMOJI"

    PRESENCE_UPDATE = "PRESENCE_UPDATE"

    STAGE_INSTANCE_CREATE = "STAGE_INSTANCE_CREATE"
    STAGE_INSTANCE_UPDATE = "STAGE_INSTANCE_UPDATE"
    STAGE_INSTANCE_DELETE = "STAGE_INSTANCE_DELETE"

    SUBSCRIPTION_CREATE = "SUBSCRIPTION_CREATE"
    SUBSCRIPTION_UPDATE = "SUBSCRIPTION_UPDATE"
    SUBSCRIPTION_DELETE = "SUBSCRIPTION_DELETE"

    TYPING_START = "TYPING_START"
    USER_UPDATE = "USER_UPDATE"

    VOICE_CHANNEL_EFFECT_SEND = "VOICE_CHANNEL_EFFECT_SEND"
    VOICE_CHANNEL_START_TIME_UPDATE = "VOICE_CHANNEL_START_TIME_UPDATE"
    VOICE_CHANNEL_STATUS_UPDATE = "VOICE_CHANNEL_STATUS_UPDATE"
    VOICE_STATE_UPDATE = "VOICE_STATE_UPDATE"
    VOICE_SERVER_UPDATE = "VOICE_SERVER_UPDATE"

    WEBHOOKS_UPDATE = "WEBHOOKS_UPDATE"

    MESSAGE_POLL_VOTE_ADD = "MESSAGE_POLL_VOTE_ADD"
    MESSAGE_POLL_VOTE_REMOVE = "MESSAGE_POLL_VOTE_REMOVE"

    MEMBER_JOIN = "GUILD_MEMBER_ADD"
    MEMBER_LEAVE = "GUILD_MEMBER_REMOVE"
    REACTION_ADD = "MESSAGE_REACTION_ADD"
    REACTION_REMOVE = "MESSAGE_REACTION_REMOVE"


class WebhookEventType(Enum):
    """Discord outgoing webhook event types."""

    APPLICATION_AUTHORIZED = "APPLICATION_AUTHORIZED"
    APPLICATION_DEAUTHORIZED = "APPLICATION_DEAUTHORIZED"
    ENTITLEMENT_CREATE = "ENTITLEMENT_CREATE"
    ENTITLEMENT_UPDATE = "ENTITLEMENT_UPDATE"
    ENTITLEMENT_DELETE = "ENTITLEMENT_DELETE"
    QUEST_USER_ENROLLMENT = "QUEST_USER_ENROLLMENT"
    LOBBY_MESSAGE_CREATE = "LOBBY_MESSAGE_CREATE"
    LOBBY_MESSAGE_UPDATE = "LOBBY_MESSAGE_UPDATE"
    LOBBY_MESSAGE_DELETE = "LOBBY_MESSAGE_DELETE"
    GAME_DIRECT_MESSAGE_CREATE = "GAME_DIRECT_MESSAGE_CREATE"
    GAME_DIRECT_MESSAGE_UPDATE = "GAME_DIRECT_MESSAGE_UPDATE"
    GAME_DIRECT_MESSAGE_DELETE = "GAME_DIRECT_MESSAGE_DELETE"


class ChannelType(Enum):
    """Discord channel types."""

    TEXT = 0
    DM = 1
    VOICE = 2
    GROUP_DM = 3
    CATEGORY = 4
    ANNOUNCEMENT = 5
    ANNOUNCEMENT_THREAD = 10
    NEWS_THREAD = 10
    PUBLIC_THREAD = 11
    PRIVATE_THREAD = 12
    STAGE = 13
    DIRECTORY = 14
    FORUM = 15
    GUILD_MEDIA = 16
    MEDIA = 16

@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True)
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
    welcome_screen: dict[str, Any] | None = None
    nsfw_level: int | None = None
    stickers: list[dict[str, Any]] = field(default_factory=list)
    premium_progress_bar_enabled: bool | None = None
    safety_alerts_channel_id: int | None = None
    incidents_data: dict[str, Any] | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def mention(self) -> str:
        """Guilds cannot be mentioned, but this returns the name."""
        return self.name


@dataclass(frozen=True, slots=True)
class Channel:
    """Represents a Discord channel."""

    id: int
    type: ChannelType
    guild_id: int | None = None
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
    managed: bool | None = None
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
    total_message_sent: int | None = None
    available_tags: list[dict[str, Any]] = field(default_factory=list)
    applied_tags: list[int] = field(default_factory=list)
    default_reaction_emoji: dict[str, Any] | None = None
    default_thread_rate_limit_per_user: int | None = None
    default_sort_order: int | None = None
    default_forum_layout: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def mention(self) -> str:
        """Get the channel's mention string."""
        return f"<#{self.id}>"


@dataclass(frozen=True, slots=True)
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
    message_snapshots: list[dict[str, Any]] = field(default_factory=list)
    flags: int | None = None
    referenced_message: Message | None = None
    interaction_metadata: dict[str, Any] = field(default_factory=dict)
    interaction: dict[str, Any] = field(default_factory=dict)
    thread: Channel | None = None
    components: list[dict[str, Any]] = field(default_factory=list)
    sticker_items: list[dict[str, Any]] = field(default_factory=list)
    stickers: list[dict[str, Any]] = field(default_factory=list)
    position: int | None = None
    role_subscription_data: dict[str, Any] = field(default_factory=dict)
    resolved: dict[str, Any] = field(default_factory=dict)
    poll: dict[str, Any] | None = None
    call: dict[str, Any] | None = None
    shared_client_theme: dict[str, Any] | None = None
    guild: Guild | None = None
    member: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)
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

    async def edit(self, **payload: Any) -> Message:
        """Edit this message."""
        if self.bot is None:
            raise RuntimeError("Message is not bound to a bot instance")
        return await self.bot.edit_message(self.channel_id, self.id, **payload)

    async def delete(self) -> dict[str, Any]:
        """Delete this message."""
        if self.bot is None:
            raise RuntimeError("Message is not bound to a bot instance")
        return await self.bot.delete_message(self.channel_id, self.id)

    async def pin(self) -> dict[str, Any]:
        """Pin this message in its channel."""
        if self.bot is None:
            raise RuntimeError("Message is not bound to a bot instance")
        return await self.bot.pin_message(self.channel_id, self.id)

    async def unpin(self) -> dict[str, Any]:
        """Unpin this message in its channel."""
        if self.bot is None:
            raise RuntimeError("Message is not bound to a bot instance")
        return await self.bot.unpin_message(self.channel_id, self.id)

    async def add_reaction(self, emoji: str) -> dict[str, Any]:
        """React to this message."""
        if self.bot is None:
            raise RuntimeError("Message is not bound to a bot instance")
        return await self.bot.add_reaction(self.channel_id, self.id, emoji)


@dataclass(frozen=True, slots=True)
class Ready:
    """Typed payload for the Discord READY gateway event."""

    version: int | None = None
    user: User | None = None
    guilds: list[Guild] = field(default_factory=list)
    session_id: str | None = None
    resume_gateway_url: str | None = None
    shard: tuple[int, int] | None = None
    application: dict[str, Any] | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class Resume:
    """Typed payload for the Discord RESUMED gateway event."""

    session_id: str | None = None
    sequence: int | None = None
    replayed: bool = True
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class DeletedMessage:
    """Typed payload for MESSAGE_DELETE."""

    id: int
    channel_id: int
    guild_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class BulkDeletedMessages:
    """Typed payload for MESSAGE_DELETE_BULK."""

    ids: list[int]
    channel_id: int
    guild_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class Reaction:
    """Typed payload for message reaction gateway events."""

    user_id: int | None
    channel_id: int
    message_id: int
    guild_id: int | None = None
    member: dict[str, Any] | None = None
    emoji: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class TypingStart:
    """Typed payload for TYPING_START."""

    channel_id: int
    user_id: int
    timestamp: int
    guild_id: int | None = None
    member: dict[str, Any] | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class PollVote:
    """Typed payload for poll vote gateway events."""

    user_id: int
    channel_id: int
    message_id: int
    answer_id: int
    guild_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class MessagePin:
    """A channel pin entry returned by the modern channel pins endpoint."""

    pinned_at: datetime
    message: Message
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class RawGatewayEvent:
    """Fallback typed wrapper for gateway payloads without a dedicated model."""

    type: EventType | WebhookEventType
    data: dict[str, Any]
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

@dataclass
class Event:
    """
    Base event class for all Discord events.

    This is the foundation of the event system, similar to Aiogram's event handling.
    """

    type: EventType | WebhookEventType
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    shard_id: int | None = None
    event_id: str | None = None

    # Parsed objects (populated by the dispatcher)
    message: Message | None = None
    user: User | None = None
    guild: Guild | None = None
    channel: Channel | None = None
    context: dict[str, Any] = field(default_factory=dict)
    interaction: dict[str, Any] | None = None
    object: Any | None = None
    payload: Any | None = None
    ready: Ready | None = None
    resume: Resume | None = None
    deleted_message: DeletedMessage | None = None
    deleted_messages: BulkDeletedMessages | None = None
    reaction: Reaction | None = None
    typing: TypingStart | None = None
    poll_vote: PollVote | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)
    bot: Bot | None = field(default=None, repr=False, compare=False)

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
