"""
Permissions module for VaidCord.

Implements Discord's permission system with bitwise operations,
permission overwrites, and role hierarchy calculations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntFlag
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import Channel, Guild, Member


class Permissions(IntFlag):
    """
    Discord permissions as bit flags.

    All permissions are stored as strings in the API but represented
    as integers here for bitwise operations.

    Based on Discord API documentation:
    https://discord.com/developers/docs/topics/permissions
    """

    # General permissions
    CREATE_INSTANT_INVITE = 1 << 0  # 0x0000000000000001
    KICK_MEMBERS = 1 << 1  # 0x0000000000000002 *
    BAN_MEMBERS = 1 << 2  # 0x0000000000000004 *
    ADMINISTRATOR = 1 << 3  # 0x0000000000000008 *
    MANAGE_CHANNELS = 1 << 4  # 0x0000000000000010 *
    MANAGE_GUILD = 1 << 5  # 0x0000000000000020 *
    ADD_REACTIONS = 1 << 6  # 0x0000000000000040
    VIEW_AUDIT_LOG = 1 << 7  # 0x0000000000000080
    PRIORITY_SPEAKER = 1 << 8  # 0x0000000000000100
    STREAM = 1 << 9  # 0x0000000000000200
    VIEW_CHANNEL = 1 << 10  # 0x0000000000000400
    SEND_MESSAGES = 1 << 11  # 0x0000000000000800
    SEND_TTS_MESSAGES = 1 << 12  # 0x0000000000001000
    MANAGE_MESSAGES = 1 << 13  # 0x0000000000002000 *
    EMBED_LINKS = 1 << 14  # 0x0000000000004000
    ATTACH_FILES = 1 << 15  # 0x0000000000008000
    READ_MESSAGE_HISTORY = 1 << 16  # 0x0000000000010000
    MENTION_EVERYONE = 1 << 17  # 0x0000000000020000
    USE_EXTERNAL_EMOJIS = 1 << 18  # 0x0000000000040000
    VIEW_GUILD_INSIGHTS = 1 << 19  # 0x0000000000080000
    CONNECT = 1 << 20  # 0x0000000000100000
    SPEAK = 1 << 21  # 0x0000000000200000
    MUTE_MEMBERS = 1 << 22  # 0x0000000000400000
    DEAFEN_MEMBERS = 1 << 23  # 0x0000000000800000
    MOVE_MEMBERS = 1 << 24  # 0x0000000001000000
    USE_VAD = 1 << 25  # 0x0000000002000000
    CHANGE_NICKNAME = 1 << 26  # 0x0000000004000000
    MANAGE_NICKNAMES = 1 << 27  # 0x0000000008000000
    MANAGE_ROLES = 1 << 28  # 0x0000000010000000 *
    MANAGE_WEBHOOKS = 1 << 29  # 0x0000000020000000 *
    MANAGE_GUILD_EXPRESSIONS = 1 << 30  # 0x0000000040000000 *
    USE_APPLICATION_COMMANDS = 1 << 31  # 0x0000000080000000
    REQUEST_TO_SPEAK = 1 << 32  # 0x0000000100000000
    MANAGE_EVENTS = 1 << 33  # 0x0000000200000000
    MANAGE_THREADS = 1 << 34  # 0x0000000400000000 *
    CREATE_PUBLIC_THREADS = 1 << 35  # 0x0000000800000000
    CREATE_PRIVATE_THREADS = 1 << 36  # 0x0000001000000000
    USE_EXTERNAL_STICKERS = 1 << 37  # 0x0000002000000000
    SEND_MESSAGES_IN_THREADS = 1 << 38  # 0x0000004000000000
    USE_EMBEDDED_ACTIVITIES = 1 << 39  # 0x0000008000000000
    MODERATE_MEMBERS = 1 << 40  # 0x0000010000000000 **
    VIEW_CREATOR_MONETIZATION_ANALYTICS = 1 << 41  # 0x0000020000000000 *
    USE_SOUNDBOARD = 1 << 42  # 0x0000040000000000
    CREATE_GUILD_EXPRESSIONS = 1 << 43  # 0x0000080000000000
    CREATE_EVENTS = 1 << 44  # 0x0000100000000000
    USE_EXTERNAL_SOUNDS = 1 << 45  # 0x0000200000000000
    SEND_VOICE_MESSAGES = 1 << 46  # 0x0000400000000000
    SET_VOICE_CHANNEL_STATUS = 1 << 48  # 0x0001000000000000
    SEND_POLLS = 1 << 49  # 0x0002000000000000
    USE_EXTERNAL_APPS = 1 << 50  # 0x0004000000000000
    PIN_MESSAGES = 1 << 51  # 0x0008000000000000
    BYPASS_SLOWMODE = 1 << 52  # 0x0010000000000000

    # Convenience properties
    @property
    def value(self) -> int:
        """Get the integer value of permissions."""
        return int(self)

    @classmethod
    def from_int(cls, value: int | str) -> Permissions:
        """Create Permissions from integer or string representation."""
        if isinstance(value, str):
            value = int(value)
        return cls(value)

    def to_int(self) -> int:
        """Convert permissions to integer."""
        return int(self)

    def to_string(self) -> str:
        """Convert permissions to string (for API serialization)."""
        return str(int(self))

    def has(self, other: Permissions) -> bool:
        """Check if this permission set has all of the specified permissions."""
        return (self & other) == other

    def add(self, other: Permissions) -> Permissions:
        """Add permissions to this set."""
        return self | other

    def remove(self, other: Permissions) -> Permissions:
        """Remove permissions from this set."""
        return self & ~other

    # Channel type specific permissions
    @property
    def text_channel_permissions(self) -> list[Permissions]:
        """Permissions that apply to text channels."""
        return [
            self.CREATE_INSTANT_INVITE,
            self.MANAGE_CHANNELS,
            self.ADD_REACTIONS,
            self.VIEW_CHANNEL,
            self.SEND_MESSAGES,
            self.SEND_TTS_MESSAGES,
            self.MANAGE_MESSAGES,
            self.EMBED_LINKS,
            self.ATTACH_FILES,
            self.READ_MESSAGE_HISTORY,
            self.MENTION_EVERYONE,
            self.USE_EXTERNAL_EMOJIS,
            self.USE_APPLICATION_COMMANDS,
            self.MANAGE_THREADS,
            self.CREATE_PUBLIC_THREADS,
            self.CREATE_PRIVATE_THREADS,
            self.USE_EXTERNAL_STICKERS,
            self.SEND_MESSAGES_IN_THREADS,
            self.USE_EMBEDDED_ACTIVITIES,
            self.MODERATE_MEMBERS,
            self.SEND_VOICE_MESSAGES,
            self.SEND_POLLS,
            self.USE_EXTERNAL_APPS,
            self.PIN_MESSAGES,
            self.BYPASS_SLOWMODE,
        ]

    @property
    def voice_channel_permissions(self) -> list[Permissions]:
        """Permissions that apply to voice channels."""
        return [
            self.CREATE_INSTANT_INVITE,
            self.MANAGE_CHANNELS,
            self.ADD_REACTIONS,
            self.VIEW_CHANNEL,
            self.SEND_MESSAGES,
            self.SEND_TTS_MESSAGES,
            self.MANAGE_MESSAGES,
            self.EMBED_LINKS,
            self.ATTACH_FILES,
            self.READ_MESSAGE_HISTORY,
            self.MENTION_EVERYONE,
            self.USE_EXTERNAL_EMOJIS,
            self.CONNECT,
            self.SPEAK,
            self.MUTE_MEMBERS,
            self.DEAFEN_MEMBERS,
            self.MOVE_MEMBERS,
            self.USE_VAD,
            self.USE_APPLICATION_COMMANDS,
            self.MANAGE_EVENTS,
            self.USE_EMBEDDED_ACTIVITIES,
            self.MODERATE_MEMBERS,
            self.USE_SOUNDBOARD,
            self.USE_EXTERNAL_SOUNDS,
            self.SEND_VOICE_MESSAGES,
            self.SET_VOICE_CHANNEL_STATUS,
            self.SEND_POLLS,
            self.USE_EXTERNAL_APPS,
            self.BYPASS_SLOWMODE,
        ]

    @property
    def stage_channel_permissions(self) -> list[Permissions]:
        """Permissions that apply to stage channels."""
        return [
            self.CREATE_INSTANT_INVITE,
            self.MANAGE_CHANNELS,
            self.ADD_REACTIONS,
            self.VIEW_CHANNEL,
            self.SEND_MESSAGES,
            self.SEND_TTS_MESSAGES,
            self.MANAGE_MESSAGES,
            self.EMBED_LINKS,
            self.ATTACH_FILES,
            self.READ_MESSAGE_HISTORY,
            self.MENTION_EVERYONE,
            self.USE_EXTERNAL_EMOJIS,
            self.STREAM,
            self.CONNECT,
            self.SPEAK,
            self.MUTE_MEMBERS,
            self.DEAFEN_MEMBERS,
            self.MOVE_MEMBERS,
            self.USE_VAD,
            self.REQUEST_TO_SPEAK,
            self.MANAGE_EVENTS,
            self.CREATE_EVENTS,
            self.USE_APPLICATION_COMMANDS,
            self.MODERATE_MEMBERS,
            self.USE_SOUNDBOARD,
            self.USE_EXTERNAL_SOUNDS,
            self.SEND_VOICE_MESSAGES,
            self.SEND_POLLS,
            self.USE_EXTERNAL_APPS,
            self.BYPASS_SLOWMODE,
        ]

    # Special permission groups
    @property
    def administrative_permissions(self) -> list[Permissions]:
        """Permissions that require 2FA on guilds with server-wide 2FA."""
        return [
            self.KICK_MEMBERS,
            self.BAN_MEMBERS,
            self.ADMINISTRATOR,
            self.MANAGE_CHANNELS,
            self.MANAGE_GUILD,
            self.MANAGE_MESSAGES,
            self.MANAGE_ROLES,
            self.MANAGE_WEBHOOKS,
            self.MANAGE_GUILD_EXPRESSIONS,
            self.MANAGE_THREADS,
            self.VIEW_CREATOR_MONETIZATION_ANALYTICS,
        ]

    @classmethod
    def all(cls) -> Permissions:
        """Get all permissions (administrator equivalent)."""
        # Include all defined permission bits
        all_perms = 0
        for perm in cls:
            all_perms |= perm.value
        return cls(all_perms)

    @classmethod
    def none(cls) -> Permissions:
        """Get no permissions."""
        return cls(0)

    @classmethod
    def default(cls) -> Permissions:
        """Get default permissions (same as @everyone role)."""
        # Default permissions that everyone has
        return cls(
            cls.CREATE_INSTANT_INVITE
            | cls.ADD_REACTIONS
            | cls.VIEW_CHANNEL
            | cls.SEND_MESSAGES
            | cls.SEND_TTS_MESSAGES
            | cls.EMBED_LINKS
            | cls.ATTACH_FILES
            | cls.READ_MESSAGE_HISTORY
            | cls.MENTION_EVERYONE
            | cls.USE_EXTERNAL_EMOJIS
            | cls.CONNECT
            | cls.SPEAK
            | cls.USE_VAD
            | cls.CHANGE_NICKNAME
            | cls.USE_APPLICATION_COMMANDS
            | cls.USE_EXTERNAL_STICKERS
            | cls.SEND_MESSAGES_IN_THREADS
            | cls.USE_EMBEDDED_ACTIVITIES
            | cls.CREATE_GUILD_EXPRESSIONS
            | cls.CREATE_EVENTS
            | cls.SEND_VOICE_MESSAGES
            | cls.SEND_POLLS
            | cls.USE_EXTERNAL_APPS
        )


@dataclass
class PermissionOverwrite:
    """
    Permission overwrite for a channel.

    Represents allow/deny pairs for channel-specific permissions.

    Attributes:
        id: ID of the role or member this overwrite applies to
        type: Type of overwrite (0=role, 1=member)
        allow: Permissions explicitly allowed
        deny: Permissions explicitly denied
    """

    id: int | str
    type: int  # 0 for role, 1 for member
    allow: Permissions = field(default_factory=Permissions.none)
    deny: Permissions = field(default_factory=Permissions.none)

    def __post_init__(self) -> None:
        """Ensure permissions are properly initialized."""
        if isinstance(self.id, str):
            self.id = int(self.id)
        if isinstance(self.allow, int):
            self.allow = Permissions.from_int(self.allow)
        if isinstance(self.deny, int):
            self.deny = Permissions.from_int(self.deny)

    @classmethod
    def from_dict(cls, data: dict) -> PermissionOverwrite:
        """Create a PermissionOverwrite from API data."""
        return cls(
            id=data["id"],
            type=data.get("type", 0),
            allow=Permissions.from_int(data.get("allow", 0)),
            deny=Permissions.from_int(data.get("deny", 0)),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for API requests."""
        return {
            "id": str(self.id),
            "type": self.type,
            "allow": self.allow.to_string(),
            "deny": self.deny.to_string(),
        }

    def set_allow(self, *permissions: Permissions) -> None:
        """Set specific permissions as allowed."""
        for perm in permissions:
            self.allow = self.allow.add(perm)
            self.deny = self.deny.remove(perm)

    def set_deny(self, *permissions: Permissions) -> None:
        """Set specific permissions as denied."""
        for perm in permissions:
            self.deny = self.deny.add(perm)
            self.allow = self.allow.remove(perm)

    def reset(self, *permissions: Permissions) -> None:
        """Reset specific permissions (neither allow nor deny)."""
        for perm in permissions:
            self.allow = self.allow.remove(perm)
            self.deny = self.deny.remove(perm)

    def __repr__(self) -> str:
        return f"<PermissionOverwrite id={self.id} type={self.type}>"


class PermissionCalculator:
    """
    Calculates effective permissions for members in various contexts.

    Implements Discord's permission hierarchy and overwrite logic.
    """

    @staticmethod
    def compute_base_permissions(member: Member, guild: Guild) -> Permissions:
        """
        Compute base permissions for a member at the guild level.

        Args:
            member: The member to compute permissions for
            guild: The guild containing the member

        Returns:
            Base permissions including role permissions
        """
        # Guild owner has all permissions
        if guild.is_owner(member):
            return Permissions.all()

        # Get @everyone role
        everyone_role = guild.get_role(guild.id)
        if everyone_role:
            permissions = Permissions.from_int(everyone_role.permissions)
        else:
            permissions = Permissions.default()

        # Add permissions from all member roles
        for role in member.roles:
            role_perms = Permissions.from_int(role.permissions)
            permissions = permissions.add(role_perms)

        # Administrator bypasses all checks
        if permissions.has(Permissions.ADMINISTRATOR):
            return Permissions.all()

        # Handle timed out members
        if member.is_timed_out():
            # Timed out members only keep VIEW_CHANNEL and READ_MESSAGE_HISTORY
            permissions = Permissions.none()
            permissions = permissions.add(Permissions.VIEW_CHANNEL)
            permissions = permissions.add(Permissions.READ_MESSAGE_HISTORY)

        return permissions

    @staticmethod
    def compute_overwrites(
        base_permissions: Permissions,
        member: Member,
        channel: Channel,
        guild_id: int | None = None,
    ) -> Permissions:
        """
        Apply permission overwrites to base permissions.

        Follows Discord's permission overwrite hierarchy:
        1. @everyone role overwrites (deny then allow)
        2. Role-specific overwrites (deny then allow)
        3. Member-specific overwrites (deny then allow)

        Args:
            base_permissions: Base permissions from roles
            member: The member to compute permissions for
            channel: The channel with overwrites

        Returns:
            Final permissions after applying overwrites
        """
        # ADMINISTRATOR bypasses overwrites
        if base_permissions.has(Permissions.ADMINISTRATOR):
            return Permissions.all()

        permissions = base_permissions

        # Get overwrites for this channel.
        # Discord API returns a list, but callers may already provide a mapping.
        raw_overwrites = channel.permission_overwrites or []
        overwrites = PermissionCalculator._normalize_overwrites(raw_overwrites)

        if guild_id is None:
            guild_id = getattr(channel, "guild_id", None)

        # Apply @everyone overwrite first
        everyone_overwrite = overwrites.get(guild_id) if guild_id is not None else None
        if everyone_overwrite:
            permissions = permissions.remove(everyone_overwrite.deny)
            permissions = permissions.add(everyone_overwrite.allow)

        # Collect role overwrites
        role_allow = Permissions.none()
        role_deny = Permissions.none()

        for role in member.roles:
            role_overwrite = overwrites.get(role.id)
            if role_overwrite:
                role_allow = role_allow.add(role_overwrite.allow)
                role_deny = role_deny.add(role_overwrite.deny)

        # Apply role overwrites (deny first, then allow)
        permissions = permissions.remove(role_deny)
        permissions = permissions.add(role_allow)

        # Apply member-specific overwrite last (highest priority)
        member_overwrite = overwrites.get(member.id)
        if member_overwrite:
            permissions = permissions.remove(member_overwrite.deny)
            permissions = permissions.add(member_overwrite.allow)

        return permissions

    @staticmethod
    def _normalize_overwrites(
        overwrites: list[dict] | dict[int, PermissionOverwrite],
    ) -> dict[int, PermissionOverwrite]:
        """Normalize overwrite payload into id -> PermissionOverwrite mapping."""
        if isinstance(overwrites, dict):
            return {
                int(overwrite_id): (
                    overwrite
                    if isinstance(overwrite, PermissionOverwrite)
                    else PermissionOverwrite.from_dict(overwrite)
                )
                for overwrite_id, overwrite in overwrites.items()
            }

        return {
            int(overwrite_data["id"]): (
                overwrite_data
                if isinstance(overwrite_data, PermissionOverwrite)
                else PermissionOverwrite.from_dict(overwrite_data)
            )
            for overwrite_data in overwrites
        }

    @staticmethod
    def compute_effective_permissions(
        member: Member,
        channel: Channel,
        guild: Guild | None = None,
    ) -> Permissions:
        """
        Compute the final effective permissions for a member in a channel.

        This is the main method to use for permission checks.

        Args:
            member: The member to check permissions for
            channel: The channel to check permissions in

        Returns:
            Effective permissions after all calculations
        """
        resolved_guild = guild or getattr(channel, "guild", None)
        if resolved_guild is None:
            raise ValueError(
                "Guild context is required to compute permissions. "
                "Pass guild explicitly or provide channel.guild."
            )

        base = PermissionCalculator.compute_base_permissions(member, resolved_guild)
        return PermissionCalculator.compute_overwrites(
            base,
            member,
            channel,
            guild_id=resolved_guild.id,
        )

    @staticmethod
    def can_send_messages(permissions: Permissions) -> bool:
        """
        Check if permissions implicitly allow sending messages.

        Denying SEND_MESSAGES implicitly denies related permissions.
        """
        if not permissions.has(Permissions.SEND_MESSAGES):
            return False
        return True

    @staticmethod
    def get_implicit_denied(permissions: Permissions) -> Permissions:
        """
        Get permissions that are implicitly denied based on logical rules.

        For example, denying VIEW_CHANNEL implicitly denies most other permissions.
        """
        implicit_deny = Permissions.none()

        # If can't view channel, most permissions are useless
        if not permissions.has(Permissions.VIEW_CHANNEL):
            implicit_deny = implicit_deny.add(
                Permissions.SEND_MESSAGES
                | Permissions.SEND_TTS_MESSAGES
                | Permissions.EMBED_LINKS
                | Permissions.ATTACH_FILES
                | Permissions.MENTION_EVERYONE
                | Permissions.USE_EXTERNAL_EMOJIS
                | Permissions.SEND_MESSAGES_IN_THREADS
                | Permissions.SEND_VOICE_MESSAGES
                | Permissions.SEND_POLLS
            )

        # If can't send messages, these are implicitly denied
        if not permissions.has(Permissions.SEND_MESSAGES):
            implicit_deny = implicit_deny.add(
                Permissions.MENTION_EVERYONE
                | Permissions.SEND_TTS_MESSAGES
                | Permissions.ATTACH_FILES
                | Permissions.EMBED_LINKS
            )

        # Voice channels: if can't connect, can't do voice stuff
        if not permissions.has(Permissions.CONNECT):
            implicit_deny = implicit_deny.add(
                Permissions.SPEAK
                | Permissions.MUTE_MEMBERS
                | Permissions.DEAFEN_MEMBERS
                | Permissions.MOVE_MEMBERS
                | Permissions.USE_VAD
                | Permissions.USE_SOUNDBOARD
                | Permissions.USE_EXTERNAL_SOUNDS
            )

        return implicit_deny


def calculate_permissions(
    member: Member,
    channel: Channel,
    guild: Guild | None = None,
) -> Permissions:
    """
    Convenience function to calculate effective permissions.

    Args:
        member: The member to calculate permissions for
        channel: The channel context

    Returns:
        Effective permissions
    """
    return PermissionCalculator.compute_effective_permissions(member, channel, guild=guild)


def check_permission(
    member: Member,
    channel: Channel,
    required: Permissions,
    guild: Guild | None = None,
) -> bool:
    """
    Check if a member has a specific permission in a channel.

    Args:
        member: The member to check
        channel: The channel context
        required: The required permission(s)

    Returns:
        True if member has all required permissions
    """
    effective = calculate_permissions(member, channel, guild=guild)
    return effective.has(required)
