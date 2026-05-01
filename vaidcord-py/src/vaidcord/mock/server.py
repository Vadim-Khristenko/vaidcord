from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web

from vaidcord.mock.ui import MOCK_UI_HTML

logger = logging.getLogger(__name__)


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

    def __post_init__(self) -> None:
        self._app.router.add_get("/", self._ui)
        self._app.router.add_get("/api/mock/state", self._mock_state)
        self._app.router.add_post("/api/mock/messages", self._mock_message)
        self._app.router.add_get("/api/v10/gateway/bot", self._gateway_bot)
        self._app.router.add_post("/api/v10/users/@me/channels", self._create_dm)
        self._app.router.add_post("/api/v10/channels/{channel_id}/messages", self._send_message)

    async def _ui(self, request: web.Request) -> web.Response:
        if not self.enable_ui:
            raise web.HTTPNotFound
        self.requests.append({"method": "GET", "path": str(request.rel_url)})
        return web.Response(text=MOCK_UI_HTML, content_type="text/html")

    async def _mock_state(self, request: web.Request) -> web.Response:
        self.requests.append({"method": "GET", "path": str(request.rel_url)})
        return web.json_response(
            {
                "base_url": self.base_url,
                "gateway_url": self.gateway_url,
                "requests": self.requests,
                "messages": self.messages,
            }
        )

    async def _mock_message(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.requests.append({"method": "POST", "path": str(request.rel_url), "json": payload})
        message = self._build_message(
            channel_id=str(payload.get("channel_id", "123")),
            content=str(payload.get("content", "")),
            author={
                "id": str(payload.get("author_id", "2")),
                "username": str(payload.get("author_username", "MockUser")),
                "discriminator": "0",
                "bot": bool(payload.get("author_bot", False)),
            },
        )
        self.messages.append(message)
        return web.json_response(message)

    async def _gateway_bot(self, request: web.Request) -> web.Response:
        self.requests.append({"method": "GET", "path": str(request.rel_url)})
        return web.json_response({"url": self.gateway_url, "shards": 1})

    async def _send_message(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.requests.append({"method": "POST", "path": str(request.rel_url), "json": payload})
        channel_id = request.match_info["channel_id"]
        message = self._build_message(
            channel_id=channel_id,
            content=str(payload.get("content", "")),
            tts=bool(payload.get("tts", False)),
            author={"id": "1", "username": "MockBot", "discriminator": "0", "bot": True},
        )
        self.messages.append(message)
        return web.json_response(message)

    async def _create_dm(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.requests.append({"method": "POST", "path": str(request.rel_url), "json": payload})
        recipient_id = payload.get("recipient_id", "0")
        return web.json_response({"id": str(int(recipient_id) + 1000), "type": 1})

    def _build_message(
        self,
        *,
        channel_id: str,
        content: str,
        author: dict[str, Any],
        tts: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": str(10000 + len(self.messages) + 1),
            "channel_id": channel_id,
            "content": content,
            "tts": tts,
            "timestamp": "2026-04-30T00:00:00Z",
            "author": author,
        }

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
