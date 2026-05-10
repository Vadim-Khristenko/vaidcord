"""Configuration and DTOs for the HTTP layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp

from vaidcord.metadata import build_user_agent


@dataclass
class HTTPConfig:
    """Configuration for the HTTP client."""

    token: str
    api_version: str = "10"
    base_url: str = "https://discord.com/api"
    proxy: str | None = None
    proxy_auth: aiohttp.BasicAuth | None = None
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    connector_limit: int = 100
    user_agent: str | None = None

    def __post_init__(self) -> None:
        if self.user_agent is None:
            self.user_agent = build_user_agent()


@dataclass
class RateLimitInfo:
    """Information about rate limiting on a single Discord route."""

    limit: int
    remaining: int
    reset_after: float
    reset: datetime
    bucket: str | None = None
    global_limit: bool = False


@dataclass
class HTTPResponseData:
    """In-memory HTTP response payload captured before context exit."""

    status: int
    headers: dict[str, str]
    body: bytes


@dataclass
class HTTPRequestContext:
    """Stable request metadata threaded through transport / retry / logger."""

    request_id: str
    method: str
    endpoint: str
    has_json: bool = False
    has_params: bool = False
    sanitized_payload: Any = None
    sanitized_headers: dict[str, Any] | None = None


__all__ = [
    "HTTPConfig",
    "RateLimitInfo",
    "HTTPResponseData",
    "HTTPRequestContext",
]
