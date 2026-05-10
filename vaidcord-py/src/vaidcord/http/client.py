"""HTTP client orchestrator.

The :class:`HTTPClient` is now a thin orchestrator that delegates each
concern to a focused collaborator:

* :class:`~vaidcord.http.transport.TransportSession` — owns the aiohttp
  ``ClientSession`` and connector.
* :class:`~vaidcord.http.rate_limit.RateLimitManager` — per-route +
  global rate-limit state and synchronization.
* :class:`~vaidcord.http.retry.RetryPolicy` — backoff + retry decisions.
* :class:`~vaidcord.http.logging.RequestLogger` — structured logging,
  payload / header redaction.

The public surface (``request``, ``get``, ``post``, ``put``, ``patch``,
``delete``, ``upload_file``, ``close``, ``set_bot_id``, ``headers``) is
unchanged so existing callers (``api_client``, ``bot``, mock, tests) keep
working without modification.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, cast

import aiohttp
from aiohttp import ClientSession

from vaidcord.errors import create_discord_error

from .config import HTTPConfig, HTTPResponseData, RateLimitInfo
from .logging import (
    RequestLogger,
    extract_rate_limit_fields,
    sanitize_headers,
    sanitize_payload,
)
from .rate_limit import RateLimitManager
from .retry import RetryPolicy
from .transport import TransportSession


class HTTPClient:
    """High-performance HTTP client for Discord API."""

    def __init__(
        self,
        config: HTTPConfig,
        *,
        session_provider: Callable[[], Awaitable[ClientSession]] | None = None,
        session_closer: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.config = config
        self._transport = TransportSession(
            config,
            session_provider=session_provider,
            session_closer=session_closer,
        )
        self._rate_limits = RateLimitManager()
        self._retry = RetryPolicy(
            max_retries=config.max_retries,
            base_delay=config.retry_delay,
        )
        self._logger = RequestLogger()

    # ------------------------------------------------------------------ #
    # Public surface (unchanged)                                         #
    # ------------------------------------------------------------------ #

    def set_bot_id(self, bot_id: str | int | None) -> None:
        """Attach bot identity to subsequent HTTP logs."""
        self._logger.set_bot_id(bot_id)

    @property
    def headers(self) -> dict[str, str]:
        return self._transport.headers

    async def close(self) -> None:
        await self._transport.close()

    async def request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        await self._rate_limits.wait_for_global()

        request_id = str(uuid.uuid4())
        has_json = "json" in kwargs and kwargs["json"] is not None
        sanitized_payload = sanitize_payload(kwargs["json"]) if has_json else None

        async with self._rate_limits.get_route_lock(endpoint):
            response = await self._request_with_retry(
                method,
                endpoint,
                request_id,
                has_json=has_json,
                sanitized_payload=sanitized_payload,
                **kwargs,
            )

        if response.status >= 400:
            try:
                error_data = json.loads(response.body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                error_data = {
                    "code": response.status,
                    "message": response.body.decode("utf-8", errors="replace"),
                }
            discord_error = create_discord_error(response.status, error_data)
            self._logger.emit(
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

        if response.status == 204:
            return {}
        if not response.body:
            return {}
        return cast(dict[str, Any], json.loads(response.body.decode("utf-8")))

    async def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", endpoint, **kwargs)

    async def put(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("PUT", endpoint, **kwargs)

    async def patch(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("PATCH", endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("DELETE", endpoint, **kwargs)

    async def upload_file(
        self,
        endpoint: str,
        file_data: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        **kwargs: Any,
    ) -> dict[str, Any]:
        form_data = aiohttp.FormData()
        form_data.add_field(
            "file",
            file_data,
            filename=filename,
            content_type=content_type,
        )
        if "payload_json" in kwargs:
            form_data.add_field(
                "payload_json",
                json.dumps(kwargs["payload_json"]),
                content_type="application/json",
            )
            del kwargs["payload_json"]
        for key, value in kwargs.items():
            form_data.add_field(key, str(value))
        return await self.request("POST", endpoint, data=form_data)

    def __repr__(self) -> str:
        return f"<HTTPClient base_url={self.config.base_url}>"

    # ------------------------------------------------------------------ #
    # Internal request loop                                              #
    # ------------------------------------------------------------------ #

    async def _create_session(self) -> ClientSession:
        """Compatibility shim retained for subclasses that override it."""
        return await self._transport.get_session()

    def _get_route_lock(self, endpoint: str) -> asyncio.Lock:
        return self._rate_limits.get_route_lock(endpoint)

    async def _wait_for_global_rate_limit(self) -> None:
        await self._rate_limits.wait_for_global()

    @staticmethod
    def _sanitize_headers(headers: dict[str, Any] | None) -> dict[str, Any]:
        return sanitize_headers(headers)

    @classmethod
    def _sanitize_payload(cls, payload: Any) -> Any:
        return sanitize_payload(payload)

    @staticmethod
    def _extract_rate_limit_fields(headers: dict[str, str] | None) -> dict[str, Any]:
        return extract_rate_limit_fields(headers)

    def _log_http_event(self, event: str, request_id: str, **fields: Any) -> None:
        self._logger.emit(event, request_id, **fields)

    async def _check_rate_limit(
        self, route: str, response: aiohttp.ClientResponse, request_id: str
    ) -> RateLimitInfo | None:
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

        if headers.get("X-RateLimit-Global") == "true":
            self._rate_limits.update_global(reset)
            self._logger.emit(
                "http.rate_limit.global",
                request_id,
                route=route,
                bucket=bucket,
                reset_after=reset_after,
                remaining=remaining,
                reset_at=reset.isoformat(),
            )

        self._rate_limits.update_route(route, info)

        if remaining == 0:
            self._logger.emit(
                "http.rate_limit.route",
                request_id,
                route=route,
                bucket=bucket,
                reset_after=reset_after,
                remaining=remaining,
                wait_time_s=reset_after,
            )
            await asyncio.sleep(reset_after)

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
        last_exception: Exception | None = None
        request_headers = sanitize_headers(kwargs.get("headers"))
        has_params = kwargs.get("params") is not None

        for attempt in range(self._retry.max_retries):
            started = time.perf_counter()
            self._logger.emit(
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
                session = await self._transport.get_session()
                url = f"{self.config.base_url}/v{self.config.api_version}{endpoint}"
                proxy = self.config.proxy
                proxy_auth = self.config.proxy_auth

                async with session.request(
                    method,
                    url,
                    proxy=proxy,
                    proxy_auth=proxy_auth,
                    **kwargs,
                ) as response:
                    await self._check_rate_limit(endpoint, response, request_id)

                    if response.status >= 500 and self._retry.should_retry(
                        attempt=attempt + 1, status=response.status
                    ):
                        delay = self._retry.delay_for(attempt + 1)
                        self._logger.emit(
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
                    self._logger.emit(
                        "http.request.done",
                        request_id,
                        method=method,
                        route=endpoint,
                        attempt=attempt + 1,
                        status=response.status,
                        duration_ms=duration_ms,
                        rate_limit=extract_rate_limit_fields(dict(response.headers)),
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
                if self._retry.should_retry(attempt=attempt + 1):
                    delay = self._retry.delay_for(attempt + 1)
                    self._logger.emit(
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
                    self._logger.emit(
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


__all__ = ["HTTPClient"]
