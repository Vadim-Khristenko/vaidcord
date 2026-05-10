"""Gateway payload parser extracted from :class:`vaidcord.bot.Bot` (issue #32).

The :class:`EventParser` owns every ``_parse_*`` method that used to live
on Bot. It is not part of the public API; Bot keeps the original method
names (``_parse_message``, ``_parse_event``, etc.) as thin shims that
delegate here. The split exists because:

* Bot had grown to ~1700 lines mixing facade, gateway state, parsing,
  and resource wrappers; parsing alone was ~340 lines and the most
  performance-sensitive surface.
* Pulling parsing out makes the hot path easy to micro-benchmark and the
  helper methods unit-testable without booting a Bot.
* It keeps the Discord-payload-shape knowledge in one file so the rest
  of Bot only sees typed objects.

The parser deliberately holds *no* state of its own — every cache it
reads (``_users``, ``_channels``, ``_guilds``) and every config flag it
honours (``keep_raw_data``, ``share_raw_data``) is provided by the
:class:`EventParserHost` it was constructed with. That's typically a Bot,
but the same parser is reusable for tests, mock harnesses, or future
worker threads.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

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

if TYPE_CHECKING:
    pass


# Shared empty mapping; never allocate a fresh empty dict per parsed object
# when ``keep_raw_data`` is disabled.
_EMPTY_RAW: dict[str, Any] = {}


class EventParserHost(Protocol):
    """The slice of Bot that the parser needs to read."""

    _users: dict[int, User]
    _guilds: dict[int, Guild]
    _channels: dict[int, Channel]
    _session_id: str | None
    _sequence: int | None

    @property
    def config(self) -> Any:  # BotConfig — typed loosely to keep the protocol minimal
        ...


class EventParser:
    """Stateless parser bound to a host (typically the active Bot)."""

    __slots__ = ("_host",)

    def __init__(self, host: EventParserHost) -> None:
        self._host = host

    # ------------------------------------------------------------------ #
    # raw_data control                                                   #
    # ------------------------------------------------------------------ #

    def raw(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return the value to assign to ``raw_data=`` for a parsed model."""
        config = self._host.config
        if not config.keep_raw_data:
            return _EMPTY_RAW
        if config.share_raw_data:
            return data
        return dict(data)

    # ------------------------------------------------------------------ #
    # Top-level event parser                                             #
    # ------------------------------------------------------------------ #

    async def parse_event(self, event_type: EventType, data: dict[str, Any]) -> Event:
        """Parse raw event data into a typed Event object."""
        host = self._host
        event = Event(type=event_type, data=data, shard_id=host.config.shard_id)
        event.event_id = str(data.get("id") or data.get("event_id") or uuid.uuid4())
        event.raw_data = self.raw(data)
        event.bot = host  # type: ignore[assignment]
        if "interaction" in data:
            event.interaction = data.get("interaction")

        if event_type == EventType.READY:
            event.ready = self.parse_ready(data)
            event.user = event.ready.user
            event.payload = event.object = event.ready
        elif event_type == EventType.RESUMED:
            event.resume = Resume(
                session_id=host._session_id,
                sequence=host._sequence,
                raw_data=self.raw(data),
            )
            event.payload = event.object = event.resume
        elif event_type in {EventType.MESSAGE_CREATE, EventType.MESSAGE_UPDATE}:
            event.message = self.parse_message(data)
            event.user = event.message.author
            event.channel = event.message.channel
            event.guild = event.message.guild
            event.payload = event.object = event.message
        elif event_type == EventType.MESSAGE_DELETE:
            deleted = DeletedMessage(
                id=int(data["id"]),
                channel_id=int(data["channel_id"]),
                guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
                raw_data=self.raw(data),
            )
            event.deleted_message = deleted
            event.payload = event.object = deleted
        elif event_type == EventType.MESSAGE_DELETE_BULK:
            deleted_many = BulkDeletedMessages(
                ids=[int(item) for item in data.get("ids", [])],
                channel_id=int(data["channel_id"]),
                guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
                raw_data=self.raw(data),
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
                raw_data=self.raw(data),
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
                raw_data=self.raw(data),
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
                raw_data=self.raw(data),
            )
            event.poll_vote = poll_vote
            event.payload = event.object = poll_vote
        elif event_type in {EventType.GUILD_CREATE, EventType.GUILD_UPDATE, EventType.GUILD_DELETE}:
            event.guild = self.parse_guild(data)
            event.payload = event.object = event.guild
        elif event_type in {
            EventType.CHANNEL_CREATE,
            EventType.CHANNEL_UPDATE,
            EventType.CHANNEL_DELETE,
            EventType.THREAD_CREATE,
            EventType.THREAD_UPDATE,
            EventType.THREAD_DELETE,
        }:
            event.channel = self.parse_channel(data)
            event.payload = event.object = event.channel
        else:
            event.payload = event.object = RawGatewayEvent(
                type=event_type,
                data=self.raw(data),
                raw_data=self.raw(data),
            )

        if "user" in data:
            event.user = self.parse_user(data["user"])
        if "guild_id" in data:
            guild_id = int(data["guild_id"])
            event.guild = event.guild or host._guilds.get(guild_id)
        if "channel_id" in data and data.get("channel_id") is not None:
            channel_id = int(data["channel_id"])
            event.channel = event.channel or host._channels.get(channel_id)

        return event

    # ------------------------------------------------------------------ #
    # Per-resource parsers                                               #
    # ------------------------------------------------------------------ #

    def parse_ready(self, data: dict[str, Any]) -> Ready:
        shard_data = data.get("shard")
        shard = (int(shard_data[0]), int(shard_data[1])) if shard_data else None
        return Ready(
            version=data.get("v"),
            user=self.parse_user(data["user"]) if data.get("user") else None,
            guilds=[self.parse_guild(item) for item in data.get("guilds", [])],
            session_id=data.get("session_id"),
            resume_gateway_url=data.get("resume_gateway_url"),
            shard=shard,
            application=data.get("application"),
            raw_data=self.raw(data),
        )

    def parse_user(self, data: dict[str, Any]) -> User:
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

    def parse_guild(self, data: dict[str, Any]) -> Guild:
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
            raw_data=self.raw(data),
        )

    def parse_channel(self, data: dict[str, Any]) -> Channel:
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
            recipients=[self.parse_user(item) for item in data.get("recipients", [])],
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
            raw_data=self.raw(data),
        )

    def parse_message(self, data: dict[str, Any]) -> Message:
        host = self._host
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
        channel = host._channels.get(channel_id)
        if channel is None:
            default_type = ChannelType.TEXT if data.get("guild_id") else ChannelType.DM
            channel = Channel(
                id=channel_id,
                type=default_type,
                guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            )

        author_data = data.get("author") or {"id": "0", "username": "", "discriminator": "0"}
        author = self.parse_user(author_data)

        guild = None
        if "guild_id" in data:
            guild_id = int(data["guild_id"])
            guild = host._guilds.get(guild_id)

        mentions = [self.parse_user(u) for u in data.get("mentions", [])]
        mention_channels = [self.parse_channel(item) for item in data.get("mention_channels", [])]
        referenced_message = None
        if isinstance(data.get("referenced_message"), dict):
            referenced_message = self.parse_message(data["referenced_message"])
        thread = self.parse_channel(data["thread"]) if isinstance(data.get("thread"), dict) else None

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
            raw_data=self.raw(data),
            bot=host,  # type: ignore[arg-type]
        )

    def parse_message_pin(self, data: dict[str, Any]) -> MessagePin:
        pinned_at = datetime.fromisoformat(data["pinned_at"].replace("Z", "+00:00"))
        return MessagePin(
            pinned_at=pinned_at,
            message=self.parse_message(data["message"]),
            raw_data=self.raw(data),
        )


__all__ = ["EventParser", "EventParserHost"]
