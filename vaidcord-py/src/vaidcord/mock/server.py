from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)


@dataclass
class MockDiscordServer:
    """Tiny aiohttp-based mock Discord server for integration tests."""

    host: str = "127.0.0.1"
    port: int = 18080
    _app: web.Application = field(default_factory=web.Application, init=False)
    _runner: web.AppRunner | None = field(default=None, init=False)
    _site: web.TCPSite | None = field(default=None, init=False)
    requests: list[dict[str, Any]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self._app.router.add_get("/api/v10/gateway/bot", self._gateway_bot)
        self._app.router.add_post("/api/v10/channels/{channel_id}/messages", self._send_message)

    async def _gateway_bot(self, request: web.Request) -> web.Response:
        self.requests.append({"method": "GET", "path": str(request.rel_url)})
        return web.json_response({"url": "wss://gateway.discord.gg", "shards": 1})

    async def _send_message(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.requests.append({"method": "POST", "path": str(request.rel_url), "json": payload})
        return web.json_response({"id": "mock-msg", **payload})

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        logger.info("MockDiscordServer started on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            logger.info("MockDiscordServer stopped")

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/api"
