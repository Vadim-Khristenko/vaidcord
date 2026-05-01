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


_GATEWAY_CLOSE_HINTS = {
    4013: "invalid intents were sent in IDENTIFY",
    4014: "a privileged intent was requested but is not enabled or approved",
}


class GatewayRuntime:
    """Owns gateway lifecycle and websocket state machine for Bot."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._heartbeat_interval: float | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._last_heartbeat_sent_at: float | None = None
        self._heartbeat_ack_received = True
        self._resume_on_hello = False
        self._latency: float = 0.0

    @property
    def ws(self) -> aiohttp.ClientWebSocketResponse | None:
        return self._ws

    @property
    def latency(self) -> float:
        return self._latency

    async def connect(self, *, resume: bool = False) -> None:
        from vaidcord.bot import BotState

        self._bot._state = BotState.CONNECTING
        if resume and self._bot._resume_gateway_url is not None:
            ws_url = self._bot._resume_gateway_url
            self._resume_on_hello = True
        else:
            gateway_info = await self._bot.api_client.request("GET", "/gateway/bot")
            ws_url = gateway_info.get("url", self._bot.config.gateway_url)
            self._resume_on_hello = False
        logger.info(
            {
                "event": "gateway.connecting",
                "resume": self._resume_on_hello,
                "url": ws_url,
                "api_version": self._bot.config.api_version,
                "shard_id": self._bot.config.shard_id,
                "shard_count": self._bot.config.shard_count,
            },
            extra=self._bot._log_extra(),
        )
        session = await self._bot._create_session()
        self._ws = await session.ws_connect(
            f"{ws_url}?v={self._bot.config.api_version}&encoding=json"
        )
        logger.info(
            {"event": "gateway.connected", "resume": self._resume_on_hello},
            extra=self._bot._log_extra(),
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
        logger.info(
            {
                "event": "gateway.identify",
                "intents": int(self._bot.config.intents),
                "shard_id": self._bot.config.shard_id,
                "shard_count": self._bot.config.shard_count,
            },
            extra=self._bot._log_extra(),
        )
        await self.send_payload(payload)

    async def resume(self) -> None:
        if self._bot._session_id is None:
            await self.identify()
            return
        payload = {
            "op": 6,
            "d": {
                "token": self._bot.config.token,
                "session_id": self._bot._session_id,
                "seq": self._bot._sequence,
            },
        }
        logger.info(
            {
                "event": "gateway.resume",
                "session_id": self._bot._session_id,
                "sequence": self._bot._sequence,
            },
            extra=self._bot._log_extra(),
        )
        await self.send_payload(payload)

    async def reconnect(self, *, resume: bool) -> None:
        from vaidcord.bot import BotState

        self._bot._state = BotState.RECONNECTING
        logger.warning(
            {"event": "gateway.reconnecting", "resume": resume},
            extra=self._bot._log_extra(),
        )
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._ws and not self._ws.closed:
            await self._ws.close()
        await self.connect(resume=resume)

    async def _heartbeat(self) -> None:
        while self._bot._running and self._heartbeat_interval is not None:
            await asyncio.sleep(self._heartbeat_interval / 1000)
            if not self._heartbeat_ack_received:
                logger.warning("Heartbeat ACK was not received before the next heartbeat")
                await self.reconnect(resume=True)
                return
            await self._send_heartbeat()

    async def _send_heartbeat(self) -> None:
        self._heartbeat_ack_received = False
        self._last_heartbeat_sent_at = time.monotonic()
        await self.send_payload({"op": 1, "d": self._bot._sequence})

    async def run(self) -> None:
        if not self._ws:
            return
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    op = data.get("op")
                    if op == 0:
                        await self._bot._handle_dispatch(data)
                    elif op == 1:
                        await self._send_heartbeat()
                    elif op == 7:
                        await self.reconnect(resume=True)
                        return
                    elif op == 9:
                        await asyncio.sleep(5)
                        await self.reconnect(resume=bool(data.get("d")))
                        return
                    elif op == 10:
                        self._heartbeat_interval = data["d"]["heartbeat_interval"]
                        if self._resume_on_hello:
                            self._resume_on_hello = False
                            await self.resume()
                        else:
                            await self.identify()
                        if self._heartbeat_task:
                            self._heartbeat_task.cancel()
                        self._heartbeat_task = asyncio.create_task(self._heartbeat())
                    elif op == 11:
                        self._heartbeat_ack_received = True
                        if self._last_heartbeat_sent_at is not None:
                            self._latency = time.monotonic() - self._last_heartbeat_sent_at
                        logger.debug("Received heartbeat ACK")
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        except asyncio.CancelledError:
            logger.debug("Gateway runtime cancelled")
            return
        finally:
            self._log_close_code()

    async def stop(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None

    def _log_close_code(self) -> None:
        if self._ws is None:
            return
        close_code = self._ws.close_code
        if close_code is None:
            return
        hint = _GATEWAY_CLOSE_HINTS.get(close_code)
        if hint is None:
            logger.info("Gateway websocket closed with code %s", close_code)
            return
        logger.warning("Gateway websocket closed with code %s: %s", close_code, hint)
