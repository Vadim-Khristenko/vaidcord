from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from vaidcord.errors import create_discord_error

from .config import MockSettings
from .types import MockHTTPResponse


class MockHTTPClient:
    def __init__(self, settings: MockSettings | None = None) -> None:
        self.settings = settings or MockSettings()
        self._responses: dict[str, MockHTTPResponse] = {}
        self._default_response = MockHTTPResponse(
            status=self.settings.default_http_status,
            data={},
        )
        self._request_history: list[dict[str, Any]] = []
        self._rate_limit_remaining = self.settings.default_rate_limit

    def set_response(self, method: str, endpoint: str, response: MockHTTPResponse) -> None:
        self._responses[f"{method.upper()}:{endpoint}"] = response

    def set_default_response(self, response: MockHTTPResponse) -> None:
        self._default_response = response

    def clear_responses(self) -> None:
        self._responses.clear()
        self._request_history.clear()

    def get_request_history(self) -> list[dict[str, Any]]:
        return self._request_history.copy()

    async def request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        self._request_history.append(
            {
                "method": method,
                "endpoint": endpoint,
                "kwargs": kwargs,
                "timestamp": datetime.now(),
            }
        )

        key = f"{method.upper()}:{endpoint}"
        response = self._responses.get(key, self._default_response)

        if self.settings.network_delay > 0:
            await asyncio.sleep(self.settings.network_delay)
        if response.delay > 0:
            await asyncio.sleep(response.delay)

        if response.headers.get("X-RateLimit-Remaining") is None:
            response.headers["X-RateLimit-Remaining"] = str(self._rate_limit_remaining)
            response.headers["X-RateLimit-Limit"] = str(self.settings.default_rate_limit)

        if response.status >= 400:
            error_data = {
                "code": response.error_code or response.status,
                "message": response.error_message or "Mock error",
            }
            if response.status == 429 and "retry_after" not in error_data:
                error_data["retry_after"] = response.headers.get("Retry-After")
            raise create_discord_error(response.status, error_data)

        return response.data
