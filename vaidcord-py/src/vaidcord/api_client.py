from __future__ import annotations

from typing import Any

from vaidcord.http import HTTPClient, HTTPConfig


class APIClient:
    """Discord REST API facade with endpoint helpers on top of HTTPClient."""

    def __init__(self, token: str, *, base_url: str = "https://discord.com/api", api_version: str = "10") -> None:
        self._http = HTTPClient(HTTPConfig(token=token, base_url=base_url, api_version=api_version))

    def set_bot_id(self, bot_id: str | int | None) -> None:
        """Attach bot identity to lower-level HTTP logs."""
        self._http.set_bot_id(bot_id)

    def _normalize_endpoint(self, endpoint: str) -> str:
        if not endpoint.startswith("/"):
            return f"/{endpoint}"
        return endpoint

    async def request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        endpoint = self._normalize_endpoint(endpoint)
        return await self._http.request(method, endpoint, **kwargs)

    async def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", endpoint, **kwargs)

    async def patch(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("PATCH", endpoint, **kwargs)

    async def put(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("PUT", endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("DELETE", endpoint, **kwargs)

    async def send_message(self, channel_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/channels/{channel_id}/messages", json=payload)

    async def list_messages(
        self,
        channel_id: int,
        *,
        limit: int = 50,
        before: int | None = None,
        after: int | None = None,
        around: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        if around is not None:
            params["around"] = around
        return await self.get(f"/channels/{channel_id}/messages", params=params)  # type: ignore[return-value]

    async def fetch_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.get(f"/channels/{channel_id}/messages/{message_id}")

    async def edit_message(
        self,
        channel_id: int,
        message_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.patch(
            f"/channels/{channel_id}/messages/{message_id}",
            json=payload,
        )

    async def delete_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.delete(f"/channels/{channel_id}/messages/{message_id}")

    async def trigger_typing(self, channel_id: int) -> dict[str, Any]:
        return await self.post(f"/channels/{channel_id}/typing")

    async def fetch_channel(self, channel_id: int) -> dict[str, Any]:
        return await self.get(f"/channels/{channel_id}")

    async def modify_channel(self, channel_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.patch(f"/channels/{channel_id}", json=payload)

    async def delete_channel(self, channel_id: int) -> dict[str, Any]:
        return await self.delete(f"/channels/{channel_id}")

    async def fetch_guild(self, guild_id: int) -> dict[str, Any]:
        return await self.get(f"/guilds/{guild_id}")

    async def list_guild_channels(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.get(f"/guilds/{guild_id}/channels")  # type: ignore[return-value]

    async def fetch_user(self, user_id: int) -> dict[str, Any]:
        return await self.get(f"/users/{user_id}")

    async def get_current_user(self) -> dict[str, Any]:
        return await self.get("/users/@me")

    async def modify_current_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.patch("/users/@me", json=payload)

    async def get_current_user_guilds(self, **params: Any) -> list[dict[str, Any]]:
        return await self.get("/users/@me/guilds", params=params)  # type: ignore[return-value]

    async def get_current_user_guild_member(self, guild_id: int) -> dict[str, Any]:
        return await self.get(f"/users/@me/guilds/{guild_id}/member")

    async def leave_guild(self, guild_id: int) -> dict[str, Any]:
        return await self.delete(f"/users/@me/guilds/{guild_id}")

    async def create_dm(self, recipient_id: int) -> dict[str, Any]:
        return await self.post("/users/@me/channels", json={"recipient_id": str(recipient_id)})

    async def close(self) -> None:
        await self._http.close()
