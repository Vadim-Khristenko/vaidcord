"""Typed models for Discord REST API resources.

Each model follows the framework conventions established in
:mod:`vaidcord.types`:

* ``@dataclass(frozen=True, slots=True)`` value objects,
* a ``raw_data`` field carrying the original payload (excluded from
  ``repr``/equality),
* a ``from_payload`` classmethod that tolerantly parses a Discord API
  payload dictionary.

These models are optional conveniences — :class:`vaidcord.api_client.APIClient`
keeps returning plain dictionaries for backward compatibility, and callers can
upgrade payloads with ``Model.from_payload(data)`` when typed access helps.
"""

from __future__ import annotations

import dataclasses
import io
from dataclasses import dataclass, field
from typing import Any, BinaryIO


def _snowflake(value: Any) -> int | None:
    """Coerce an optional Discord snowflake (str or int) to ``int``."""
    if value is None:
        return None
    return int(value)


def _snowflake_list(values: Any) -> list[int]:
    """Coerce a list of snowflakes to ``list[int]``."""
    if not values:
        return []
    return [int(value) for value in values]


def _from_payload[T](cls: type[T], data: dict[str, Any], **overrides: Any) -> T:
    """Build ``cls`` from a Discord payload, keeping unknown keys in raw_data."""
    names = {f.name for f in dataclasses.fields(cls)} - {"raw_data"}  # type: ignore[arg-type]
    kwargs: dict[str, Any] = {name: data[name] for name in names if name in data}
    kwargs.update(overrides)
    return cls(raw_data=data, **kwargs)  # type: ignore[call-arg]


@dataclass(frozen=True, slots=True)
class Role:
    """A Discord guild role."""

    id: int
    name: str = ""
    color: int = 0
    hoist: bool = False
    icon: str | None = None
    unicode_emoji: str | None = None
    position: int = 0
    permissions: str = "0"
    managed: bool = False
    mentionable: bool = False
    tags: dict[str, Any] | None = None
    flags: int = 0
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def mention(self) -> str:
        return f"<@&{self.id}>"

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Role:
        return _from_payload(cls, data, id=int(data["id"]))


@dataclass(frozen=True, slots=True)
class Member:
    """A Discord guild member."""

    user: dict[str, Any] | None = None
    nick: str | None = None
    avatar: str | None = None
    banner: str | None = None
    roles: list[int] = field(default_factory=list)
    joined_at: str | None = None
    premium_since: str | None = None
    deaf: bool = False
    mute: bool = False
    flags: int = 0
    pending: bool = False
    permissions: str | None = None
    communication_disabled_until: str | None = None
    avatar_decoration_data: dict[str, Any] | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def user_id(self) -> int | None:
        if self.user is None or "id" not in self.user:
            return None
        return int(self.user["id"])

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Member:
        return _from_payload(cls, data, roles=_snowflake_list(data.get("roles")))


@dataclass(frozen=True, slots=True)
class Emoji:
    """A Discord custom emoji (guild or application scoped)."""

    id: int | None = None
    name: str | None = None
    roles: list[int] = field(default_factory=list)
    user: dict[str, Any] | None = None
    require_colons: bool | None = None
    managed: bool | None = None
    animated: bool | None = None
    available: bool | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def mention(self) -> str:
        if self.id is None:
            return self.name or ""
        prefix = "a" if self.animated else ""
        return f"<{prefix}:{self.name}:{self.id}>"

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Emoji:
        return _from_payload(
            cls,
            data,
            id=_snowflake(data.get("id")),
            roles=_snowflake_list(data.get("roles")),
        )


@dataclass(frozen=True, slots=True)
class Sticker:
    """A Discord sticker."""

    id: int
    name: str = ""
    description: str | None = None
    tags: str = ""
    type: int | None = None
    format_type: int | None = None
    pack_id: int | None = None
    available: bool | None = None
    guild_id: int | None = None
    user: dict[str, Any] | None = None
    sort_value: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Sticker:
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            pack_id=_snowflake(data.get("pack_id")),
            guild_id=_snowflake(data.get("guild_id")),
        )


@dataclass(frozen=True, slots=True)
class StickerPack:
    """A pack of standard Discord stickers."""

    id: int
    stickers: list[Sticker] = field(default_factory=list)
    name: str = ""
    sku_id: int | None = None
    cover_sticker_id: int | None = None
    description: str | None = None
    banner_asset_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> StickerPack:
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            sku_id=_snowflake(data.get("sku_id")),
            cover_sticker_id=_snowflake(data.get("cover_sticker_id")),
            banner_asset_id=_snowflake(data.get("banner_asset_id")),
            stickers=[Sticker.from_payload(s) for s in data.get("stickers", [])],
        )


@dataclass(frozen=True, slots=True)
class Attachment:
    """A message attachment as returned by the API."""

    id: int
    filename: str = ""
    title: str | None = None
    description: str | None = None
    content_type: str | None = None
    size: int = 0
    url: str = ""
    proxy_url: str = ""
    height: int | None = None
    width: int | None = None
    ephemeral: bool | None = None
    duration_secs: float | None = None
    waveform: str | None = None
    flags: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Attachment:
        return _from_payload(cls, data, id=int(data["id"]))


@dataclass(frozen=True, slots=True)
class Embed:
    """A message embed."""

    title: str | None = None
    type: str | None = None
    description: str | None = None
    url: str | None = None
    timestamp: str | None = None
    color: int | None = None
    footer: dict[str, Any] | None = None
    image: dict[str, Any] | None = None
    thumbnail: dict[str, Any] | None = None
    video: dict[str, Any] | None = None
    provider: dict[str, Any] | None = None
    author: dict[str, Any] | None = None
    fields: list[dict[str, Any]] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Embed:
        return _from_payload(cls, data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to a Discord embed payload (omits ``None`` values)."""
        payload: dict[str, Any] = {}
        for name in (
            "title",
            "type",
            "description",
            "url",
            "timestamp",
            "color",
            "footer",
            "image",
            "thumbnail",
            "video",
            "provider",
            "author",
        ):
            value = getattr(self, name)
            if value is not None:
                payload[name] = value
        if self.fields:
            payload["fields"] = list(self.fields)
        return payload


class EmbedBuilder:
    """Fluent builder producing embed payload dictionaries.

    Example::

        embed = (
            EmbedBuilder()
            .set_title("Release 1.0")
            .set_description("Changelog...")
            .set_color(0x5865F2)
            .add_field("Downloads", "42", inline=True)
            .to_dict()
        )
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def set_title(self, title: str) -> EmbedBuilder:
        self._data["title"] = title
        return self

    def set_description(self, description: str) -> EmbedBuilder:
        self._data["description"] = description
        return self

    def set_url(self, url: str) -> EmbedBuilder:
        self._data["url"] = url
        return self

    def set_color(self, color: int) -> EmbedBuilder:
        self._data["color"] = color
        return self

    def set_timestamp(self, timestamp: str) -> EmbedBuilder:
        """Set an ISO8601 timestamp string."""
        self._data["timestamp"] = timestamp
        return self

    def set_footer(self, text: str, *, icon_url: str | None = None) -> EmbedBuilder:
        footer: dict[str, Any] = {"text": text}
        if icon_url is not None:
            footer["icon_url"] = icon_url
        self._data["footer"] = footer
        return self

    def set_image(self, url: str) -> EmbedBuilder:
        self._data["image"] = {"url": url}
        return self

    def set_thumbnail(self, url: str) -> EmbedBuilder:
        self._data["thumbnail"] = {"url": url}
        return self

    def set_author(
        self,
        name: str,
        *,
        url: str | None = None,
        icon_url: str | None = None,
    ) -> EmbedBuilder:
        author: dict[str, Any] = {"name": name}
        if url is not None:
            author["url"] = url
        if icon_url is not None:
            author["icon_url"] = icon_url
        self._data["author"] = author
        return self

    def add_field(self, name: str, value: str, *, inline: bool = False) -> EmbedBuilder:
        self._data.setdefault("fields", []).append(
            {"name": name, "value": value, "inline": inline}
        )
        return self

    def to_dict(self) -> dict[str, Any]:
        """Return the embed payload dictionary (deep-enough copy for reuse)."""
        payload = dict(self._data)
        if "fields" in payload:
            payload["fields"] = [dict(f) for f in payload["fields"]]
        return payload

    def build(self) -> Embed:
        """Return a frozen :class:`Embed` for the current builder state."""
        return Embed.from_payload(self.to_dict())


@dataclass(frozen=True, slots=True)
class Webhook:
    """A Discord webhook."""

    id: int
    type: int | None = None
    guild_id: int | None = None
    channel_id: int | None = None
    user: dict[str, Any] | None = None
    name: str | None = None
    avatar: str | None = None
    token: str | None = None
    application_id: int | None = None
    source_guild: dict[str, Any] | None = None
    source_channel: dict[str, Any] | None = None
    url: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Webhook:
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            guild_id=_snowflake(data.get("guild_id")),
            channel_id=_snowflake(data.get("channel_id")),
            application_id=_snowflake(data.get("application_id")),
        )


@dataclass(frozen=True, slots=True)
class Invite:
    """A Discord invite (optionally with metadata fields)."""

    code: str
    type: int | None = None
    guild: dict[str, Any] | None = None
    channel: dict[str, Any] | None = None
    inviter: dict[str, Any] | None = None
    target_type: int | None = None
    target_user: dict[str, Any] | None = None
    target_application: dict[str, Any] | None = None
    approximate_presence_count: int | None = None
    approximate_member_count: int | None = None
    expires_at: str | None = None
    guild_scheduled_event: dict[str, Any] | None = None
    uses: int | None = None
    max_uses: int | None = None
    max_age: int | None = None
    temporary: bool | None = None
    created_at: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Invite:
        return _from_payload(cls, data)


@dataclass(frozen=True, slots=True)
class ThreadMember:
    """A thread member entry."""

    id: int | None = None
    user_id: int | None = None
    join_timestamp: str | None = None
    flags: int = 0
    member: Member | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> ThreadMember:
        member = data.get("member")
        return _from_payload(
            cls,
            data,
            id=_snowflake(data.get("id")),
            user_id=_snowflake(data.get("user_id")),
            member=Member.from_payload(member) if member is not None else None,
        )


@dataclass(frozen=True, slots=True)
class StageInstance:
    """A stage instance."""

    id: int
    guild_id: int | None = None
    channel_id: int | None = None
    topic: str = ""
    privacy_level: int | None = None
    discoverable_disabled: bool | None = None
    guild_scheduled_event_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> StageInstance:
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            guild_id=_snowflake(data.get("guild_id")),
            channel_id=_snowflake(data.get("channel_id")),
            guild_scheduled_event_id=_snowflake(data.get("guild_scheduled_event_id")),
        )


@dataclass(frozen=True, slots=True)
class AutoModerationRule:
    """An auto-moderation rule."""

    id: int
    guild_id: int | None = None
    name: str = ""
    creator_id: int | None = None
    event_type: int | None = None
    trigger_type: int | None = None
    trigger_metadata: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    enabled: bool = False
    exempt_roles: list[int] = field(default_factory=list)
    exempt_channels: list[int] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> AutoModerationRule:
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            guild_id=_snowflake(data.get("guild_id")),
            creator_id=_snowflake(data.get("creator_id")),
            exempt_roles=_snowflake_list(data.get("exempt_roles")),
            exempt_channels=_snowflake_list(data.get("exempt_channels")),
        )


@dataclass(frozen=True, slots=True)
class GuildScheduledEvent:
    """A guild scheduled event."""

    id: int
    guild_id: int | None = None
    channel_id: int | None = None
    creator_id: int | None = None
    name: str = ""
    description: str | None = None
    scheduled_start_time: str | None = None
    scheduled_end_time: str | None = None
    privacy_level: int | None = None
    status: int | None = None
    entity_type: int | None = None
    entity_id: int | None = None
    entity_metadata: dict[str, Any] | None = None
    creator: dict[str, Any] | None = None
    user_count: int | None = None
    image: str | None = None
    recurrence_rule: dict[str, Any] | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> GuildScheduledEvent:
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            guild_id=_snowflake(data.get("guild_id")),
            channel_id=_snowflake(data.get("channel_id")),
            creator_id=_snowflake(data.get("creator_id")),
            entity_id=_snowflake(data.get("entity_id")),
        )


@dataclass(frozen=True, slots=True)
class Entitlement:
    """A premium entitlement."""

    id: int
    sku_id: int | None = None
    application_id: int | None = None
    user_id: int | None = None
    guild_id: int | None = None
    type: int | None = None
    deleted: bool = False
    consumed: bool | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Entitlement:
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            sku_id=_snowflake(data.get("sku_id")),
            application_id=_snowflake(data.get("application_id")),
            user_id=_snowflake(data.get("user_id")),
            guild_id=_snowflake(data.get("guild_id")),
        )


@dataclass(frozen=True, slots=True)
class SKU:
    """A monetization SKU."""

    id: int
    type: int | None = None
    application_id: int | None = None
    name: str = ""
    slug: str = ""
    flags: int = 0
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> SKU:
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            application_id=_snowflake(data.get("application_id")),
        )


@dataclass(frozen=True, slots=True)
class Subscription:
    """A premium subscription for one or more SKUs."""

    id: int
    user_id: int | None = None
    sku_ids: list[int] = field(default_factory=list)
    entitlement_ids: list[int] = field(default_factory=list)
    renewal_sku_ids: list[int] | None = None
    current_period_start: str | None = None
    current_period_end: str | None = None
    status: int | None = None
    canceled_at: str | None = None
    country: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Subscription:
        renewal = data.get("renewal_sku_ids")
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            user_id=_snowflake(data.get("user_id")),
            sku_ids=_snowflake_list(data.get("sku_ids")),
            entitlement_ids=_snowflake_list(data.get("entitlement_ids")),
            renewal_sku_ids=_snowflake_list(renewal) if renewal is not None else None,
        )


@dataclass(frozen=True, slots=True)
class SoundboardSound:
    """A soundboard sound."""

    sound_id: int
    name: str = ""
    volume: float = 1.0
    emoji_id: int | None = None
    emoji_name: str | None = None
    guild_id: int | None = None
    available: bool = True
    user: dict[str, Any] | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> SoundboardSound:
        return _from_payload(
            cls,
            data,
            sound_id=int(data["sound_id"]),
            emoji_id=_snowflake(data.get("emoji_id")),
            guild_id=_snowflake(data.get("guild_id")),
        )


@dataclass(frozen=True, slots=True)
class AuditLogEntry:
    """One entry from a guild audit log."""

    id: int
    action_type: int | None = None
    target_id: int | None = None
    user_id: int | None = None
    changes: list[dict[str, Any]] = field(default_factory=list)
    options: dict[str, Any] | None = None
    reason: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> AuditLogEntry:
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            target_id=_snowflake(data.get("target_id")),
            user_id=_snowflake(data.get("user_id")),
        )


@dataclass(frozen=True, slots=True)
class AuditLog:
    """The audit log response object for a guild."""

    audit_log_entries: list[AuditLogEntry] = field(default_factory=list)
    application_commands: list[dict[str, Any]] = field(default_factory=list)
    auto_moderation_rules: list[AutoModerationRule] = field(default_factory=list)
    guild_scheduled_events: list[GuildScheduledEvent] = field(default_factory=list)
    integrations: list[dict[str, Any]] = field(default_factory=list)
    threads: list[dict[str, Any]] = field(default_factory=list)
    users: list[dict[str, Any]] = field(default_factory=list)
    webhooks: list[dict[str, Any]] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> AuditLog:
        return _from_payload(
            cls,
            data,
            audit_log_entries=[
                AuditLogEntry.from_payload(entry)
                for entry in data.get("audit_log_entries", [])
            ],
            auto_moderation_rules=[
                AutoModerationRule.from_payload(rule)
                for rule in data.get("auto_moderation_rules", [])
            ],
            guild_scheduled_events=[
                GuildScheduledEvent.from_payload(event)
                for event in data.get("guild_scheduled_events", [])
            ],
        )


@dataclass(frozen=True, slots=True)
class VoiceRegion:
    """A voice region."""

    id: str
    name: str = ""
    optimal: bool = False
    deprecated: bool = False
    custom: bool = False
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> VoiceRegion:
        return _from_payload(cls, data)


@dataclass(frozen=True, slots=True)
class Application:
    """A Discord application (as returned by ``GET /applications/@me``)."""

    id: int
    name: str = ""
    icon: str | None = None
    description: str = ""
    rpc_origins: list[str] | None = None
    bot_public: bool | None = None
    bot_require_code_grant: bool | None = None
    bot: dict[str, Any] | None = None
    terms_of_service_url: str | None = None
    privacy_policy_url: str | None = None
    owner: dict[str, Any] | None = None
    verify_key: str | None = None
    team: dict[str, Any] | None = None
    guild_id: int | None = None
    guild: dict[str, Any] | None = None
    primary_sku_id: int | None = None
    slug: str | None = None
    cover_image: str | None = None
    flags: int | None = None
    approximate_guild_count: int | None = None
    approximate_user_install_count: int | None = None
    redirect_uris: list[str] | None = None
    interactions_endpoint_url: str | None = None
    role_connections_verification_url: str | None = None
    event_webhooks_url: str | None = None
    event_webhooks_status: int | None = None
    event_webhooks_types: list[str] | None = None
    tags: list[str] | None = None
    install_params: dict[str, Any] | None = None
    integration_types_config: dict[str, Any] | None = None
    custom_install_url: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Application:
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            guild_id=_snowflake(data.get("guild_id")),
            primary_sku_id=_snowflake(data.get("primary_sku_id")),
        )


@dataclass(frozen=True, slots=True)
class Integration:
    """A guild integration."""

    id: int
    name: str = ""
    type: str = ""
    enabled: bool = False
    syncing: bool | None = None
    role_id: int | None = None
    enable_emoticons: bool | None = None
    expire_behavior: int | None = None
    expire_grace_period: int | None = None
    user: dict[str, Any] | None = None
    account: dict[str, Any] | None = None
    synced_at: str | None = None
    subscriber_count: int | None = None
    revoked: bool | None = None
    application: dict[str, Any] | None = None
    scopes: list[str] | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Integration:
        return _from_payload(
            cls,
            data,
            id=int(data["id"]),
            role_id=_snowflake(data.get("role_id")),
        )


@dataclass(frozen=True, slots=True)
class WelcomeScreen:
    """A guild welcome screen."""

    description: str | None = None
    welcome_channels: list[dict[str, Any]] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> WelcomeScreen:
        return _from_payload(cls, data)


@dataclass(frozen=True, slots=True)
class PollAnswer:
    """One answer of a poll."""

    answer_id: int | None = None
    poll_media: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> PollAnswer:
        return _from_payload(cls, data)


@dataclass(frozen=True, slots=True)
class Poll:
    """A message poll."""

    question: dict[str, Any] = field(default_factory=dict)
    answers: list[PollAnswer] = field(default_factory=list)
    expiry: str | None = None
    allow_multiselect: bool = False
    layout_type: int | None = None
    results: dict[str, Any] | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Poll:
        return _from_payload(
            cls,
            data,
            answers=[PollAnswer.from_payload(a) for a in data.get("answers", [])],
        )


@dataclass(frozen=True, slots=True)
class AttachmentFile:
    """A file to upload alongside a JSON payload (multipart/form-data).

    Used with the ``files=[...]`` keyword of
    :meth:`vaidcord.api_client.APIClient.send_message` and related helpers.

    ``data`` may be raw ``bytes`` or a binary file-like object.
    """

    filename: str
    data: bytes | BinaryIO
    description: str | None = None
    spoiler: bool = False
    content_type: str = "application/octet-stream"

    @property
    def upload_filename(self) -> str:
        """The filename sent to Discord (``SPOILER_`` prefixed if spoiler)."""
        if self.spoiler and not self.filename.startswith("SPOILER_"):
            return f"SPOILER_{self.filename}"
        return self.filename

    def read_bytes(self) -> bytes:
        """Return the file content as bytes (reads file-like objects once)."""
        if isinstance(self.data, bytes):
            return self.data
        if isinstance(self.data, io.IOBase) or hasattr(self.data, "read"):
            return self.data.read()
        raise TypeError(f"Unsupported attachment data type: {type(self.data)!r}")


__all__ = [
    "SKU",
    "Application",
    "Attachment",
    "AttachmentFile",
    "AuditLog",
    "AuditLogEntry",
    "AutoModerationRule",
    "Embed",
    "EmbedBuilder",
    "Emoji",
    "Entitlement",
    "GuildScheduledEvent",
    "Integration",
    "Invite",
    "Member",
    "Poll",
    "PollAnswer",
    "Role",
    "SoundboardSound",
    "StageInstance",
    "Sticker",
    "StickerPack",
    "Subscription",
    "ThreadMember",
    "VoiceRegion",
    "Webhook",
    "WelcomeScreen",
]
