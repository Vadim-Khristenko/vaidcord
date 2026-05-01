"""
HTTP Client for VaidCord.

Provides a high-performance HTTP client with support for:
- Proxy configuration
- Custom API endpoints
- Rate limiting
- Error handling with detailed error messages
- Request retries
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, cast

import aiohttp
from aiohttp import ClientSession, TCPConnector

from vaidcord.errors import create_discord_error
from vaidcord.metadata import __version__, build_user_agent

logger = logging.getLogger(__name__)


class DiscordErrorCode(Enum):
    """Common Discord error codes."""

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
    UNKNOWN_ROLE_2 = 50028  # Second UNKNOWN_ROLE (different context)
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


@dataclass
class RateLimitInfo:
    """Information about rate limiting."""

    limit: int
    remaining: int
    reset_after: float
    reset: datetime
    bucket: str | None = None
    global_limit: bool = False


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
class HTTPResponseData:
    """In-memory HTTP response payload captured before context exit."""

    status: int
    headers: dict[str, str]
    body: bytes


class HTTPClient:
    """
    High-performance HTTP client for Discord API.

    Features:
    - Automatic rate limit handling
    - Retry logic with exponential backoff
    - Proxy support
    - Custom API endpoints
    - Detailed error handling
    """

    def __init__(
        self,
        config: HTTPConfig,
        *,
        session_provider: Callable[[], Awaitable[ClientSession]] | None = None,
        session_closer: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.config = config
        self._session: ClientSession | None = None
        self._session_provider = session_provider
        self._session_closer = session_closer
        self._rate_limits: dict[str, RateLimitInfo] = {}
        self._global_rate_limit: datetime | None = None
        self._global_rate_limit_lock = asyncio.Lock()
        self._route_locks: dict[str, asyncio.Lock] = {}
        self._bot_id: str | None = None

    def set_bot_id(self, bot_id: str | int | None) -> None:
        """Attach bot identity to subsequent HTTP logs."""
        self._bot_id = None if bot_id is None else str(bot_id)

    @staticmethod
    def _sanitize_headers(headers: dict[str, Any] | None) -> dict[str, Any]:
        """Return headers with sensitive values redacted."""
        if not headers:
            return {}

        sensitive_keys = {
            "authorization",
            "proxy-authorization",
            "x-api-key",
            "cookie",
            "set-cookie",
        }
        sanitized: dict[str, Any] = {}
        for key, value in headers.items():
            if key.lower() in sensitive_keys:
                sanitized[key] = "<redacted>"
            else:
                sanitized[key] = value
        return sanitized

    @classmethod
    def _sanitize_payload(cls, payload: Any) -> Any:
        """Return payload with sensitive values redacted."""
        sensitive_keys = {"token", "authorization", "password", "secret", "api_key"}

        if isinstance(payload, dict):
            sanitized: dict[str, Any] = {}
            for key, value in payload.items():
                if key.lower() in sensitive_keys:
                    sanitized[key] = "<redacted>"
                else:
                    sanitized[key] = cls._sanitize_payload(value)
            return sanitized
        if isinstance(payload, list):
            return [cls._sanitize_payload(item) for item in payload]
        return payload

    @staticmethod
    def _extract_rate_limit_fields(headers: dict[str, str] | None) -> dict[str, Any]:
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

    def _log_http_event(self, event: str, request_id: str, **fields: Any) -> None:
        """Emit structured HTTP log events."""
        payload = {"event": event, "request_id": request_id, **fields}
        if self._bot_id is not None:
            payload["bot_id"] = self._bot_id
        logger.info(payload)

    @property
    def headers(self) -> dict[str, str]:
        """Get default headers for requests."""
        user_agent = self.config.user_agent or build_user_agent()
        return {
            "Authorization": f"Bot {self.config.token}",
            "User-Agent": user_agent,
            "X-VaidCord-Version": __version__,
        }

    async def _create_session(self) -> ClientSession:
        """Create or get existing aiohttp session."""
        if self._session_provider is not None:
            return await self._session_provider()
        if self._session is None or self._session.closed:
            connector = TCPConnector(limit=self.config.connector_limit)
            self._session = ClientSession(
                connector=connector,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session_closer is not None:
            await self._session_closer()
            return
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _check_rate_limit(
        self, route: str, response: aiohttp.ClientResponse, request_id: str
    ) -> RateLimitInfo | None:
        """Check and handle rate limit headers."""
        headers = response.headers

        limit = int(headers.get("X-RateLimit-Limit", 0))
        remaining = int(headers.get("X-RateLimit-Remaining", 0))
        reset_after = float(headers.get("X-RateLimit-Reset-After", 0))
        reset_ts = float(headers.get("X-RateLimit-Reset", 0))
        bucket = headers.get("X-RateLimit-Bucket")

        reset = datetime.fromtimestamp(reset_ts) if reset_ts else datetime.now()

        info = RateLimitInfo(
            limit=limit,
            remaining=remaining,
            reset_after=reset_after,
            reset=reset,
            bucket=bucket,
        )

        # Check for global rate limit
        if headers.get("X-RateLimit-Global") == "true":
            self._global_rate_limit = reset
            self._log_http_event(
                "http.rate_limit.global",
                request_id,
                route=route,
                bucket=bucket,
                reset_after=reset_after,
                remaining=remaining,
                reset_at=reset.isoformat(),
            )

        # Store rate limit info
        self._rate_limits[route] = info

        if remaining == 0:
            wait_time = reset_after
            self._log_http_event(
                "http.rate_limit.route",
                request_id,
                route=route,
                bucket=bucket,
                reset_after=reset_after,
                remaining=remaining,
                wait_time_s=wait_time,
            )
            await asyncio.sleep(wait_time)

        return info

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        request_id: str,
        has_json: bool = False,
        sanitized_payload: Any = None,
        **kwargs: Any,
    ) -> HTTPResponseData:
        """Make a request with automatic retries."""
        last_exception: Exception | None = None
        request_headers = self._sanitize_headers(kwargs.get("headers"))
        has_params = kwargs.get("params") is not None

        for attempt in range(self.config.max_retries):
            started = time.perf_counter()
            self._log_http_event(
                "http.request.start",
                request_id,
                method=method,
                route=endpoint,
                attempt=attempt + 1,
                has_json=has_json,
                has_params=has_params,
                headers=request_headers,
                payload=sanitized_payload,
            )
            try:
                session = await self._create_session()
                url = f"{self.config.base_url}/v{self.config.api_version}{endpoint}"

                # Handle proxy
                proxy = self.config.proxy
                proxy_auth = self.config.proxy_auth

                async with session.request(
                    method,
                    url,
                    proxy=proxy,
                    proxy_auth=proxy_auth,
                    **kwargs,
                ) as response:
                    # Check rate limits
                    await self._check_rate_limit(endpoint, response, request_id)

                    # Handle server errors with retry
                    if response.status >= 500:
                        if attempt < self.config.max_retries - 1:
                            delay = self.config.retry_delay * (2**attempt)
                            self._log_http_event(
                                "http.request.retry",
                                request_id,
                                method=method,
                                route=endpoint,
                                attempt=attempt + 1,
                                delay_s=delay,
                                reason="server_error",
                                status=response.status,
                            )
                            await asyncio.sleep(delay)
                            continue

                    body = await response.read()
                    duration_ms = round((time.perf_counter() - started) * 1000, 2)
                    self._log_http_event(
                        "http.request.done",
                        request_id,
                        method=method,
                        route=endpoint,
                        attempt=attempt + 1,
                        status=response.status,
                        duration_ms=duration_ms,
                        rate_limit=self._extract_rate_limit_fields(dict(response.headers)),
                        response_size=len(body),
                    )
                    return HTTPResponseData(
                        status=response.status,
                        headers=dict(response.headers),
                        body=body,
                    )

            except (TimeoutError, aiohttp.ClientError) as e:
                last_exception = e
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (2**attempt)
                    self._log_http_event(
                        "http.request.retry",
                        request_id,
                        method=method,
                        route=endpoint,
                        attempt=attempt + 1,
                        delay_s=delay,
                        reason=type(e).__name__,
                        error=str(e),
                        duration_ms=duration_ms,
                    )
                    await asyncio.sleep(delay)
                else:
                    self._log_http_event(
                        "http.request.error",
                        request_id,
                        method=method,
                        route=endpoint,
                        attempt=attempt + 1,
                        reason=type(e).__name__,
                        message=str(e),
                        duration_ms=duration_ms,
                    )
                    raise

        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected error in request loop")

    def _get_route_lock(self, endpoint: str) -> asyncio.Lock:
        lock = self._route_locks.get(endpoint)
        if lock is None:
            lock = asyncio.Lock()
            self._route_locks[endpoint] = lock
        return lock

    async def _wait_for_global_rate_limit(self) -> None:
        async with self._global_rate_limit_lock:
            if self._global_rate_limit and datetime.now() < self._global_rate_limit:
                wait_time = (self._global_rate_limit - datetime.now()).total_seconds()
                logger.warning(f"Waiting for global rate limit: {wait_time}s")
                await asyncio.sleep(wait_time)

    async def request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Make an API request to Discord.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint (e.g., "/channels/123/messages")
            **kwargs: Additional arguments for the request

        Returns:
            JSON response from the API

        Raises:
            DiscordError: If the API returns an error
        """
        await self._wait_for_global_rate_limit()

        # Prepare request data
        request_id = str(uuid.uuid4())
        has_json = "json" in kwargs and kwargs["json"] is not None
        sanitized_payload = (
            self._sanitize_payload(kwargs["json"]) if has_json else None
        )

        async with self._get_route_lock(endpoint):
            response = await self._request_with_retry(
                method,
                endpoint,
                request_id,
                has_json=has_json,
                sanitized_payload=sanitized_payload,
                **kwargs,
            )

        # Handle error responses
        if response.status >= 400:
            try:
                error_data = json.loads(response.body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                error_data = {
                    "code": response.status,
                    "message": response.body.decode("utf-8", errors="replace"),
                }

            discord_error = create_discord_error(response.status, error_data)
            self._log_http_event(
                "http.request.error",
                request_id,
                method=method,
                route=endpoint,
                status=response.status,
                attempt=1,
                code=discord_error.code,
                message=discord_error.message,
                duration_ms=None,
            )
            raise discord_error

        # Parse successful response
        if response.status == 204:
            return {}

        if not response.body:
            return {}
        return cast(dict[str, Any], json.loads(response.body.decode("utf-8")))

    async def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make a GET request."""
        return await self.request("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make a POST request."""
        return await self.request("POST", endpoint, **kwargs)

    async def put(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make a PUT request."""
        return await self.request("PUT", endpoint, **kwargs)

    async def patch(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make a PATCH request."""
        return await self.request("PATCH", endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make a DELETE request."""
        return await self.request("DELETE", endpoint, **kwargs)

    async def upload_file(
        self,
        endpoint: str,
        file_data: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Upload a file to Discord.

        Args:
            endpoint: API endpoint
            file_data: File content as bytes
            filename: Name of the file
            content_type: MIME type of the file
            **kwargs: Additional form fields

        Returns:
            JSON response with file information
        """
        form_data = aiohttp.FormData()
        form_data.add_field(
            "file",
            file_data,
            filename=filename,
            content_type=content_type,
        )

        # Add payload_json if provided
        if "payload_json" in kwargs:
            form_data.add_field(
                "payload_json",
                json.dumps(kwargs["payload_json"]),
                content_type="application/json",
            )
            del kwargs["payload_json"]

        # Add additional fields
        for key, value in kwargs.items():
            form_data.add_field(key, str(value))

        return await self.request("POST", endpoint, data=form_data)

    def __repr__(self) -> str:
        return f"<HTTPClient base_url={self.config.base_url}>"
