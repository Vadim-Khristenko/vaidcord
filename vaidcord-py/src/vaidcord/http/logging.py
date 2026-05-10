"""Structured request logging and payload sanitization helpers.

Pulled out of the monolithic HTTP client so that:

* tests can assert on log output without instantiating an HTTP client;
* third parties can re-use the redaction rules for their own logging.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("vaidcord.http")


_SENSITIVE_HEADERS = frozenset({
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "cookie",
    "set-cookie",
})

_SENSITIVE_PAYLOAD_KEYS = frozenset({
    "token",
    "authorization",
    "password",
    "secret",
    "api_key",
})


def sanitize_headers(headers: dict[str, Any] | None) -> dict[str, Any]:
    """Return ``headers`` with sensitive values redacted."""
    if not headers:
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in headers.items():
        if key.lower() in _SENSITIVE_HEADERS:
            sanitized[key] = "<redacted>"
        else:
            sanitized[key] = value
    return sanitized


def sanitize_payload(payload: Any) -> Any:
    """Return ``payload`` with sensitive values redacted (recursively)."""
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            if key.lower() in _SENSITIVE_PAYLOAD_KEYS:
                sanitized[key] = "<redacted>"
            else:
                sanitized[key] = sanitize_payload(value)
        return sanitized
    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    return payload


def extract_rate_limit_fields(headers: dict[str, str] | None) -> dict[str, Any]:
    """Extract common Discord rate-limit fields from headers."""
    headers = headers or {}
    return {
        "limit": headers.get("X-RateLimit-Limit"),
        "remaining": headers.get("X-RateLimit-Remaining"),
        "reset_after": headers.get("X-RateLimit-Reset-After"),
        "reset": headers.get("X-RateLimit-Reset"),
        "bucket": headers.get("X-RateLimit-Bucket"),
        "global": headers.get("X-RateLimit-Global"),
    }


class RequestLogger:
    """Emits structured HTTP log events scoped to a particular bot."""

    __slots__ = ("_bot_id",)

    def __init__(self) -> None:
        self._bot_id: str | None = None

    def set_bot_id(self, bot_id: str | int | None) -> None:
        self._bot_id = None if bot_id is None else str(bot_id)

    def emit(self, event: str, request_id: str, /, **fields: Any) -> None:
        payload = {"event": event, "request_id": request_id, **fields}
        if self._bot_id is not None:
            payload["bot_id"] = self._bot_id
        logger.info(payload)


__all__ = [
    "RequestLogger",
    "sanitize_headers",
    "sanitize_payload",
    "extract_rate_limit_fields",
]
