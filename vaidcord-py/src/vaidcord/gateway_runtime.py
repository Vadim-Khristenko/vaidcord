from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from vaidcord.bot import Bot

logger = logging.getLogger(__name__)


class GatewayRuntime:
    """Owns gateway lifecycle and websocket state machine for Bot."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._heartbeat_interval: float | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._last_heartbeat_sent_at: float | None = None
        self._latency: float = 0.0

    @property
    def ws(self) -> aiohttp.ClientWebSocketResponse | None:
        return self._ws

    @property
    def latency(self) -> float:
        return self._latency

    async def connect(self) -> None:
        from vaidcord.bot import BotState

        self._bot._state = BotState.CONNECTING
        gateway_info = await self._bot.api_client.request("GET", "/gateway/bot")
        ws_url = gateway_info.get("url", self._bot.config.gateway_url)
        session = await self._bot._create_session()
        self._ws = await session.ws_connect(
            f"{ws_url}?v={self._bot.config.api_version}&encoding=json"
        )

    async def send_payload(self, payload: dict[str, Any]) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.send_json(payload)

    async def identify(self) -> None:
        from vaidcord.bot import BotState

        self._bot._state = BotState.IDENTIFYING
        payload: dict[str, Any] = {
            "op": 2,
            "d": {
                "token": self._bot.config.token,
                "intents": int(self._bot.config.intents),
                "properties": {"os": "linux", "browser": "VaidCord", "device": "VaidCord"},
                "compress": False,
                "large_threshold": 250,
            },
        }
        if self._bot.config.shard_count > 1:
            payload["d"]["shard"] = [self._bot.config.shard_id, self._bot.config.shard_count]
        if self._bot.config.presence:
            payload["d"]["presence"] = self._bot.config.presence
        await self.send_payload(payload)

    async def _heartbeat(self) -> None:
        while self._bot._running and self._heartbeat_interval is not None:
            await asyncio.sleep(self._heartbeat_interval / 1000)
            self._last_heartbeat_sent_at = time.monotonic()
            await self.send_payload({"op": 1, "d": self._bot._sequence})

    async def run(self) -> None:
        if not self._ws:
            return
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                op = data.get("op")
                if op == 0:
                    await self._bot._handle_dispatch(data)
                elif op == 9:
                    from vaidcord.bot import BotState

                    self._bot._state = BotState.RECONNECTING
                    await asyncio.sleep(5)
                    await self.identify()
                elif op == 10:
                    self._heartbeat_interval = data["d"]["heartbeat_interval"]
                    await self.identify()
                    if self._heartbeat_task:
                        self._heartbeat_task.cancel()
                    self._heartbeat_task = asyncio.create_task(self._heartbeat())
                elif op == 11:
                    if self._last_heartbeat_sent_at is not None:
                        self._latency = time.monotonic() - self._last_heartbeat_sent_at
                    logger.debug("Received heartbeat ACK")
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    async def stop(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None
