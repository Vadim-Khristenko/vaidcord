"""HTTP layer for VaidCord.

Splits the legacy single-file ``vaidcord.http`` module into focused
collaborators (issue #32) while keeping every previously-exported symbol
importable from the same dotted path:

* :mod:`.client` — :class:`HTTPClient`, the orchestrator.
* :mod:`.transport` — :class:`TransportSession` (aiohttp ownership).
* :mod:`.rate_limit` — :class:`RateLimitManager`.
* :mod:`.retry` — :class:`RetryPolicy` (exponential backoff).
* :mod:`.logging` — :class:`RequestLogger` + sanitization helpers.
* :mod:`.config` — ``HTTPConfig``, ``HTTPResponseData``, ``RateLimitInfo``.
* :mod:`.errors` — legacy ``DiscordError``, ``DiscordErrorCode``.

Existing code that does ``from vaidcord.http import HTTPClient, ...`` is
unchanged.
"""

from .client import HTTPClient
from .config import HTTPConfig, HTTPRequestContext, HTTPResponseData, RateLimitInfo
from .errors import DiscordError, DiscordErrorCode
from .logging import (
    RequestLogger,
    extract_rate_limit_fields,
    sanitize_headers,
    sanitize_payload,
)
from .rate_limit import RateLimitManager
from .retry import RetryPolicy
from .transport import TransportSession

__all__ = [
    "HTTPClient",
    "HTTPConfig",
    "HTTPResponseData",
    "HTTPRequestContext",
    "RateLimitInfo",
    "RateLimitManager",
    "RetryPolicy",
    "TransportSession",
    "RequestLogger",
    "DiscordError",
    "DiscordErrorCode",
    "sanitize_headers",
    "sanitize_payload",
    "extract_rate_limit_fields",
]
