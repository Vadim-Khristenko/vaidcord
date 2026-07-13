from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from urllib.parse import quote

import aiohttp
from aiohttp import ClientSession

from vaidcord.http import HTTPClient, HTTPConfig
from vaidcord.types.resources import AttachmentFile


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

    @staticmethod
    def _audit_kwargs(reason: str | None) -> dict[str, Any]:
        """Build the X-Audit-Log-Reason header kwargs for a request."""
        if reason is None:
            return {}
        return {"headers": {"X-Audit-Log-Reason": quote(reason, safe="/ ")}}

    @staticmethod
    def _build_attachment_form(
        payload: dict[str, Any] | None,
        files: Sequence[AttachmentFile],
    ) -> aiohttp.FormData:
        """Build a multipart form with a ``payload_json`` part and ``files[n]`` parts.

        The JSON payload's ``attachments`` array is extended with one
        descriptor per uploaded file (id, filename, optional description),
        as required by Discord's file upload contract.
        """
        form = aiohttp.FormData(quote_fields=False)
        body = dict(payload or {})
        attachments = list(body.get("attachments") or [])
        for index, file in enumerate(files):
            descriptor: dict[str, Any] = {
                "id": index,
                "filename": file.upload_filename,
            }
            if file.description is not None:
                descriptor["description"] = file.description
            attachments.append(descriptor)
        body["attachments"] = attachments
        form.add_field("payload_json", json.dumps(body), content_type="application/json")
        for index, file in enumerate(files):
            form.add_field(
                f"files[{index}]",
                file.read_bytes(),
                filename=file.upload_filename,
                content_type=file.content_type,
            )
        return form

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

    async def send_message(
        self,
        channel_id: int,
        payload: dict[str, Any],
        *,
        files: Sequence[AttachmentFile] | None = None,
    ) -> dict[str, Any]:
        """Create a message. Route: POST /channels/{channel_id}/messages.

        Pass ``files=[AttachmentFile(...)]`` to upload attachments via
        multipart/form-data alongside the JSON payload.
        """
        if files:
            return await self.post(
                f"/channels/{channel_id}/messages",
                data=self._build_attachment_form(payload, files),
            )
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
        *,
        files: Sequence[AttachmentFile] | None = None,
    ) -> dict[str, Any]:
        """Edit a message. Route: PATCH /channels/{channel_id}/messages/{message_id}."""
        if files:
            return await self.patch(
                f"/channels/{channel_id}/messages/{message_id}",
                data=self._build_attachment_form(payload, files),
            )
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
        *,
        files: Sequence[AttachmentFile] | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """Execute a webhook. Route: POST /webhooks/{webhook_id}/{webhook_token}."""
        if files:
            return await self.post(
                f"/webhooks/{webhook_id}/{token}",
                data=self._build_attachment_form(payload, files),
                params=params or None,
            )
        return await self.post(f"/webhooks/{webhook_id}/{token}", json=payload, params=params or None)

    async def fetch_webhook_message(self, webhook_id: int, token: str, message_id: int) -> dict[str, Any]:
        return await self.get(f"/webhooks/{webhook_id}/{token}/messages/{message_id}")

    async def edit_webhook_message(
        self,
        webhook_id: int,
        token: str,
        message_id: int,
        payload: dict[str, Any],
        *,
        files: Sequence[AttachmentFile] | None = None,
    ) -> dict[str, Any]:
        """Edit a webhook message. Route: PATCH /webhooks/{id}/{token}/messages/{message_id}."""
        if files:
            return await self.patch(
                f"/webhooks/{webhook_id}/{token}/messages/{message_id}",
                data=self._build_attachment_form(payload, files),
            )
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
        *,
        files: Sequence[AttachmentFile] | None = None,
    ) -> dict[str, Any]:
        """Create an interaction response. Route: POST /interactions/{id}/{token}/callback."""
        if files:
            return await self.post(
                f"/interactions/{interaction_id}/{interaction_token}/callback",
                data=self._build_attachment_form(payload, files),
            )
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
        *,
        files: Sequence[AttachmentFile] | None = None,
    ) -> dict[str, Any]:
        """Edit the original interaction response.

        Route: PATCH /webhooks/{application_id}/{interaction_token}/messages/@original.
        """
        if files:
            return await self.patch(
                f"/webhooks/{application_id}/{interaction_token}/messages/@original",
                data=self._build_attachment_form(payload, files),
            )
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
        *,
        files: Sequence[AttachmentFile] | None = None,
    ) -> dict[str, Any]:
        """Create a followup message. Route: POST /webhooks/{application_id}/{token}."""
        if files:
            return await self.post(
                f"/webhooks/{application_id}/{interaction_token}",
                data=self._build_attachment_form(payload, files),
            )
        return await self.post(f"/webhooks/{application_id}/{interaction_token}", json=payload)

    async def edit_followup_message(
        self,
        application_id: int,
        interaction_token: str,
        message_id: int,
        payload: dict[str, Any],
        *,
        files: Sequence[AttachmentFile] | None = None,
    ) -> dict[str, Any]:
        """Edit a followup message. Route: PATCH /webhooks/{app_id}/{token}/messages/{message_id}."""
        if files:
            return await self.patch(
                f"/webhooks/{application_id}/{interaction_token}/messages/{message_id}",
                data=self._build_attachment_form(payload, files),
            )
        return await self.patch(f"/webhooks/{application_id}/{interaction_token}/messages/{message_id}", json=payload)

    async def delete_followup_message(
        self,
        application_id: int,
        interaction_token: str,
        message_id: int,
    ) -> dict[str, Any]:
        return await self.delete(f"/webhooks/{application_id}/{interaction_token}/messages/{message_id}")

    # ------------------------------------------------------------------ #
    # Emojis                                                             #
    # ------------------------------------------------------------------ #

    async def get_guild_emoji(self, guild_id: int | str, emoji_id: int | str) -> dict[str, Any]:
        """Get a guild emoji. Route: GET /guilds/{guild_id}/emojis/{emoji_id}."""
        return await self.get(f"/guilds/{guild_id}/emojis/{emoji_id}")

    async def create_guild_emoji(
        self,
        guild_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Create a guild emoji. Route: POST /guilds/{guild_id}/emojis."""
        return await self.post(f"/guilds/{guild_id}/emojis", json=payload, **self._audit_kwargs(reason))

    async def modify_guild_emoji(
        self,
        guild_id: int | str,
        emoji_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Modify a guild emoji. Route: PATCH /guilds/{guild_id}/emojis/{emoji_id}."""
        return await self.patch(
            f"/guilds/{guild_id}/emojis/{emoji_id}",
            json=payload,
            **self._audit_kwargs(reason),
        )

    async def delete_guild_emoji(
        self,
        guild_id: int | str,
        emoji_id: int | str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Delete a guild emoji. Route: DELETE /guilds/{guild_id}/emojis/{emoji_id}."""
        return await self.delete(f"/guilds/{guild_id}/emojis/{emoji_id}", **self._audit_kwargs(reason))

    async def list_application_emojis(self, application_id: int | str) -> dict[str, Any]:
        """List application emojis. Route: GET /applications/{application_id}/emojis."""
        return await self.get(f"/applications/{application_id}/emojis")

    async def get_application_emoji(
        self,
        application_id: int | str,
        emoji_id: int | str,
    ) -> dict[str, Any]:
        """Get an application emoji. Route: GET /applications/{application_id}/emojis/{emoji_id}."""
        return await self.get(f"/applications/{application_id}/emojis/{emoji_id}")

    async def create_application_emoji(
        self,
        application_id: int | str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Create an application emoji. Route: POST /applications/{application_id}/emojis."""
        return await self.post(f"/applications/{application_id}/emojis", json=payload)

    async def modify_application_emoji(
        self,
        application_id: int | str,
        emoji_id: int | str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Modify an application emoji. Route: PATCH /applications/{app_id}/emojis/{emoji_id}."""
        return await self.patch(f"/applications/{application_id}/emojis/{emoji_id}", json=payload)

    async def delete_application_emoji(
        self,
        application_id: int | str,
        emoji_id: int | str,
    ) -> dict[str, Any]:
        """Delete an application emoji. Route: DELETE /applications/{app_id}/emojis/{emoji_id}."""
        return await self.delete(f"/applications/{application_id}/emojis/{emoji_id}")

    # ------------------------------------------------------------------ #
    # Stickers                                                           #
    # ------------------------------------------------------------------ #

    async def get_sticker(self, sticker_id: int | str) -> dict[str, Any]:
        """Get a sticker. Route: GET /stickers/{sticker_id}."""
        return await self.get(f"/stickers/{sticker_id}")

    async def list_sticker_packs(self) -> dict[str, Any]:
        """List available sticker packs. Route: GET /sticker-packs."""
        return await self.get("/sticker-packs")

    async def get_sticker_pack(self, pack_id: int | str) -> dict[str, Any]:
        """Get a sticker pack. Route: GET /sticker-packs/{pack_id}."""
        return await self.get(f"/sticker-packs/{pack_id}")

    async def get_guild_sticker(self, guild_id: int | str, sticker_id: int | str) -> dict[str, Any]:
        """Get a guild sticker. Route: GET /guilds/{guild_id}/stickers/{sticker_id}."""
        return await self.get(f"/guilds/{guild_id}/stickers/{sticker_id}")

    async def create_guild_sticker(
        self,
        guild_id: int | str,
        *,
        name: str,
        description: str,
        tags: str,
        file: AttachmentFile,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Create a guild sticker (multipart). Route: POST /guilds/{guild_id}/stickers."""
        form = aiohttp.FormData(quote_fields=False)
        form.add_field("name", name)
        form.add_field("description", description)
        form.add_field("tags", tags)
        form.add_field(
            "file",
            file.read_bytes(),
            filename=file.upload_filename,
            content_type=file.content_type,
        )
        return await self.post(f"/guilds/{guild_id}/stickers", data=form, **self._audit_kwargs(reason))

    async def modify_guild_sticker(
        self,
        guild_id: int | str,
        sticker_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Modify a guild sticker. Route: PATCH /guilds/{guild_id}/stickers/{sticker_id}."""
        return await self.patch(
            f"/guilds/{guild_id}/stickers/{sticker_id}",
            json=payload,
            **self._audit_kwargs(reason),
        )

    async def delete_guild_sticker(
        self,
        guild_id: int | str,
        sticker_id: int | str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Delete a guild sticker. Route: DELETE /guilds/{guild_id}/stickers/{sticker_id}."""
        return await self.delete(f"/guilds/{guild_id}/stickers/{sticker_id}", **self._audit_kwargs(reason))

    # ------------------------------------------------------------------ #
    # Auto Moderation                                                    #
    # ------------------------------------------------------------------ #

    async def list_auto_moderation_rules(self, guild_id: int | str) -> list[dict[str, Any]]:
        """List auto-moderation rules. Route: GET /guilds/{guild_id}/auto-moderation/rules."""
        return await self.get(f"/guilds/{guild_id}/auto-moderation/rules")  # type: ignore[return-value]

    async def get_auto_moderation_rule(self, guild_id: int | str, rule_id: int | str) -> dict[str, Any]:
        """Get an auto-moderation rule. Route: GET /guilds/{guild_id}/auto-moderation/rules/{rule_id}."""
        return await self.get(f"/guilds/{guild_id}/auto-moderation/rules/{rule_id}")

    async def create_auto_moderation_rule(
        self,
        guild_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Create an auto-moderation rule. Route: POST /guilds/{guild_id}/auto-moderation/rules."""
        return await self.post(
            f"/guilds/{guild_id}/auto-moderation/rules",
            json=payload,
            **self._audit_kwargs(reason),
        )

    async def modify_auto_moderation_rule(
        self,
        guild_id: int | str,
        rule_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Modify an auto-moderation rule. Route: PATCH /guilds/{gid}/auto-moderation/rules/{rule_id}."""
        return await self.patch(
            f"/guilds/{guild_id}/auto-moderation/rules/{rule_id}",
            json=payload,
            **self._audit_kwargs(reason),
        )

    async def delete_auto_moderation_rule(
        self,
        guild_id: int | str,
        rule_id: int | str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Delete an auto-moderation rule. Route: DELETE /guilds/{gid}/auto-moderation/rules/{rule_id}."""
        return await self.delete(
            f"/guilds/{guild_id}/auto-moderation/rules/{rule_id}",
            **self._audit_kwargs(reason),
        )

    # ------------------------------------------------------------------ #
    # Stage Instances                                                    #
    # ------------------------------------------------------------------ #

    async def create_stage_instance(
        self,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Create a stage instance. Route: POST /stage-instances."""
        return await self.post("/stage-instances", json=payload, **self._audit_kwargs(reason))

    async def get_stage_instance(self, channel_id: int | str) -> dict[str, Any]:
        """Get a stage instance. Route: GET /stage-instances/{channel_id}."""
        return await self.get(f"/stage-instances/{channel_id}")

    async def modify_stage_instance(
        self,
        channel_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Modify a stage instance. Route: PATCH /stage-instances/{channel_id}."""
        return await self.patch(f"/stage-instances/{channel_id}", json=payload, **self._audit_kwargs(reason))

    async def delete_stage_instance(
        self,
        channel_id: int | str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Delete a stage instance. Route: DELETE /stage-instances/{channel_id}."""
        return await self.delete(f"/stage-instances/{channel_id}", **self._audit_kwargs(reason))

    # ------------------------------------------------------------------ #
    # Entitlements & Monetization                                        #
    # ------------------------------------------------------------------ #

    async def list_entitlements(self, application_id: int | str, **params: Any) -> list[dict[str, Any]]:
        """List entitlements. Route: GET /applications/{application_id}/entitlements.

        Supported filters: user_id, sku_ids, before, after, limit, guild_id,
        exclude_ended, exclude_deleted.
        """
        return await self.get(f"/applications/{application_id}/entitlements", params=params or None)  # type: ignore[return-value]

    async def get_entitlement(
        self,
        application_id: int | str,
        entitlement_id: int | str,
    ) -> dict[str, Any]:
        """Get an entitlement. Route: GET /applications/{app_id}/entitlements/{entitlement_id}."""
        return await self.get(f"/applications/{application_id}/entitlements/{entitlement_id}")

    async def consume_entitlement(
        self,
        application_id: int | str,
        entitlement_id: int | str,
    ) -> dict[str, Any]:
        """Consume an entitlement. Route: POST /applications/{app_id}/entitlements/{id}/consume."""
        return await self.post(f"/applications/{application_id}/entitlements/{entitlement_id}/consume")

    async def create_test_entitlement(
        self,
        application_id: int | str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a test entitlement. Route: POST /applications/{application_id}/entitlements."""
        return await self.post(f"/applications/{application_id}/entitlements", json=payload)

    async def delete_test_entitlement(
        self,
        application_id: int | str,
        entitlement_id: int | str,
    ) -> dict[str, Any]:
        """Delete a test entitlement. Route: DELETE /applications/{app_id}/entitlements/{id}."""
        return await self.delete(f"/applications/{application_id}/entitlements/{entitlement_id}")

    async def list_skus(self, application_id: int | str) -> list[dict[str, Any]]:
        """List SKUs. Route: GET /applications/{application_id}/skus."""
        return await self.get(f"/applications/{application_id}/skus")  # type: ignore[return-value]

    async def list_sku_subscriptions(self, sku_id: int | str, **params: Any) -> list[dict[str, Any]]:
        """List SKU subscriptions. Route: GET /skus/{sku_id}/subscriptions.

        Supported filters: before, after, limit, user_id.
        """
        return await self.get(f"/skus/{sku_id}/subscriptions", params=params or None)  # type: ignore[return-value]

    async def get_sku_subscription(
        self,
        sku_id: int | str,
        subscription_id: int | str,
    ) -> dict[str, Any]:
        """Get a SKU subscription. Route: GET /skus/{sku_id}/subscriptions/{subscription_id}."""
        return await self.get(f"/skus/{sku_id}/subscriptions/{subscription_id}")

    # ------------------------------------------------------------------ #
    # Soundboard                                                         #
    # ------------------------------------------------------------------ #

    async def list_default_soundboard_sounds(self) -> list[dict[str, Any]]:
        """List default soundboard sounds. Route: GET /soundboard-default-sounds."""
        return await self.get("/soundboard-default-sounds")  # type: ignore[return-value]

    async def list_guild_soundboard_sounds(self, guild_id: int | str) -> dict[str, Any]:
        """List guild soundboard sounds. Route: GET /guilds/{guild_id}/soundboard-sounds."""
        return await self.get(f"/guilds/{guild_id}/soundboard-sounds")

    async def get_guild_soundboard_sound(
        self,
        guild_id: int | str,
        sound_id: int | str,
    ) -> dict[str, Any]:
        """Get a guild soundboard sound. Route: GET /guilds/{guild_id}/soundboard-sounds/{sound_id}."""
        return await self.get(f"/guilds/{guild_id}/soundboard-sounds/{sound_id}")

    async def create_guild_soundboard_sound(
        self,
        guild_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Create a guild soundboard sound. Route: POST /guilds/{guild_id}/soundboard-sounds."""
        return await self.post(
            f"/guilds/{guild_id}/soundboard-sounds",
            json=payload,
            **self._audit_kwargs(reason),
        )

    async def modify_guild_soundboard_sound(
        self,
        guild_id: int | str,
        sound_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Modify a guild soundboard sound. Route: PATCH /guilds/{gid}/soundboard-sounds/{sound_id}."""
        return await self.patch(
            f"/guilds/{guild_id}/soundboard-sounds/{sound_id}",
            json=payload,
            **self._audit_kwargs(reason),
        )

    async def delete_guild_soundboard_sound(
        self,
        guild_id: int | str,
        sound_id: int | str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Delete a guild soundboard sound. Route: DELETE /guilds/{gid}/soundboard-sounds/{sound_id}."""
        return await self.delete(
            f"/guilds/{guild_id}/soundboard-sounds/{sound_id}",
            **self._audit_kwargs(reason),
        )

    async def send_soundboard_sound(
        self,
        channel_id: int | str,
        sound_id: int | str,
        *,
        source_guild_id: int | str | None = None,
    ) -> dict[str, Any]:
        """Send a soundboard sound. Route: POST /channels/{channel_id}/send-soundboard-sound."""
        payload: dict[str, Any] = {"sound_id": str(sound_id)}
        if source_guild_id is not None:
            payload["source_guild_id"] = str(source_guild_id)
        return await self.post(f"/channels/{channel_id}/send-soundboard-sound", json=payload)

    # ------------------------------------------------------------------ #
    # Guild lifecycle & management                                       #
    # ------------------------------------------------------------------ #

    async def create_guild(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a guild. Route: POST /guilds."""
        return await self.post("/guilds", json=payload)

    async def modify_guild(
        self,
        guild_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Modify a guild. Route: PATCH /guilds/{guild_id}."""
        return await self.patch(f"/guilds/{guild_id}", json=payload, **self._audit_kwargs(reason))

    async def delete_guild(self, guild_id: int | str) -> dict[str, Any]:
        """Delete a guild. Route: DELETE /guilds/{guild_id}."""
        return await self.delete(f"/guilds/{guild_id}")

    async def get_guild_prune_count(self, guild_id: int | str, **params: Any) -> dict[str, Any]:
        """Get the guild prune count. Route: GET /guilds/{guild_id}/prune.

        Supported filters: days, include_roles (comma-delimited snowflakes).
        """
        return await self.get(f"/guilds/{guild_id}/prune", params=params or None)

    async def begin_guild_prune(
        self,
        guild_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Begin a guild prune. Route: POST /guilds/{guild_id}/prune."""
        return await self.post(f"/guilds/{guild_id}/prune", json=payload, **self._audit_kwargs(reason))

    async def list_guild_voice_regions(self, guild_id: int | str) -> list[dict[str, Any]]:
        """List guild voice regions. Route: GET /guilds/{guild_id}/regions."""
        return await self.get(f"/guilds/{guild_id}/regions")  # type: ignore[return-value]

    async def list_guild_integrations(self, guild_id: int | str) -> list[dict[str, Any]]:
        """List guild integrations. Route: GET /guilds/{guild_id}/integrations."""
        return await self.get(f"/guilds/{guild_id}/integrations")  # type: ignore[return-value]

    async def delete_guild_integration(
        self,
        guild_id: int | str,
        integration_id: int | str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Delete a guild integration. Route: DELETE /guilds/{guild_id}/integrations/{integration_id}."""
        return await self.delete(
            f"/guilds/{guild_id}/integrations/{integration_id}",
            **self._audit_kwargs(reason),
        )

    async def get_guild_widget_settings(self, guild_id: int | str) -> dict[str, Any]:
        """Get guild widget settings. Route: GET /guilds/{guild_id}/widget."""
        return await self.get(f"/guilds/{guild_id}/widget")

    async def modify_guild_widget(
        self,
        guild_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Modify guild widget settings. Route: PATCH /guilds/{guild_id}/widget."""
        return await self.patch(f"/guilds/{guild_id}/widget", json=payload, **self._audit_kwargs(reason))

    async def get_guild_widget(self, guild_id: int | str) -> dict[str, Any]:
        """Get the guild widget JSON. Route: GET /guilds/{guild_id}/widget.json."""
        return await self.get(f"/guilds/{guild_id}/widget.json")

    def guild_widget_image_url(self, guild_id: int | str, *, style: str | None = None) -> str:
        """Build the guild widget image URL. Route: GET /guilds/{guild_id}/widget.png.

        Returns the fully-qualified URL (the endpoint serves a PNG, not JSON,
        so it is exposed as a URL helper rather than an API call).
        """
        config = self._http.config
        url = f"{config.base_url}/v{config.api_version}/guilds/{guild_id}/widget.png"
        if style is not None:
            url += f"?style={quote(style, safe='')}"
        return url

    async def get_guild_vanity_url(self, guild_id: int | str) -> dict[str, Any]:
        """Get the guild vanity URL. Route: GET /guilds/{guild_id}/vanity-url."""
        return await self.get(f"/guilds/{guild_id}/vanity-url")

    async def get_guild_welcome_screen(self, guild_id: int | str) -> dict[str, Any]:
        """Get the guild welcome screen. Route: GET /guilds/{guild_id}/welcome-screen."""
        return await self.get(f"/guilds/{guild_id}/welcome-screen")

    async def modify_guild_welcome_screen(
        self,
        guild_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Modify the guild welcome screen. Route: PATCH /guilds/{guild_id}/welcome-screen."""
        return await self.patch(
            f"/guilds/{guild_id}/welcome-screen",
            json=payload,
            **self._audit_kwargs(reason),
        )

    async def get_guild_onboarding(self, guild_id: int | str) -> dict[str, Any]:
        """Get guild onboarding. Route: GET /guilds/{guild_id}/onboarding."""
        return await self.get(f"/guilds/{guild_id}/onboarding")

    async def modify_guild_onboarding(
        self,
        guild_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Modify guild onboarding. Route: PUT /guilds/{guild_id}/onboarding."""
        return await self.put(f"/guilds/{guild_id}/onboarding", json=payload, **self._audit_kwargs(reason))

    async def modify_guild_mfa_level(
        self,
        guild_id: int | str,
        level: int,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Modify the guild MFA level. Route: POST /guilds/{guild_id}/mfa."""
        return await self.post(f"/guilds/{guild_id}/mfa", json={"level": level}, **self._audit_kwargs(reason))

    async def get_guild_audit_log(
        self,
        guild_id: int | str,
        *,
        user_id: int | str | None = None,
        action_type: int | None = None,
        before: int | str | None = None,
        after: int | str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Get the guild audit log. Route: GET /guilds/{guild_id}/audit-logs."""
        params: dict[str, Any] = {}
        if user_id is not None:
            params["user_id"] = str(user_id)
        if action_type is not None:
            params["action_type"] = action_type
        if before is not None:
            params["before"] = str(before)
        if after is not None:
            params["after"] = str(after)
        if limit is not None:
            params["limit"] = limit
        return await self.get(f"/guilds/{guild_id}/audit-logs", params=params or None)

    async def list_active_guild_threads(self, guild_id: int | str) -> dict[str, Any]:
        """List active guild threads. Route: GET /guilds/{guild_id}/threads/active."""
        return await self.get(f"/guilds/{guild_id}/threads/active")

    async def bulk_guild_ban(
        self,
        guild_id: int | str,
        user_ids: list[int | str],
        *,
        delete_message_seconds: int = 0,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Bulk ban users. Route: POST /guilds/{guild_id}/bulk-ban."""
        payload = {
            "user_ids": [str(user_id) for user_id in user_ids],
            "delete_message_seconds": delete_message_seconds,
        }
        return await self.post(f"/guilds/{guild_id}/bulk-ban", json=payload, **self._audit_kwargs(reason))

    # ------------------------------------------------------------------ #
    # Members & roles                                                    #
    # ------------------------------------------------------------------ #

    async def search_guild_members(
        self,
        guild_id: int | str,
        query: str,
        *,
        limit: int = 1,
    ) -> list[dict[str, Any]]:
        """Search guild members by username/nickname. Route: GET /guilds/{guild_id}/members/search."""
        return await self.get(
            f"/guilds/{guild_id}/members/search",
            params={"query": query, "limit": limit},
        )  # type: ignore[return-value]

    async def modify_current_member(
        self,
        guild_id: int | str,
        payload: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Modify the current member. Route: PATCH /guilds/{guild_id}/members/@me."""
        return await self.patch(f"/guilds/{guild_id}/members/@me", json=payload, **self._audit_kwargs(reason))

    async def add_guild_member_role(
        self,
        guild_id: int | str,
        user_id: int | str,
        role_id: int | str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Add a role to a member. Route: PUT /guilds/{guild_id}/members/{user_id}/roles/{role_id}."""
        return await self.put(
            f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            **self._audit_kwargs(reason),
        )

    async def remove_guild_member_role(
        self,
        guild_id: int | str,
        user_id: int | str,
        role_id: int | str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Remove a role from a member. Route: DELETE /guilds/{gid}/members/{uid}/roles/{role_id}."""
        return await self.delete(
            f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            **self._audit_kwargs(reason),
        )

    async def get_guild_role(self, guild_id: int | str, role_id: int | str) -> dict[str, Any]:
        """Get a guild role. Route: GET /guilds/{guild_id}/roles/{role_id}."""
        return await self.get(f"/guilds/{guild_id}/roles/{role_id}")

    # ------------------------------------------------------------------ #
    # Application commands (guild-scoped + permissions)                  #
    # ------------------------------------------------------------------ #

    async def fetch_guild_command(
        self,
        application_id: int | str,
        guild_id: int | str,
        command_id: int | str,
    ) -> dict[str, Any]:
        """Get a guild command. Route: GET /applications/{app_id}/guilds/{gid}/commands/{command_id}."""
        return await self.get(f"/applications/{application_id}/guilds/{guild_id}/commands/{command_id}")

    async def edit_guild_command(
        self,
        application_id: int | str,
        guild_id: int | str,
        command_id: int | str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Edit a guild command. Route: PATCH /applications/{app_id}/guilds/{gid}/commands/{cmd_id}."""
        return await self.patch(
            f"/applications/{application_id}/guilds/{guild_id}/commands/{command_id}",
            json=payload,
        )

    async def delete_guild_command(
        self,
        application_id: int | str,
        guild_id: int | str,
        command_id: int | str,
    ) -> dict[str, Any]:
        """Delete a guild command. Route: DELETE /applications/{app_id}/guilds/{gid}/commands/{cmd_id}."""
        return await self.delete(f"/applications/{application_id}/guilds/{guild_id}/commands/{command_id}")

    async def get_guild_command_permissions(
        self,
        application_id: int | str,
        guild_id: int | str,
    ) -> list[dict[str, Any]]:
        """Get permissions for all commands in a guild.

        Route: GET /applications/{application_id}/guilds/{guild_id}/commands/permissions.
        """
        return await self.get(
            f"/applications/{application_id}/guilds/{guild_id}/commands/permissions"
        )  # type: ignore[return-value]

    async def get_application_command_permissions(
        self,
        application_id: int | str,
        guild_id: int | str,
        command_id: int | str,
    ) -> dict[str, Any]:
        """Get permissions for one command.

        Route: GET /applications/{app_id}/guilds/{gid}/commands/{command_id}/permissions.
        """
        return await self.get(
            f"/applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions"
        )

    async def edit_application_command_permissions(
        self,
        application_id: int | str,
        guild_id: int | str,
        command_id: int | str,
        permissions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Edit permissions for one command.

        Route: PUT /applications/{app_id}/guilds/{gid}/commands/{command_id}/permissions.
        """
        return await self.put(
            f"/applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions",
            json={"permissions": permissions},
        )

    async def batch_edit_application_command_permissions(
        self,
        application_id: int | str,
        guild_id: int | str,
        payload: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Batch edit command permissions.

        Route: PUT /applications/{application_id}/guilds/{guild_id}/commands/permissions.
        """
        return await self.put(
            f"/applications/{application_id}/guilds/{guild_id}/commands/permissions",
            json=payload,
        )  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Application resource                                               #
    # ------------------------------------------------------------------ #

    async def get_current_application(self) -> dict[str, Any]:
        """Get the current application. Route: GET /applications/@me."""
        return await self.get("/applications/@me")

    async def edit_current_application(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Edit the current application. Route: PATCH /applications/@me."""
        return await self.patch("/applications/@me", json=payload)

    async def get_application_role_connection_metadata(
        self,
        application_id: int | str,
    ) -> list[dict[str, Any]]:
        """Get role connection metadata records.

        Route: GET /applications/{application_id}/role-connections/metadata.
        """
        return await self.get(f"/applications/{application_id}/role-connections/metadata")  # type: ignore[return-value]

    async def update_application_role_connection_metadata(
        self,
        application_id: int | str,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Update role connection metadata records.

        Route: PUT /applications/{application_id}/role-connections/metadata.
        """
        return await self.put(
            f"/applications/{application_id}/role-connections/metadata",
            json=records,
        )  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Channels: recipients, positions, thread members, forum threads     #
    # ------------------------------------------------------------------ #

    async def group_dm_add_recipient(
        self,
        channel_id: int | str,
        user_id: int | str,
        *,
        access_token: str,
        nick: str | None = None,
    ) -> dict[str, Any]:
        """Add a recipient to a group DM. Route: PUT /channels/{channel_id}/recipients/{user_id}."""
        payload: dict[str, Any] = {"access_token": access_token}
        if nick is not None:
            payload["nick"] = nick
        return await self.put(f"/channels/{channel_id}/recipients/{user_id}", json=payload)

    async def group_dm_remove_recipient(
        self,
        channel_id: int | str,
        user_id: int | str,
    ) -> dict[str, Any]:
        """Remove a recipient from a group DM. Route: DELETE /channels/{cid}/recipients/{user_id}."""
        return await self.delete(f"/channels/{channel_id}/recipients/{user_id}")

    async def modify_guild_channel_positions(
        self,
        guild_id: int | str,
        positions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Modify guild channel positions. Route: PATCH /guilds/{guild_id}/channels."""
        return await self.patch(f"/guilds/{guild_id}/channels", json=positions)

    async def get_thread_member(
        self,
        channel_id: int | str,
        user_id: int | str,
        *,
        with_member: bool = False,
    ) -> dict[str, Any]:
        """Get a thread member. Route: GET /channels/{channel_id}/thread-members/{user_id}."""
        params = {"with_member": "true"} if with_member else None
        return await self.get(f"/channels/{channel_id}/thread-members/{user_id}", params=params)

    async def list_thread_members(
        self,
        channel_id: int | str,
        *,
        with_member: bool = False,
        after: int | str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List thread members. Route: GET /channels/{channel_id}/thread-members."""
        params: dict[str, Any] = {}
        if with_member:
            params["with_member"] = "true"
        if after is not None:
            params["after"] = str(after)
        if limit is not None:
            params["limit"] = limit
        return await self.get(f"/channels/{channel_id}/thread-members", params=params or None)  # type: ignore[return-value]

    async def start_thread_in_forum(
        self,
        channel_id: int | str,
        payload: dict[str, Any],
        *,
        files: Sequence[AttachmentFile] | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Start a thread in a forum or media channel. Route: POST /channels/{channel_id}/threads.

        ``payload`` must include a ``message`` object (first-message params);
        pass ``files=[...]`` to attach uploads via multipart/form-data.
        """
        if files:
            return await self.post(
                f"/channels/{channel_id}/threads",
                data=self._build_attachment_form(payload, files),
                **self._audit_kwargs(reason),
            )
        return await self.post(f"/channels/{channel_id}/threads", json=payload, **self._audit_kwargs(reason))

    # ------------------------------------------------------------------ #
    # Voice                                                              #
    # ------------------------------------------------------------------ #

    async def list_voice_regions(self) -> list[dict[str, Any]]:
        """List all voice regions. Route: GET /voice/regions."""
        return await self.get("/voice/regions")  # type: ignore[return-value]

    async def get_current_user_voice_state(self, guild_id: int | str) -> dict[str, Any]:
        """Get the current user's voice state. Route: GET /guilds/{guild_id}/voice-states/@me."""
        return await self.get(f"/guilds/{guild_id}/voice-states/@me")

    async def get_user_voice_state(self, guild_id: int | str, user_id: int | str) -> dict[str, Any]:
        """Get a user's voice state. Route: GET /guilds/{guild_id}/voice-states/{user_id}."""
        return await self.get(f"/guilds/{guild_id}/voice-states/{user_id}")

    async def modify_current_user_voice_state(
        self,
        guild_id: int | str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Modify the current user's voice state. Route: PATCH /guilds/{gid}/voice-states/@me."""
        return await self.patch(f"/guilds/{guild_id}/voice-states/@me", json=payload)

    async def modify_user_voice_state(
        self,
        guild_id: int | str,
        user_id: int | str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Modify a user's voice state. Route: PATCH /guilds/{guild_id}/voice-states/{user_id}."""
        return await self.patch(f"/guilds/{guild_id}/voice-states/{user_id}", json=payload)

    # ------------------------------------------------------------------ #
    # Scheduled events                                                   #
    # ------------------------------------------------------------------ #

    async def get_scheduled_event_users(
        self,
        guild_id: int | str,
        event_id: int | str,
        *,
        limit: int | None = None,
        with_member: bool = False,
        before: int | str | None = None,
        after: int | str | None = None,
    ) -> list[dict[str, Any]]:
        """Get scheduled event users. Route: GET /guilds/{gid}/scheduled-events/{event_id}/users."""
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if with_member:
            params["with_member"] = "true"
        if before is not None:
            params["before"] = str(before)
        if after is not None:
            params["after"] = str(after)
        return await self.get(
            f"/guilds/{guild_id}/scheduled-events/{event_id}/users",
            params=params or None,
        )  # type: ignore[return-value]

    async def close(self) -> None:
        await self._http.close()
