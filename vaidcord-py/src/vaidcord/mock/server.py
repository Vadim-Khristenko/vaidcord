from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web

from vaidcord.mock.ui import MOCK_UI_HTML

logger = logging.getLogger(__name__)


def _copy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items()}


@dataclass
class MockDiscordServer:
    """Aiohttp-based mock Discord server for integration tests and local testing."""

    host: str = "127.0.0.1"
    port: int = 18080
    enable_ui: bool = False
    gateway_url: str = "wss://gateway.discord.gg"
    _app: web.Application = field(default_factory=web.Application, init=False)
    _runner: web.AppRunner | None = field(default=None, init=False)
    _site: web.TCPSite | None = field(default=None, init=False)
    requests: list[dict[str, Any]] = field(default_factory=list, init=False)
    messages: list[dict[str, Any]] = field(default_factory=list, init=False)
    typing_events: list[dict[str, Any]] = field(default_factory=list, init=False)
    users: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    channels: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    guilds: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _messages_by_id: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _current_user: dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._seed_state()
        self._app.router.add_get("/", self._ui)
        self._app.router.add_get("/api/mock/state", self._mock_state)
        self._app.router.add_post("/api/mock/messages", self._mock_message)
        self._app.router.add_post("/api/mock/reset", self._mock_reset)

        self._app.router.add_get("/api/v10/gateway/bot", self._gateway_bot)
        self._app.router.add_get("/api/v10/users/@me", self._get_current_user)
        self._app.router.add_get("/api/v10/users/{user_id}", self._get_user)
        self._app.router.add_get("/api/v10/users/@me/guilds", self._list_current_user_guilds)
        self._app.router.add_get("/api/v10/guilds/{guild_id}", self._get_guild)
        self._app.router.add_get(
            "/api/v10/guilds/{guild_id}/channels",
            self._list_guild_channels,
        )
        self._app.router.add_post("/api/v10/users/@me/channels", self._create_dm)

        self._app.router.add_get("/api/v10/channels/{channel_id}", self._get_channel)
        self._app.router.add_patch("/api/v10/channels/{channel_id}", self._edit_channel)
        self._app.router.add_delete("/api/v10/channels/{channel_id}", self._delete_channel)
        self._app.router.add_get(
            "/api/v10/channels/{channel_id}/messages",
            self._list_messages,
        )
        self._app.router.add_post(
            "/api/v10/channels/{channel_id}/messages",
            self._send_message,
        )
        self._app.router.add_get(
            "/api/v10/channels/{channel_id}/messages/{message_id}",
            self._get_message,
        )
        self._app.router.add_patch(
            "/api/v10/channels/{channel_id}/messages/{message_id}",
            self._edit_message,
        )
        self._app.router.add_delete(
            "/api/v10/channels/{channel_id}/messages/{message_id}",
            self._delete_message,
        )
        self._app.router.add_post(
            "/api/v10/channels/{channel_id}/typing",
            self._trigger_typing,
        )

    def _seed_state(self) -> None:
        self.requests = []
        self.messages = []
        self.typing_events = []
        self._messages_by_id = {}
        self._current_user = {
            "id": "1",
            "username": "MockBot",
            "discriminator": "0",
            "bot": True,
        }
        self.users = {
            "1": _copy_payload(self._current_user),
            "2": {
                "id": "2",
                "username": "MockUser",
                "discriminator": "0",
                "bot": False,
            },
        }
        self.guilds = {
            "999": {
                "id": "999",
                "name": "Mock Guild",
                "owner": True,
                "owner_id": "1",
                "features": [],
                "member_count": 2,
            }
        }
        self.channels = {
            "123": {
                "id": "123",
                "type": 0,
                "name": "general",
                "topic": "Mock Discord workspace",
                "guild_id": "999",
            }
        }

    def _record_request(
        self,
        request: web.Request,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {"method": request.method, "path": str(request.rel_url)}
        if payload is not None:
            entry["json"] = payload
        self.requests.append(entry)

    def _ensure_user(
        self,
        user_id: str,
        *,
        username: str | None = None,
        bot: bool = False,
    ) -> dict[str, Any]:
        existing = self.users.get(user_id)
        if existing is not None:
            if username:
                existing["username"] = username
            existing["bot"] = bot
            return existing
        user = {
            "id": user_id,
            "username": username or f"User{user_id}",
            "discriminator": "0",
            "bot": bot,
        }
        self.users[user_id] = user
        return user

    def _ensure_guild(self, guild_id: str, *, name: str | None = None) -> dict[str, Any]:
        existing = self.guilds.get(guild_id)
        if existing is not None:
            if name:
                existing["name"] = name
            return existing
        guild = {
            "id": guild_id,
            "name": name or f"Guild {guild_id}",
            "owner": False,
            "owner_id": "1",
            "features": [],
            "member_count": len(self.users),
        }
        self.guilds[guild_id] = guild
        return guild

    def _ensure_channel(
        self,
        channel_id: str,
        *,
        channel_type: int = 0,
        name: str | None = None,
        guild_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self.channels.get(channel_id)
        if existing is not None:
            if name:
                existing["name"] = name
            if guild_id is not None:
                existing["guild_id"] = guild_id
            return existing
        channel = {
            "id": channel_id,
            "type": channel_type,
            "name": name or f"channel-{channel_id}",
        }
        if guild_id is not None:
            channel["guild_id"] = guild_id
        self.channels[channel_id] = channel
        return channel

    async def _ui(self, request: web.Request) -> web.Response:
        if not self.enable_ui:
            raise web.HTTPNotFound
        self._record_request(request)
        return web.Response(text=MOCK_UI_HTML, content_type="text/html")

    async def _mock_state(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(
            {
                "base_url": self.base_url,
                "gateway_url": self.gateway_url,
                "current_user": self._current_user,
                "requests": self.requests,
                "messages": self.messages,
                "typing_events": self.typing_events,
                "users": list(self.users.values()),
                "channels": list(self.channels.values()),
                "guilds": list(self.guilds.values()),
            }
        )

    async def _mock_reset(self, request: web.Request) -> web.Response:
        self._record_request(request)
        self._seed_state()
        return web.json_response({"ok": True})

    async def _mock_message(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self._record_request(request, payload=payload)
        channel_id = str(payload.get("channel_id", "123"))
        guild_id = payload.get("guild_id")
        guild_name = payload.get("guild_name")
        channel_name = payload.get("channel_name")
        author_id = str(payload.get("author_id", "2"))
        author_name = str(payload.get("author_username", "MockUser"))
        author_bot = bool(payload.get("author_bot", False))

        if guild_id is not None:
            self._ensure_guild(str(guild_id), name=str(guild_name) if guild_name else None)
        self._ensure_channel(
            channel_id,
            channel_type=1 if guild_id is None and channel_id.startswith("dm-") else 0,
            name=str(channel_name) if channel_name else None,
            guild_id=str(guild_id) if guild_id is not None else None,
        )
        author = self._ensure_user(author_id, username=author_name, bot=author_bot)
        message = self._build_message(
            channel_id=channel_id,
            content=str(payload.get("content", "")),
            author=author,
            guild_id=str(guild_id) if guild_id is not None else None,
        )
        self.messages.append(message)
        self._messages_by_id[message["id"]] = message
        return web.json_response(message)

    async def _gateway_bot(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response({"url": self.gateway_url, "shards": 1})

    async def _get_current_user(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(self._current_user)

    async def _get_user(self, request: web.Request) -> web.Response:
        self._record_request(request)
        user_id = request.match_info["user_id"]
        user = self.users.get(user_id)
        if user is None:
            raise web.HTTPNotFound(text='{"message":"Unknown User","code":10013}')
        return web.json_response(user)

    async def _list_current_user_guilds(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(list(self.guilds.values()))

    async def _get_guild(self, request: web.Request) -> web.Response:
        self._record_request(request)
        guild_id = request.match_info["guild_id"]
        guild = self.guilds.get(guild_id)
        if guild is None:
            raise web.HTTPNotFound(text='{"message":"Unknown Guild","code":10004}')
        return web.json_response(guild)

    async def _list_guild_channels(self, request: web.Request) -> web.Response:
        self._record_request(request)
        guild_id = request.match_info["guild_id"]
        guild = self.guilds.get(guild_id)
        if guild is None:
            raise web.HTTPNotFound(text='{"message":"Unknown Guild","code":10004}')
        channels = [channel for channel in self.channels.values() if channel.get("guild_id") == guild_id]
        return web.json_response(channels)

    async def _get_channel(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        channel = self.channels.get(channel_id)
        if channel is None:
            raise web.HTTPNotFound(text='{"message":"Unknown Channel","code":10003}')
        return web.json_response(channel)

    async def _edit_channel(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self._record_request(request, payload=payload)
        channel_id = request.match_info["channel_id"]
        channel = self.channels.get(channel_id)
        if channel is None:
            raise web.HTTPNotFound(text='{"message":"Unknown Channel","code":10003}')
        for key in ("name", "topic", "position", "nsfw"):
            if key in payload:
                channel[key] = payload[key]
        return web.json_response(channel)

    async def _delete_channel(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        channel = self.channels.pop(channel_id, None)
        if channel is None:
            raise web.HTTPNotFound(text='{"message":"Unknown Channel","code":10003}')
        removed_ids = {
            message["id"] for message in self.messages if message["channel_id"] == channel_id
        }
        self.messages = [message for message in self.messages if message["channel_id"] != channel_id]
        self.typing_events = [
            event for event in self.typing_events if event["channel_id"] != channel_id
        ]
        for message_id in removed_ids:
            self._messages_by_id.pop(message_id, None)
        return web.json_response(channel)

    async def _list_messages(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        limit = int(request.query.get("limit", "50"))
        messages = [msg for msg in self.messages if msg["channel_id"] == channel_id]
        before = request.query.get("before")
        after = request.query.get("after")
        around = request.query.get("around")
        if before is not None:
            messages = [msg for msg in messages if int(msg["id"]) < int(before)]
        if after is not None:
            messages = [msg for msg in messages if int(msg["id"]) > int(after)]
        if around is not None:
            center_index = next(
                (index for index, msg in enumerate(messages) if msg["id"] == around),
                None,
            )
            if center_index is None:
                messages = []
            else:
                radius = max(1, limit // 2)
                start = max(0, center_index - radius)
                stop = center_index + radius + 1
                messages = messages[start:stop]
        return web.json_response(list(reversed(messages[-limit:])))

    async def _get_message(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        message_id = request.match_info["message_id"]
        message = self._messages_by_id.get(message_id)
        if message is None or message["channel_id"] != channel_id:
            raise web.HTTPNotFound(text='{"message":"Unknown Message","code":10008}')
        return web.json_response(message)

    async def _send_message(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self._record_request(request, payload=payload)
        channel_id = request.match_info["channel_id"]
        channel = self.channels.get(channel_id)
        if channel is None:
            channel = self._ensure_channel(channel_id)
        message = self._build_message(
            channel_id=channel_id,
            content=str(payload.get("content", "")),
            tts=bool(payload.get("tts", False)),
            author=self._current_user,
            guild_id=channel.get("guild_id"),
        )
        if "embeds" in payload:
            message["embeds"] = payload["embeds"]
        if "components" in payload:
            message["components"] = payload["components"]
        if "flags" in payload:
            message["flags"] = payload["flags"]
        if "message_reference" in payload:
            message["message_reference"] = payload["message_reference"]
        if "poll" in payload:
            message["poll"] = payload["poll"]
        self.messages.append(message)
        self._messages_by_id[message["id"]] = message
        return web.json_response(message)

    async def _edit_message(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self._record_request(request, payload=payload)
        channel_id = request.match_info["channel_id"]
        message_id = request.match_info["message_id"]
        message = self._messages_by_id.get(message_id)
        if message is None or message["channel_id"] != channel_id:
            raise web.HTTPNotFound(text='{"message":"Unknown Message","code":10008}')
        for key in ("content", "embeds", "components", "flags"):
            if key in payload:
                message[key] = payload[key]
        return web.json_response(message)

    async def _delete_message(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        message_id = request.match_info["message_id"]
        message = self._messages_by_id.get(message_id)
        if message is None or message["channel_id"] != channel_id:
            raise web.HTTPNotFound(text='{"message":"Unknown Message","code":10008}')
        self.messages = [item for item in self.messages if item["id"] != message_id]
        self._messages_by_id.pop(message_id, None)
        return web.Response(status=204)

    async def _trigger_typing(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        channel = self.channels.get(channel_id)
        if channel is None:
            self._ensure_channel(channel_id)
        self.typing_events.append(
            {
                "channel_id": channel_id,
                "user_id": self._current_user["id"],
                "username": self._current_user["username"],
            }
        )
        return web.Response(status=204)

    async def _create_dm(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self._record_request(request, payload=payload)
        recipient_id = str(payload.get("recipient_id", "0"))
        recipient = self._ensure_user(recipient_id)
        try:
            channel_id = str(int(recipient_id) + 1000)
        except ValueError:
            channel_id = f"dm-{recipient_id}"
        channel = self._ensure_channel(
            channel_id,
            channel_type=1,
            name=f"dm-{recipient['username']}",
        )
        channel["recipients"] = [recipient]
        return web.json_response({"id": channel_id, "type": 1, "recipients": [recipient]})

    def _build_message(
        self,
        *,
        channel_id: str,
        content: str,
        author: dict[str, Any],
        guild_id: str | None = None,
        tts: bool = False,
    ) -> dict[str, Any]:
        message = {
            "id": str(10000 + len(self.messages) + 1),
            "channel_id": channel_id,
            "content": content,
            "tts": tts,
            "timestamp": "2026-04-30T00:00:00Z",
            "author": _copy_payload(author),
        }
        if guild_id is not None:
            message["guild_id"] = guild_id
        return message

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self._sync_bound_port()
        logger.info("MockDiscordServer started on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            logger.info("MockDiscordServer stopped")

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/api"

    @property
    def local_url(self) -> str:
        """Return the browser URL for the optional local test UI."""
        return f"http://{self.host}:{self.port}/"

    def _sync_bound_port(self) -> None:
        server = getattr(self._site, "_server", None)
        sockets = getattr(server, "sockets", None)
        if sockets:
            self.port = int(sockets[0].getsockname()[1])
