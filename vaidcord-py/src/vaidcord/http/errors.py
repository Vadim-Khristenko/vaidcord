"""Legacy error types exported by the public ``vaidcord.http`` surface.

The comprehensive Discord error code enum lives in :mod:`vaidcord.errors`.
The smaller :class:`DiscordErrorCode` defined here is preserved for
backwards compatibility with code that imports it from ``vaidcord.http``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class DiscordErrorCode(Enum):
    """Common Discord error codes (legacy ``vaidcord.http`` surface).

    For the full enum used across the framework see
    :class:`vaidcord.errors.DiscordErrorCode`.
    """

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
    UNKNOWN_ROLE_1 = 10011  # First UNKNOWN_ROLE
    UNKNOWN_TOKEN = 10012
    UNKNOWN_USER = 10013
    UNKNOWN_EMOJI = 10014
    UNKNOWN_WEBHOOK = 10015
    UNKNOWN_BOT = 10016
    BOTS_NOT_ALLOWED = 20001
    BOT_ONLY_ENDPOINT = 20002
    MAX_CHANNELS_EXCEEDED = 30003
    UNAUTHORIZED = 40001
    USER_BANNED = 40004
    CONNECTION_REVOKED = 40005
    MISSING_ACCESS = 50001
    INVALID_ACCOUNT_TYPE = 50002
    CANNOT_EXECUTE_ON_DM = 50003
    EMBED_DISABLED = 50004
    CANNOT_EDIT_MESSAGE_BY_OTHER = 50005
    CANNOT_SEND_EMPTY_MESSAGE = 50006
    CANNOT_MESSAGE_USER = 50007
    CANNOT_SEND_MESSAGES_IN_VOICE_CHANNEL = 50008
    CHANNEL_VERIFICATION_LEVEL_TOO_HIGH = 50009
    OAUTH2_APPLICATION_HAS_NO_BOT = 50010
    OAUTH2_APPLICATION_LIMIT_REACHED = 50011
    INVALID_OAUTH_STATE = 50012
    MISSING_PERMISSIONS = 50013
    INVALID_AUTHENTICATION_TOKEN = 50014
    NOTE_TOO_LONG = 50015
    BULK_DELETE_AMOUNT_OUT_OF_RANGE = 50016
    CANNOT_PIN_MESSAGE_IN_OTHER_CHANNEL = 50019
    INVITE_CODE_INVALID_OR_TAKEN = 50020
    CANNOT_EXECUTE_ON_SYSTEM_MESSAGE = 50021
    CANNOT_EXECUTE_ON_CHANNEL_TYPE = 50024
    INVALID_OAUTH2_ACCESS_TOKEN = 50025
    MISSING_REQUIRED_OAUTH2_SCOPE = 50026
    INVALID_WEBHOOK_TOKEN = 50027
    UNKNOWN_ROLE_2 = 50028
    INVALID_FORM_BODY = 50035
    APPLICATION_COMMAND_TOO_LARGE = 50038


@dataclass
class DiscordError(Exception):
    """Represents a Discord API error."""

    code: int
    message: str
    errors: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        super().__init__(self.__str__())

    @classmethod
    def from_response(cls, status: int, data: dict[str, Any]) -> DiscordError:
        """Create a DiscordError from an API response."""
        return cls(
            code=data.get("code", status),
            message=data.get("message", "Unknown error"),
            errors=data.get("errors"),
        )

    def __str__(self) -> str:
        if self.errors:
            return f"{self.code}: {self.message} - Errors: {json.dumps(self.errors)}"
        return f"{self.code}: {self.message}"


__all__ = ["DiscordErrorCode", "DiscordError"]
