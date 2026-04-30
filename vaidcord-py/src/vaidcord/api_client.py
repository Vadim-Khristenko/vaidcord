from __future__ import annotations

from typing import Any

from vaidcord.http import HTTPClient, HTTPConfig


class APIClient:
    """Discord REST API client facade built on top of HTTPClient."""

    def __init__(self, token: str, *, base_url: str = "https://discord.com/api", api_version: str = "10") -> None:
        self._http = HTTPClient(HTTPConfig(token=token, base_url=base_url, api_version=api_version))

    async def request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self._http.request(method, endpoint, **kwargs)

    async def close(self) -> None:
        await self._http.close()
