from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

from aiohttp import ClientSession

from vaidcord.http import HTTPClient, HTTPConfig


class APIClient:
    """Discord REST API facade with endpoint helpers on top of HTTPClient."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://discord.com/api",
        api_version: str = "10",
        session_provider: Callable[[], Awaitable[ClientSession]] | None = None,
        session_closer: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._http = HTTPClient(
            HTTPConfig(token=token, base_url=base_url, api_version=api_version),
            session_provider=session_provider,
            session_closer=session_closer,
        )

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

    async def crosspost_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.post(f"/channels/{channel_id}/messages/{message_id}/crosspost")

    async def add_reaction(self, channel_id: int, message_id: int, emoji: str) -> dict[str, Any]:
        return await self.put(
            f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}/@me"
        )

    async def delete_own_reaction(
        self,
        channel_id: int,
        message_id: int,
        emoji: str,
    ) -> dict[str, Any]:
        return await self.delete(
            f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}/@me"
        )

    async def delete_user_reaction(
        self,
        channel_id: int,
        message_id: int,
        emoji: str,
        user_id: int,
    ) -> dict[str, Any]:
        return await self.delete(
            f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}/{user_id}"
        )

    async def list_reactions(
        self,
        channel_id: int,
        message_id: int,
        emoji: str,
        **params: Any,
    ) -> list[dict[str, Any]]:
        return await self.get(
            f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}",
            params=params or None,
        )  # type: ignore[return-value]

    async def clear_reactions(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.delete(f"/channels/{channel_id}/messages/{message_id}/reactions")

    async def clear_reaction(
        self,
        channel_id: int,
        message_id: int,
        emoji: str,
    ) -> dict[str, Any]:
        return await self.delete(
            f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}"
        )

    async def bulk_delete_messages(self, channel_id: int, message_ids: list[int]) -> dict[str, Any]:
        return await self.post(
            f"/channels/{channel_id}/messages/bulk-delete",
            json={"messages": [str(message_id) for message_id in message_ids]},
        )

    async def get_poll_answer_voters(
        self,
        channel_id: int,
        message_id: int,
        answer_id: int,
        **params: Any,
    ) -> dict[str, Any]:
        return await self.get(
            f"/channels/{channel_id}/polls/{message_id}/answers/{answer_id}",
            params=params or None,
        )

    async def end_poll(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.post(f"/channels/{channel_id}/polls/{message_id}/expire")

    async def list_pins(self, channel_id: int) -> list[dict[str, Any]]:
        return await self.get(f"/channels/{channel_id}/pins")  # type: ignore[return-value]

    async def get_channel_pins(
        self,
        channel_id: int,
        *,
        before: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if before is not None:
            params["before"] = before
        return await self.get(f"/channels/{channel_id}/messages/pins", params=params)

    async def pin_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.put(f"/channels/{channel_id}/pins/{message_id}")

    async def unpin_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.delete(f"/channels/{channel_id}/pins/{message_id}")

    async def pin_channel_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.put(f"/channels/{channel_id}/messages/pins/{message_id}")

    async def unpin_channel_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self.delete(f"/channels/{channel_id}/messages/pins/{message_id}")

    async def trigger_typing(self, channel_id: int) -> dict[str, Any]:
        return await self.post(f"/channels/{channel_id}/typing")

    async def fetch_channel(self, channel_id: int) -> dict[str, Any]:
        return await self.get(f"/channels/{channel_id}")

    async def modify_channel(self, channel_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.patch(f"/channels/{channel_id}", json=payload)

    async def delete_channel(self, channel_id: int) -> dict[str, Any]:
        return await self.delete(f"/channels/{channel_id}")

    async def list_channel_invites(self, channel_id: int) -> list[dict[str, Any]]:
        return await self.get(f"/channels/{channel_id}/invites")  # type: ignore[return-value]

    async def create_channel_invite(self, channel_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/channels/{channel_id}/invites", json=payload)

    async def edit_channel_permissions(
        self,
        channel_id: int,
        overwrite_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.put(f"/channels/{channel_id}/permissions/{overwrite_id}", json=payload)

    async def delete_channel_permission(self, channel_id: int, overwrite_id: int) -> dict[str, Any]:
        return await self.delete(f"/channels/{channel_id}/permissions/{overwrite_id}")

    async def follow_news_channel(self, channel_id: int, webhook_channel_id: int) -> dict[str, Any]:
        return await self.post(
            f"/channels/{channel_id}/followers",
            json={"webhook_channel_id": str(webhook_channel_id)},
        )

    async def start_thread_from_message(
        self,
        channel_id: int,
        message_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.post(f"/channels/{channel_id}/messages/{message_id}/threads", json=payload)

    async def start_thread_without_message(self, channel_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/channels/{channel_id}/threads", json=payload)

    async def join_thread(self, channel_id: int) -> dict[str, Any]:
        return await self.put(f"/channels/{channel_id}/thread-members/@me")

    async def leave_thread(self, channel_id: int) -> dict[str, Any]:
        return await self.delete(f"/channels/{channel_id}/thread-members/@me")

    async def add_thread_member(self, channel_id: int, user_id: int) -> dict[str, Any]:
        return await self.put(f"/channels/{channel_id}/thread-members/{user_id}")

    async def remove_thread_member(self, channel_id: int, user_id: int) -> dict[str, Any]:
        return await self.delete(f"/channels/{channel_id}/thread-members/{user_id}")

    async def list_public_archived_threads(self, channel_id: int, **params: Any) -> dict[str, Any]:
        return await self.get(f"/channels/{channel_id}/threads/archived/public", params=params or None)

    async def list_private_archived_threads(self, channel_id: int, **params: Any) -> dict[str, Any]:
        return await self.get(f"/channels/{channel_id}/threads/archived/private", params=params or None)

    async def list_joined_private_archived_threads(self, channel_id: int, **params: Any) -> dict[str, Any]:
        return await self.get(f"/channels/{channel_id}/users/@me/threads/archived/private", params=params or None)

    async def fetch_guild(self, guild_id: int) -> dict[str, Any]:
        return await self.get(f"/guilds/{guild_id}")

    async def fetch_guild_preview(self, guild_id: int) -> dict[str, Any]:
        return await self.get(f"/guilds/{guild_id}/preview")

    async def list_guild_channels(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.get(f"/guilds/{guild_id}/channels")  # type: ignore[return-value]

    async def list_guild_roles(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.get(f"/guilds/{guild_id}/roles")  # type: ignore[return-value]

    async def create_guild_role(self, guild_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/guilds/{guild_id}/roles", json=payload)

    async def modify_guild_role_positions(
        self,
        guild_id: int,
        positions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return await self.patch(f"/guilds/{guild_id}/roles", json=positions)  # type: ignore[return-value]

    async def modify_guild_role(self, guild_id: int, role_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.patch(f"/guilds/{guild_id}/roles/{role_id}", json=payload)

    async def delete_guild_role(self, guild_id: int, role_id: int) -> dict[str, Any]:
        return await self.delete(f"/guilds/{guild_id}/roles/{role_id}")

    async def get_guild_member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.get(f"/guilds/{guild_id}/members/{user_id}")

    async def list_guild_members(self, guild_id: int, **params: Any) -> list[dict[str, Any]]:
        return await self.get(f"/guilds/{guild_id}/members", params=params or None)  # type: ignore[return-value]

    async def add_guild_member(self, guild_id: int, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.put(f"/guilds/{guild_id}/members/{user_id}", json=payload)

    async def modify_guild_member(self, guild_id: int, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.patch(f"/guilds/{guild_id}/members/{user_id}", json=payload)

    async def remove_guild_member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.delete(f"/guilds/{guild_id}/members/{user_id}")

    async def ban_guild_member(self, guild_id: int, user_id: int, **payload: Any) -> dict[str, Any]:
        return await self.put(f"/guilds/{guild_id}/bans/{user_id}", json=payload or None)

    async def unban_guild_member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.delete(f"/guilds/{guild_id}/bans/{user_id}")

    async def list_guild_bans(self, guild_id: int, **params: Any) -> list[dict[str, Any]]:
        return await self.get(f"/guilds/{guild_id}/bans", params=params or None)  # type: ignore[return-value]

    async def get_guild_ban(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.get(f"/guilds/{guild_id}/bans/{user_id}")

    async def list_guild_emojis(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.get(f"/guilds/{guild_id}/emojis")  # type: ignore[return-value]

    async def list_guild_stickers(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.get(f"/guilds/{guild_id}/stickers")  # type: ignore[return-value]

    async def list_scheduled_events(self, guild_id: int, **params: Any) -> list[dict[str, Any]]:
        return await self.get(f"/guilds/{guild_id}/scheduled-events", params=params or None)  # type: ignore[return-value]

    async def create_scheduled_event(self, guild_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/guilds/{guild_id}/scheduled-events", json=payload)

    async def fetch_scheduled_event(self, guild_id: int, event_id: int, **params: Any) -> dict[str, Any]:
        return await self.get(f"/guilds/{guild_id}/scheduled-events/{event_id}", params=params or None)

    async def modify_scheduled_event(
        self,
        guild_id: int,
        event_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.patch(f"/guilds/{guild_id}/scheduled-events/{event_id}", json=payload)

    async def delete_scheduled_event(self, guild_id: int, event_id: int) -> dict[str, Any]:
        return await self.delete(f"/guilds/{guild_id}/scheduled-events/{event_id}")

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

    async def create_group_dm(self, access_tokens: list[str], nicks: dict[str, str]) -> dict[str, Any]:
        return await self.post(
            "/users/@me/channels",
            json={"access_tokens": access_tokens, "nicks": nicks},
        )

    async def get_current_user_connections(self) -> list[dict[str, Any]]:
        return await self.get("/users/@me/connections")  # type: ignore[return-value]

    async def get_current_user_application_role_connection(self, application_id: int) -> dict[str, Any]:
        return await self.get(f"/users/@me/applications/{application_id}/role-connection")

    async def update_current_user_application_role_connection(
        self,
        application_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.put(f"/users/@me/applications/{application_id}/role-connection", json=payload)

    async def fetch_invite(self, invite_code: str, **params: Any) -> dict[str, Any]:
        return await self.get(f"/invites/{invite_code}", params=params or None)

    async def delete_invite(self, invite_code: str) -> dict[str, Any]:
        return await self.delete(f"/invites/{invite_code}")

    async def create_webhook(self, channel_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/channels/{channel_id}/webhooks", json=payload)

    async def list_channel_webhooks(self, channel_id: int) -> list[dict[str, Any]]:
        return await self.get(f"/channels/{channel_id}/webhooks")  # type: ignore[return-value]

    async def list_guild_webhooks(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.get(f"/guilds/{guild_id}/webhooks")  # type: ignore[return-value]

    async def fetch_webhook(self, webhook_id: int, token: str | None = None) -> dict[str, Any]:
        suffix = f"/{token}" if token is not None else ""
        return await self.get(f"/webhooks/{webhook_id}{suffix}")

    async def modify_webhook(
        self,
        webhook_id: int,
        payload: dict[str, Any],
        token: str | None = None,
    ) -> dict[str, Any]:
        suffix = f"/{token}" if token is not None else ""
        return await self.patch(f"/webhooks/{webhook_id}{suffix}", json=payload)

    async def delete_webhook_resource(self, webhook_id: int, token: str | None = None) -> dict[str, Any]:
        suffix = f"/{token}" if token is not None else ""
        return await self.delete(f"/webhooks/{webhook_id}{suffix}")

    async def execute_webhook(
        self,
        webhook_id: int,
        token: str,
        payload: dict[str, Any],
        **params: Any,
    ) -> dict[str, Any]:
        return await self.post(f"/webhooks/{webhook_id}/{token}", json=payload, params=params or None)

    async def fetch_webhook_message(self, webhook_id: int, token: str, message_id: int) -> dict[str, Any]:
        return await self.get(f"/webhooks/{webhook_id}/{token}/messages/{message_id}")

    async def edit_webhook_message(
        self,
        webhook_id: int,
        token: str,
        message_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.patch(f"/webhooks/{webhook_id}/{token}/messages/{message_id}", json=payload)

    async def delete_webhook_message(self, webhook_id: int, token: str, message_id: int) -> dict[str, Any]:
        return await self.delete(f"/webhooks/{webhook_id}/{token}/messages/{message_id}")

    async def list_global_commands(self, application_id: int, **params: Any) -> list[dict[str, Any]]:
        return await self.get(f"/applications/{application_id}/commands", params=params or None)  # type: ignore[return-value]

    async def create_global_command(self, application_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/applications/{application_id}/commands", json=payload)

    async def fetch_global_command(self, application_id: int, command_id: int) -> dict[str, Any]:
        return await self.get(f"/applications/{application_id}/commands/{command_id}")

    async def edit_global_command(
        self,
        application_id: int,
        command_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.patch(f"/applications/{application_id}/commands/{command_id}", json=payload)

    async def delete_global_command(self, application_id: int, command_id: int) -> dict[str, Any]:
        return await self.delete(f"/applications/{application_id}/commands/{command_id}")

    async def bulk_overwrite_global_commands(
        self,
        application_id: int,
        commands: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return await self.put(f"/applications/{application_id}/commands", json=commands)  # type: ignore[return-value]

    async def list_guild_commands(self, application_id: int, guild_id: int, **params: Any) -> list[dict[str, Any]]:
        return await self.get(
            f"/applications/{application_id}/guilds/{guild_id}/commands",
            params=params or None,
        )  # type: ignore[return-value]

    async def create_guild_command(
        self,
        application_id: int,
        guild_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.post(f"/applications/{application_id}/guilds/{guild_id}/commands", json=payload)

    async def bulk_overwrite_guild_commands(
        self,
        application_id: int,
        guild_id: int,
        commands: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return await self.put(f"/applications/{application_id}/guilds/{guild_id}/commands", json=commands)  # type: ignore[return-value]

    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.post(f"/interactions/{interaction_id}/{interaction_token}/callback", json=payload)

    async def get_original_interaction_response(
        self,
        application_id: int,
        interaction_token: str,
    ) -> dict[str, Any]:
        return await self.get(f"/webhooks/{application_id}/{interaction_token}/messages/@original")

    async def edit_original_interaction_response(
        self,
        application_id: int,
        interaction_token: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.patch(f"/webhooks/{application_id}/{interaction_token}/messages/@original", json=payload)

    async def delete_original_interaction_response(
        self,
        application_id: int,
        interaction_token: str,
    ) -> dict[str, Any]:
        return await self.delete(f"/webhooks/{application_id}/{interaction_token}/messages/@original")

    async def create_followup_message(
        self,
        application_id: int,
        interaction_token: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.post(f"/webhooks/{application_id}/{interaction_token}", json=payload)

    async def edit_followup_message(
        self,
        application_id: int,
        interaction_token: str,
        message_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.patch(f"/webhooks/{application_id}/{interaction_token}/messages/{message_id}", json=payload)

    async def delete_followup_message(
        self,
        application_id: int,
        interaction_token: str,
        message_id: int,
    ) -> dict[str, Any]:
        return await self.delete(f"/webhooks/{application_id}/{interaction_token}/messages/{message_id}")

    async def close(self) -> None:
        await self._http.close()
