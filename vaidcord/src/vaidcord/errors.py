"""
Comprehensive error handling for VaidCord.

This module provides detailed error classes that match Discord's API error codes,
Gateway opcodes and close codes, Voice close codes, and HTTP status codes.
All errors are designed to be informative and help with debugging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ============================================================================
# Gateway Opcodes
# ============================================================================


class GatewayOpcode(Enum):
    """Discord Gateway Opcodes."""

    DISPATCH = 0  # Receive: An event was dispatched
    HEARTBEAT = 1  # Send/Receive: Fired periodically to keep connection alive
    IDENTIFY = 2  # Send: Starts a new session during initial handshake
    PRESENCE_UPDATE = 3  # Send: Update the client's presence
    VOICE_STATE_UPDATE = 4  # Send: Used to join/leave or move between voice channels
    RESUME = 6  # Send: Resume a previous session
    RECONNECT = 7  # Receive: You should attempt to reconnect and resume immediately
    REQUEST_GUILD_MEMBERS = 8  # Send: Request information about offline guild members
    INVALID_SESSION = 9  # Receive: Session has been invalidated
    HELLO = (
        10  # Receive: Sent immediately after connecting, contains heartbeat_interval
    )
    HEARTBEAT_ACK = 11  # Receive: Sent in response to receiving a heartbeat
    REQUEST_SOUNDBOARD_SOUNDS = 31  # Send: Request soundboard sounds
    REQUEST_CHANNEL_INFO = 43  # Send: Request ephemeral channel data


# ============================================================================
# Gateway Close Event Codes
# ============================================================================


class GatewayCloseCode(Enum):
    """Discord Gateway Close Event Codes."""

    UNKNOWN_ERROR = 4000
    UNKNOWN_OPCODE = 4001
    DECODE_ERROR = 4002
    NOT_AUTHENTICATED = 4003
    AUTHENTICATION_FAILED = 4004
    ALREADY_AUTHENTICATED = 4005
    INVALID_SEQ = 4007
    RATE_LIMITED = 4008
    SESSION_TIMED_OUT = 4009
    INVALID_SHARD = 4010
    SHARDING_REQUIRED = 4011
    INVALID_API_VERSION = 4012
    INVALID_INTENT = 4013
    DISALLOWED_INTENT = 4014

    @property
    def should_reconnect(self) -> bool:
        """Whether the client should attempt to reconnect."""
        # Codes that should NOT reconnect
        no_reconnect_codes = {
            GatewayCloseCode.AUTHENTICATION_FAILED,
            GatewayCloseCode.INVALID_SHARD,
            GatewayCloseCode.SHARDING_REQUIRED,
            GatewayCloseCode.INVALID_API_VERSION,
            GatewayCloseCode.INVALID_INTENT,
            GatewayCloseCode.DISALLOWED_INTENT,
        }
        return self not in no_reconnect_codes

    @property
    def description(self) -> str:
        """Human-readable description of the close code."""
        descriptions = {
            GatewayCloseCode.UNKNOWN_ERROR: "Unknown error. Try reconnecting?",
            GatewayCloseCode.UNKNOWN_OPCODE: "You sent an invalid Gateway opcode or payload.",
            GatewayCloseCode.DECODE_ERROR: "You sent an invalid payload to Discord.",
            GatewayCloseCode.NOT_AUTHENTICATED: "You sent a payload prior to identifying.",
            GatewayCloseCode.AUTHENTICATION_FAILED: "The account token sent is incorrect.",
            GatewayCloseCode.ALREADY_AUTHENTICATED: "You sent more than one identify payload.",
            GatewayCloseCode.INVALID_SEQ: "The sequence sent when resuming was invalid.",
            GatewayCloseCode.RATE_LIMITED: "You're sending payloads too quickly.",
            GatewayCloseCode.SESSION_TIMED_OUT: "Your session timed out.",
            GatewayCloseCode.INVALID_SHARD: "You sent an invalid shard when identifying.",
            GatewayCloseCode.SHARDING_REQUIRED: "The session would have handled too many guilds.",
            GatewayCloseCode.INVALID_API_VERSION: "You sent an invalid version for the gateway.",
            GatewayCloseCode.INVALID_INTENT: "You sent an invalid intent for a Gateway Intent.",
            GatewayCloseCode.DISALLOWED_INTENT: "You sent a disallowed intent.",
        }
        return descriptions.get(self, "Unknown close code")


# ============================================================================
# Voice Gateway Opcodes
# ============================================================================


class VoiceGatewayOpcode(Enum):
    """Discord Voice Gateway Opcodes."""

    IDENTIFY = 0  # Client: Begin a voice websocket connection
    SELECT_PROTOCOL = 1  # Client: Select the voice protocol
    READY = 2  # Server: Complete the websocket handshake
    HEARTBEAT = 3  # Client: Keep the websocket connection alive
    SESSION_DESCRIPTION = 4  # Server: Describe the session
    SPEAKING = 5  # Client and Server: Indicate which users are speaking
    HEARTBEAT_ACK = 6  # Server: Acknowledge received client heartbeat
    RESUME = 7  # Client: Resume a connection
    HELLO = 8  # Server: Time to wait between sending heartbeats
    RESUMED = 9  # Server: Acknowledge successful session resume
    CLIENTS_CONNECT = 11  # Server: One or more clients have connected
    CLIENT_DISCONNECT = 13  # Server: A client has disconnected
    DAVE_PREPARE_TRANSITION = 21  # Server: Downgrade from DAVE protocol upcoming
    DAVE_EXECUTE_TRANSITION = 22  # Server: Execute protocol transition
    DAVE_TRANSITION_READY = 23  # Client: Acknowledge readiness
    DAVE_PREPARE_EPOCH = 24  # Server: DAVE protocol version change upcoming
    DAVE_MLS_EXTERNAL_SENDER = 25  # Server: MLS external sender credential
    DAVE_MLS_KEY_PACKAGE = 26  # Client: MLS Key Package for pending member
    DAVE_MLS_PROPOSALS = 27  # Server: MLS Proposals to append/revoke
    DAVE_MLS_COMMIT_WELCOME = 28  # Client: MLS Commit with Welcome messages
    DAVE_MLS_ANNOUNCE_COMMIT_TRANSITION = 29  # Server: MLS Commit for transition
    DAVE_MLS_WELCOME = 30  # Server: MLS Welcome to group
    DAVE_MLS_INVALID_COMMIT_WELCOME = 31  # Client: Flag invalid commit/welcome


# ============================================================================
# Voice Gateway Close Event Codes
# ============================================================================


class VoiceGatewayCloseCode(Enum):
    """Discord Voice Gateway Close Event Codes."""

    UNKNOWN_OPCODE = 4001
    DECODE_ERROR = 4002
    NOT_AUTHENTICATED = 4003
    AUTHENTICATION_FAILED = 4004
    ALREADY_AUTHENTICATED = 4005
    SESSION_NO_LONGER_VALID = 4006
    SESSION_TIMEOUT = 4009
    SERVER_NOT_FOUND = 4011
    UNKNOWN_PROTOCOL = 4012
    DISCONNECTED = 4014
    VOICE_SERVER_CRASHED = 4015
    UNKNOWN_ENCRYPTION_MODE = 4016
    E2EE_DAVE_REQUIRED = 4017
    BAD_REQUEST = 4020
    DISCONNECTED_RATE_LIMITED = 4021
    DISCONNECTED_CALL_TERMINATED = 4022

    @property
    def should_reconnect(self) -> bool:
        """Whether the client should attempt to reconnect."""
        no_reconnect_codes = {
            VoiceGatewayCloseCode.DISCONNECTED,
            VoiceGatewayCloseCode.DISCONNECTED_RATE_LIMITED,
            VoiceGatewayCloseCode.DISCONNECTED_CALL_TERMINATED,
        }
        return self not in no_reconnect_codes

    @property
    def description(self) -> str:
        """Human-readable description."""
        descriptions = {
            VoiceGatewayCloseCode.UNKNOWN_OPCODE: "You sent an invalid opcode.",
            VoiceGatewayCloseCode.DECODE_ERROR: "You sent an invalid payload.",
            VoiceGatewayCloseCode.NOT_AUTHENTICATED: "You sent a payload before identifying.",
            VoiceGatewayCloseCode.AUTHENTICATION_FAILED: "The token is incorrect.",
            VoiceGatewayCloseCode.ALREADY_AUTHENTICATED: "You sent more than one identify payload.",
            VoiceGatewayCloseCode.SESSION_NO_LONGER_VALID: "Your session is no longer valid.",
            VoiceGatewayCloseCode.SESSION_TIMEOUT: "Your session has timed out.",
            VoiceGatewayCloseCode.SERVER_NOT_FOUND: "We can't find the server you're trying to connect to.",
            VoiceGatewayCloseCode.UNKNOWN_PROTOCOL: "We didn't recognize your protocol.",
            VoiceGatewayCloseCode.DISCONNECTED: "You were kicked or the main gateway dropped.",
            VoiceGatewayCloseCode.VOICE_SERVER_CRASHED: "The server crashed. Try resuming.",
            VoiceGatewayCloseCode.UNKNOWN_ENCRYPTION_MODE: "We didn't recognize your encryption.",
            VoiceGatewayCloseCode.E2EE_DAVE_REQUIRED: "This channel requires E2EE via DAVE Protocol.",
            VoiceGatewayCloseCode.BAD_REQUEST: "You sent a malformed request.",
            VoiceGatewayCloseCode.DISCONNECTED_RATE_LIMITED: "Disconnected due to rate limit exceeded.",
            VoiceGatewayCloseCode.DISCONNECTED_CALL_TERMINATED: "Call terminated (channel deleted, etc.).",
        }
        return descriptions.get(self, "Unknown voice close code")


# ============================================================================
# HTTP Status Codes
# ============================================================================


class HTTPStatus(Enum):
    """HTTP Status Codes used by Discord API."""

    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    NOT_MODIFIED = 304
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    TOO_MANY_REQUESTS = 429
    GATEWAY_UNAVAILABLE = 502
    SERVER_ERROR = 500  # Generic 5xx


# ============================================================================
# Discord JSON Error Codes
# ============================================================================


class DiscordErrorCode(Enum):
    """Discord JSON Error Codes from the API."""

    # General errors
    GENERAL_ERROR = 0

    # Unknown resources (10000-10099)
    UNKNOWN_ACCOUNT = 10001
    UNKNOWN_APPLICATION = 10002
    UNKNOWN_CHANNEL = 10003
    UNKNOWN_GUILD = 10004
    UNKNOWN_INTEGRATION = 10005
    UNKNOWN_INVITE = 10006
    UNKNOWN_MEMBER = 10007
    UNKNOWN_MESSAGE = 10008
    UNKNOWN_OVERWRITE = 10009
    UNKNOWN_PROVIDER = 10010
    UNKNOWN_ROLE = 10011
    UNKNOWN_TOKEN = 10012
    UNKNOWN_USER = 10013
    UNKNOWN_EMOJI = 10014
    UNKNOWN_WEBHOOK = 10015
    UNKNOWN_WEBHOOK_SERVICE = 10016
    UNKNOWN_SESSION = 10020
    UNKNOWN_ASSET = 10021
    UNKNOWN_BAN = 10026
    UNKNOWN_SKU = 10027
    UNKNOWN_STORE_LISTING = 10028
    UNKNOWN_ENTITLEMENT = 10029
    UNKNOWN_BUILD = 10030
    UNKNOWN_LOBBY = 10031
    UNKNOWN_BRANCH = 10032
    UNKNOWN_STORE_DIRECTORY_LAYOUT = 10033
    UNKNOWN_REDISTRIBUTABLE = 10036
    UNKNOWN_GIFT_CODE = 10038
    UNKNOWN_STREAM = 10049
    UNKNOWN_PREMIUM_SUBSCRIBE_COOLDOWN = 10050
    UNKNOWN_GUILD_TEMPLATE = 10057
    UNKNOWN_DISCOVERABLE_CATEGORY = 10059
    UNKNOWN_STICKER = 10060
    UNKNOWN_STICKER_PACK = 10061
    UNKNOWN_INTERACTION = 10062
    UNKNOWN_APPLICATION_COMMAND = 10063
    UNKNOWN_VOICE_STATE = 10065
    UNKNOWN_APPLICATION_COMMAND_PERMISSIONS = 10066
    UNKNOWN_STAGE_INSTANCE = 10067
    UNKNOWN_GUILD_MEMBER_VERIFICATION_FORM = 10068
    UNKNOWN_GUILD_WELCOME_SCREEN = 10069
    UNKNOWN_GUILD_SCHEDULED_EVENT = 10070
    UNKNOWN_GUILD_SCHEDULED_EVENT_USER = 10071
    UNKNOWN_TAG = 10087
    UNKNOWN_SOUND = 10097
    UNKNOWN_INVITE_TARGET_USERS_JOB = 10124
    UNKNOWN_INVITE_TARGET_USERS = 10129

    # Bots (20000-20099)
    BOTS_CANNOT_USE_ENDPOINT = 20001
    BOT_ONLY_ENDPOINT = 20002
    EXPLICIT_CONTENT_CANNOT_BE_SENT = 20009
    NOT_AUTHORIZED_FOR_ACTION = 20012
    SLOWMODE_RATE_LIMIT = 20016
    ONLY_OWNER_CAN_PERFORM_ACTION = 20018
    MESSAGE_CANNOT_BE_EDITED = 20022
    UNDER_MINIMUM_AGE = 20024
    CHANNEL_WRITE_RATE_LIMIT = 20028
    GUILD_WRITE_RATE_LIMIT = 20029
    FORBIDDEN_WORDS_IN_NAMES = 20031
    GUILD_PREMIUM_TOO_LOW = 20035

    # Limits (30000-30099)
    MAX_GUILDS_REACHED = 30001
    MAX_FRIENDS_REACHED = 30002
    MAX_PINS_REACHED = 30003
    MAX_RECIPIENTS_REACHED = 30004
    MAX_ROLES_REACHED = 30005
    MAX_WEBHOOKS_REACHED = 30007
    MAX_EMOJIS_REACHED = 30008
    MAX_REACTIONS_REACHED = 30010
    MAX_GROUP_DMS_REACHED = 30011
    MAX_CHANNELS_REACHED = 30013
    MAX_ATTACHMENTS_REACHED = 30015
    MAX_INVITES_REACHED = 30016
    MAX_ANIMATED_EMOJIS_REACHED = 30018
    MAX_MEMBERS_REACHED = 30019
    MAX_CATEGORIES_REACHED = 30030
    GUILD_ALREADY_HAS_TEMPLATE = 30031
    MAX_APPLICATION_COMMANDS_REACHED = 30032
    MAX_THREAD_PARTICIPANTS_REACHED = 30033
    MAX_DAILY_APP_COMMAND_CREATES_REACHED = 30034
    MAX_NON_MEMBER_BANS_EXCEEDED = 30035
    MAX_BAN_FETCHES_REACHED = 30037
    MAX_UNCOMPLETED_SCHEDULED_EVENTS_REACHED = 30038
    MAX_STICKERS_REACHED = 30039
    MAX_PRUNE_REQUESTS_REACHED = 30040
    MAX_WIDGET_SETTINGS_UPDATES_REACHED = 30042
    MAX_SOUNDBOARD_SOUNDS_REACHED = 30045
    MAX_OLD_MESSAGE_EDITS_REACHED = 30046
    MAX_PINNED_THREADS_IN_FORUM_REACHED = 30047
    MAX_TAGS_IN_FORUM_REACHED = 30048
    BITRATE_TOO_HIGH = 30052
    MAX_PREMIUM_EMOJIS_REACHED = 30056
    MAX_WEBHOOKS_PER_GUILD_REACHED = 30058
    MAX_CHANNEL_OVERWRITES_REACHED = 30060
    CHANNELS_TOO_LARGE = 30061

    # Unauthorized/Validation (40000-40099)
    UNAUTHORIZED = 40001
    ACCOUNT_VERIFICATION_REQUIRED = 40002
    OPENING_DMS_TOO_FAST = 40003
    SEND_MESSAGES_DISABLED = 40004
    REQUEST_ENTITY_TOO_LARGE = 40005
    FEATURE_TEMPORARILY_DISABLED = 40006
    USER_BANNED_FROM_GUILD = 40007
    CONNECTION_REVOKED = 40012
    ONLY_CONSUMABLE_SKUS = 40018
    ONLY_SANDBOX_ENTITLEMENTS = 40019
    TARGET_USER_NOT_IN_VOICE = 40032
    MESSAGE_ALREADY_CROSSPOSTED = 40033
    COMMAND_NAME_ALREADY_EXISTS = 40041
    INTERACTION_FAILED_TO_SEND = 40043
    CANNOT_SEND_IN_FORUM_CHANNEL = 40058
    INTERACTION_ALREADY_ACKNOWLEDGED = 40060
    TAG_NAMES_MUST_BE_UNIQUE = 40061
    SERVICE_RATE_LIMITED = 40062
    NO_TAGS_FOR_NON_MODERATORS = 40066
    TAG_REQUIRED_FOR_FORUM_POST = 40067
    ENTITLEMENT_ALREADY_GRANTED = 40074
    MAX_FOLLOW_UP_MESSAGES_REACHED = 40094
    CLOUDFLARE_BLOCKING = 40333

    # Permissions (50000-50099)
    MISSING_ACCESS = 50001
    INVALID_ACCOUNT_TYPE = 50002
    CANNOT_EXECUTE_ON_DM = 50003
    GUILD_WIDGET_DISABLED = 50004
    CANNOT_EDIT_MESSAGE_BY_OTHER = 50005
    CANNOT_SEND_EMPTY_MESSAGE = 50006
    CANNOT_MESSAGE_USER = 50007
    CANNOT_SEND_IN_VOICE_CHANNEL = 50008
    CHANNEL_VERIFICATION_TOO_HIGH = 50009
    OAUTH2_APP_HAS_NO_BOT = 50010
    OAUTH2_APPLICATION_LIMIT = 50011
    INVALID_OAUTH_STATE = 50012
    MISSING_PERMISSIONS = 50013
    INVALID_AUTH_TOKEN = 50014
    NOTE_TOO_LONG = 50015
    BULK_DELETE_AMOUNT_INVALID = 50016
    INVALID_MFA_LEVEL = 50017
    CANNOT_PIN_IN_OTHER_CHANNEL = 50019
    INVITE_INVALID_OR_TAKEN = 50020
    CANNOT_EXECUTE_ON_SYSTEM_MESSAGE = 50021
    CANNOT_EXECUTE_ON_CHANNEL_TYPE = 50024
    INVALID_OAUTH2_ACCESS_TOKEN = 50025
    MISSING_REQUIRED_OAUTH2_SCOPE = 50026
    INVALID_WEBHOOK_TOKEN = 50027
    INVALID_ROLE = 50028
    INVALID_RECIPIENTS = 50033
    MESSAGE_TOO_OLD_FOR_BULK_DELETE = 50034
    INVALID_FORM_BODY = 50035
    INVITE_ACCEPTED_BOT_NOT_IN_GUILD = 50036
    INVALID_ACTIVITY_ACTION = 50039
    INVALID_API_VERSION = 50041
    FILE_TOO_LARGE = 50045
    INVALID_FILE = 50046
    CANNOT_SELF_REDEEM_GIFT = 50054
    INVALID_GUILD = 50055
    INVALID_SKU = 50057
    INVALID_REQUEST_ORIGIN = 50067
    INVALID_MESSAGE_TYPE = 50068
    PAYMENT_SOURCE_REQUIRED = 50070
    CANNOT_MODIFY_SYSTEM_WEBHOOK = 50073
    CANNOT_DELETE_COMMUNITY_CHANNEL = 50074
    CANNOT_EDIT_STICKERS = 50080
    INVALID_STICKER = 50081
    ARCHIVED_THREAD_OPERATION = 50083
    INVALID_THREAD_NOTIFICATION_SETTINGS = 50084
    BEFORE_VALUE_TOO_EARLY = 50085
    COMMUNITY_CHANNELS_MUST_BE_TEXT = 50086
    EVENT_ENTITY_TYPE_MISMATCH = 50091
    SERVER_NOT_AVAILABLE_IN_LOCATION = 50095
    MONETIZATION_REQUIRED = 50097
    NEED_MORE_BOOSTS = 50101
    INVALID_JSON = 50109
    INVALID_FILE_UPLOADED = 50110
    INVALID_FILE_TYPE = 50123
    FILE_DURATION_EXCEEDS_MAX = 50124
    OWNER_CANNOT_BE_PENDING = 50131
    OWNERSHIP_CANNOT_TRANSFER_TO_BOT = 50132
    ASSET_RESIZE_FAILED = 50138
    CANNOT_MIX_SUBSCRIPTION_ROLES = 50144
    CANNOT_CONVERT_EMOJI_TYPE = 50145
    UPLOADED_FILE_NOT_FOUND = 50146
    INVALID_EMOJI = 50151
    VOICE_MESSAGES_NO_CONTENT = 50159
    VOICE_MESSAGES_SINGLE_ATTACHMENT = 50160
    VOICE_MESSAGES_NEED_METADATA = 50161
    VOICE_MESSAGES_CANNOT_EDIT = 50162
    CANNOT_DELETE_SUBSCRIPTION_INTEGRATION = 50163
    CANNOT_SEND_VOICE_MESSAGES = 50173
    ACCOUNT_MUST_BE_VERIFIED = 50178
    INVALID_FILE_DURATION = 50192
    NO_MUTUAL_GUILDS = 50278
    NO_PERMISSION_FOR_STICKER = 50600

    # 2FA (60000-60099)
    TWO_FACTOR_REQUIRED = 60003

    # Other (80000+)
    NO_USERS_WITH_DISCORD_TAG = 80004
    REACTION_BLOCKED = 90001
    USER_CANNOT_USE_BURST_REACTIONS = 90002
    INDEX_NOT_AVAILABLE = 110000
    APPLICATION_NOT_AVAILABLE = 110001
    API_RESOURCE_OVERLOADED = 130000
    STAGE_ALREADY_OPEN = 150006
    CANNOT_REPLY_WITHOUT_HISTORY = 160002
    THREAD_ALREADY_CREATED = 160003
    THREAD_LOCKED = 160004
    MAX_ACTIVE_THREADS_REACHED = 160005
    MAX_ANNOUNCEMENT_THREADS_REACHED = 160006
    CANNOT_FORWARD_MESSAGE = 160014
    INVALID_LOTTIE_JSON = 170001
    LOTTIE_CONTAINS_RASTERIZED = 170002
    STICKER_FRAMERATE_EXCEEDED = 170003
    STICKER_FRAME_COUNT_EXCEEDED = 170004
    LOTTIE_DIMENSIONS_EXCEEDED = 170005
    STICKER_FRAMERATE_INVALID = 170006
    STICKER_ANIMATION_TOO_LONG = 170007
    CANNOT_UPDATE_FINISHED_EVENT = 180000
    FAILED_TO_CREATE_STAGE = 180002
    MESSAGE_BLOCKED_BY_AUTOMOD = 200000
    TITLE_BLOCKED_BY_AUTOMOD = 200001
    WEBHOOK_FORUM_THREAD_NAME_REQUIRED = 220001
    WEBHOOK_FORUM_BOTH_THREAD_NAME_AND_ID = 220002
    WEBHOOK_ONLY_CREATE_THREADS_IN_FORUM = 220003
    WEBHOOK_SERVICES_NOT_IN_FORUM = 220004
    MESSAGE_BLOCKED_BY_HARMFUL_LINKS = 240000
    CANNOT_ENABLE_ONBOARDING = 350000
    CANNOT_UPDATE_ONBOARDING = 350001
    FILE_UPLOADS_LIMITED = 400001
    FAILED_TO_BAN_USERS = 500000
    POLL_VOTING_BLOCKED = 520000
    POLL_EXPIRED = 520001
    INVALID_CHANNEL_FOR_POLL = 520002
    CANNOT_EDIT_POLL = 520003
    CANNOT_USE_POLL_EMOJI = 520004
    CANNOT_EXPIRE_NON_POLL = 520006
    PROVISIONAL_ACCOUNTS_NOT_GRANTED = 530000
    ID_TOKEN_EXPIRED = 530001
    ID_TOKEN_ISSUER_MISMATCH = 530002
    ID_TOKEN_AUDIENCE_MISMATCH = 530003
    ID_TOKEN_ISSUED_TOO_LONG_AGO = 530004
    USERNAME_GENERATION_TIMEOUT = 530006
    INVALID_CLIENT_SECRET = 530007

    @property
    def category(self) -> str:
        """Get the category of the error code."""
        code = self.value
        if code == 0:
            return "General"
        elif 10000 <= code < 20000:
            return "Unknown Resource"
        elif 20000 <= code < 30000:
            return "Bot/User Action"
        elif 30000 <= code < 40000:
            return "Limit Reached"
        elif 40000 <= code < 50000:
            return "Unauthorized/Validation"
        elif 50000 <= code < 60000:
            return "Permissions"
        elif 60000 <= code < 70000:
            return "Two-Factor Authentication"
        else:
            return "Other"

    @property
    def description(self) -> str:
        """Human-readable description of the error."""
        # This could be expanded with more detailed descriptions
        return f"{self.name.replace('_', ' ').title()} ({self.category})"


# ============================================================================
# RPC Error Codes
# ============================================================================


class RPCErrorCode(Enum):
    """Discord RPC Error Codes."""

    UNKNOWN_ERROR = 1000
    INVALID_PAYLOAD = 4000
    INVALID_COMMAND = 4002
    INVALID_GUILD = 4003
    INVALID_EVENT = 4004
    INVALID_CHANNEL = 4005
    INVALID_PERMISSIONS = 4006
    INVALID_CLIENT_ID = 4007
    INVALID_ORIGIN = 4008
    INVALID_TOKEN = 4009
    INVALID_USER = 4010
    OAUTH2_ERROR = 5000
    SELECT_CHANNEL_TIMEOUT = 5001
    GET_GUILD_TIMEOUT = 5002
    SELECT_VOICE_FORCE_REQUIRED = 5003
    CAPTURE_SHORTCUT_ALREADY_LISTENING = 5004


class RPCCloseCode(Enum):
    """Discord RPC Close Event Codes."""

    INVALID_CLIENT_ID = 4000
    INVALID_ORIGIN = 4001
    RATE_LIMITED = 4002
    TOKEN_REVOKED = 4003
    INVALID_VERSION = 4004
    INVALID_ENCODING = 4005


# ============================================================================
# Exception Classes
# ============================================================================


@dataclass
class ErrorDetails:
    """Detailed error information from Discord API."""

    code: str
    message: str
    path: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
        }


class VaidCordError(Exception):
    """Base exception for all VaidCord errors."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        status: int | None = None,
        details: list[ErrorDetails] | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.details = details or []
        self.raw_data = raw_data or {}

    def __str__(self) -> str:
        parts = [self.message]
        if self.code is not None:
            parts.append(f"(Code: {self.code})")
        if self.status is not None:
            parts.append(f"(Status: {self.status})")
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for logging/debugging."""
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "code": self.code,
            "status": self.status,
            "details": [d.to_dict() for d in self.details],
            "raw_data": self.raw_data,
        }


class DiscordAPIError(VaidCordError):
    """Raised when Discord API returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        status: int | None = None,
        errors: dict[str, Any] | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        details = self._parse_errors(errors) if errors else []
        super().__init__(
            message,
            code=code,
            status=status,
            details=details,
            raw_data=raw_data,
        )
        self.errors = errors

    def _parse_errors(
        self,
        errors: dict[str, Any] | None,
        path: list[str] | None = None,
    ) -> list[ErrorDetails]:
        """Parse Discord's nested error structure into flat list."""
        result = []
        if not errors:
            return result

        path = path or []

        # Handle root-level "_errors" key
        if "_errors" in errors:
            for error in errors["_errors"]:
                result.append(
                    ErrorDetails(
                        code=error.get("code", "UNKNOWN"),
                        message=error.get("message", "Unknown error"),
                        path=path,  # Root level has empty path
                    )
                )

        for key, value in errors.items():
            if key == "_errors":
                continue  # Already handled above

            current_path = path + [key]

            if isinstance(value, dict):
                if "_errors" in value:
                    # Found actual errors
                    for error in value["_errors"]:
                        result.append(
                            ErrorDetails(
                                code=error.get("code", "UNKNOWN"),
                                message=error.get("message", "Unknown error"),
                                path=current_path,
                            )
                        )
                else:
                    # Recurse into nested structure
                    result.extend(self._parse_errors(value, current_path))

        return result

    @property
    def error_code_enum(self) -> DiscordErrorCode | None:
        """Get the DiscordErrorCode enum if code matches."""
        if self.code:
            try:
                return DiscordErrorCode(self.code)
            except ValueError:
                return None
        return None

    @property
    def formatted_details(self) -> str:
        """Get a formatted string of all error details."""
        if not self.details:
            return ""

        lines = ["Error Details:"]
        for detail in self.details:
            path_str = ".".join(detail.path)
            lines.append(f"  - {path_str}: {detail.message} ({detail.code})")
        return "\n".join(lines)

    def __str__(self) -> str:
        base = super().__str__()
        if self.formatted_details:
            return f"{base}\n{self.formatted_details}"
        return base


class GatewayError(VaidCordError):
    """Raised when Gateway encounters an error."""

    def __init__(
        self,
        message: str,
        *,
        close_code: GatewayCloseCode | None = None,
        opcode: GatewayOpcode | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        code = close_code.value if close_code else None
        super().__init__(
            message,
            code=code,
            raw_data=raw_data,
        )
        self.close_code = close_code
        self.opcode = opcode

    @property
    def should_reconnect(self) -> bool:
        """Whether to attempt reconnection."""
        if self.close_code:
            return self.close_code.should_reconnect
        return True

    def __str__(self) -> str:
        parts = [self.message]
        if self.close_code:
            parts.append(
                f"Close Code: {self.close_code.name} ({self.close_code.value})"
            )
            parts.append(f"Description: {self.close_code.description}")
            parts.append(f"Should Reconnect: {self.should_reconnect}")
        return " | ".join(parts)


class VoiceGatewayError(VaidCordError):
    """Raised when Voice Gateway encounters an error."""

    def __init__(
        self,
        message: str,
        *,
        close_code: VoiceGatewayCloseCode | None = None,
        opcode: VoiceGatewayOpcode | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        code = close_code.value if close_code else None
        super().__init__(
            message,
            code=code,
            raw_data=raw_data,
        )
        self.close_code = close_code
        self.opcode = opcode

    @property
    def should_reconnect(self) -> bool:
        """Whether to attempt reconnection."""
        if self.close_code:
            return self.close_code.should_reconnect
        return True

    def __str__(self) -> str:
        parts = [self.message]
        if self.close_code:
            parts.append(
                f"Close Code: {self.close_code.name} ({self.close_code.value})"
            )
            parts.append(f"Description: {self.close_code.description}")
            parts.append(f"Should Reconnect: {self.should_reconnect}")
        return " | ".join(parts)


class RateLimitError(VaidCordError):
    """Raised when rate limited by Discord."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        global_limit: bool = False,
        route: str | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=429,
            status=429,
            raw_data=raw_data,
        )
        self.retry_after = retry_after
        self.global_limit = global_limit
        self.route = route

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.retry_after is not None:
            parts.append(f"Retry After: {self.retry_after}s")
        if self.global_limit:
            parts.append("(Global Rate Limit)")
        if self.route:
            parts.append(f"Route: {self.route}")
        return " | ".join(parts)


class AuthenticationError(VaidCordError):
    """Raised when authentication fails."""

    def __init__(
        self,
        message: str,
        *,
        reason: str | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=401,
            status=401,
            raw_data=raw_data,
        )
        self.reason = reason


class ForbiddenError(VaidCordError):
    """Raised when action is forbidden (insufficient permissions)."""

    def __init__(
        self,
        message: str,
        *,
        missing_permissions: list[str] | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=403,
            status=403,
            raw_data=raw_data,
        )
        self.missing_permissions = missing_permissions


class NotFoundError(VaidCordError):
    """Raised when resource is not found."""

    def __init__(
        self,
        message: str,
        *,
        resource_type: str | None = None,
        resource_id: str | int | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=404,
            status=404,
            raw_data=raw_data,
        )
        self.resource_type = resource_type
        self.resource_id = resource_id


class ValidationError(VaidCordError):
    """Raised when request validation fails."""

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: Any | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=400,
            status=400,
            raw_data=raw_data,
        )
        self.field = field
        self.value = value


class OAuth2Error(VaidCordError):
    """Raised when OAuth2 flow fails."""

    def __init__(
        self,
        message: str,
        *,
        error_type: str | None = None,
        error_description: str | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            raw_data=raw_data,
        )
        self.error_type = error_type
        self.error_description = error_description


class MockError(VaidCordError):
    """Raised when mock testing encounters an error."""

    pass


# ============================================================================
# Error Factory
# ============================================================================


def create_discord_error(
    status: int,
    data: dict[str, Any],
) -> VaidCordError:
    """
    Create appropriate error instance from Discord API response.

    Args:
        status: HTTP status code
        data: Response data containing 'code' and 'message'

    Returns:
        Appropriate VaidCordError subclass
    """
    code = data.get("code", status)
    message = data.get("message", "Unknown error")
    errors = data.get("errors")

    # Map status codes to error types
    if status == 401:
        return AuthenticationError(message, raw_data=data)
    elif status == 403:
        return ForbiddenError(message, raw_data=data)
    elif status == 404:
        return NotFoundError(message, raw_data=data)
    elif status == 429:
        retry_after = data.get("retry_after")
        is_global = data.get("global", False)
        return RateLimitError(
            message,
            retry_after=retry_after,
            global_limit=is_global,
            raw_data=data,
        )
    elif status >= 500:
        return VaidCordError(
            message,
            code=code,
            status=status,
            raw_data=data,
        )
    else:
        # Default to DiscordAPIError for 4xx errors
        return DiscordAPIError(
            message,
            code=code,
            status=status,
            errors=errors,
            raw_data=data,
        )


def create_gateway_error(
    close_code: int,
    message: str | None = None,
) -> GatewayError:
    """
    Create GatewayError from close code.

    Args:
        close_code: Gateway close code
        message: Optional custom message

    Returns:
        GatewayError instance
    """
    try:
        code_enum = GatewayCloseCode(close_code)
        msg = message or code_enum.description
        return GatewayError(msg, close_code=code_enum)
    except ValueError:
        return GatewayError(
            message or f"Unknown gateway close code: {close_code}",
            raw_data={"close_code": close_code},
        )


def create_voice_gateway_error(
    close_code: int,
    message: str | None = None,
) -> VoiceGatewayError:
    """
    Create VoiceGatewayError from close code.

    Args:
        close_code: Voice gateway close code
        message: Optional custom message

    Returns:
        VoiceGatewayError instance
    """
    try:
        code_enum = VoiceGatewayCloseCode(close_code)
        msg = message or code_enum.description
        return VoiceGatewayError(msg, close_code=code_enum)
    except ValueError:
        return VoiceGatewayError(
            message or f"Unknown voice gateway close code: {close_code}",
            raw_data={"close_code": close_code},
        )
