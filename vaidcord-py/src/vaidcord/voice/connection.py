from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import aiohttp

from .models import (
    VoiceGatewayConfig,
    VoiceReady,
    VoiceServerUpdate,
    VoiceSessionDescription,
    VoiceState,
)
from .udp import VoiceUDPClient

if TYPE_CHECKING:
    from vaidcord.bot import Bot

logger = logging.getLogger(__name__)


class VoiceManager:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._states: dict[int, VoiceState] = {}
        self._servers: dict[int, VoiceServerUpdate] = {}
        self._waiters: dict[int, asyncio.Event] = {}

    def _event_for(self, guild_id: int) -> asyncio.Event:
        event = self._waiters.get(guild_id)
        if event is None:
            event = asyncio.Event()
            self._waiters[guild_id] = event
        return event

    def handle_gateway_event(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type == "VOICE_STATE_UPDATE" and data.get("session_id"):
            guild_id = int(data["guild_id"])
            self._states[guild_id] = VoiceState(
                guild_id=guild_id,
                channel_id=int(data["channel_id"]) if data.get("channel_id") else None,
                user_id=int(data["user_id"]) if data.get("user_id") else None,
                session_id=data["session_id"],
                raw_data=dict(data),
            )
            self._event_for(guild_id).set()
        elif event_type == "VOICE_SERVER_UPDATE":
            guild_id = int(data["guild_id"])
            self._servers[guild_id] = VoiceServerUpdate(
                guild_id=guild_id,
                token=data["token"],
                endpoint=data["endpoint"],
                raw_data=dict(data),
            )
            self._event_for(guild_id).set()

    async def request_join(
        self,
        guild_id: int,
        channel_id: int,
        *,
        self_mute: bool = False,
        self_deaf: bool = False,
        wait_timeout: float = 30.0,
    ) -> tuple[VoiceState, VoiceServerUpdate]:
        self._event_for(guild_id).clear()
        await self._bot.runtime.send_payload(
            {
                "op": 4,
                "d": {
                    "guild_id": str(guild_id),
                    "channel_id": str(channel_id),
                    "self_mute": self_mute,
                    "self_deaf": self_deaf,
                },
            }
        )
        deadline = time.monotonic() + wait_timeout
        while time.monotonic() < deadline:
            state = self._states.get(guild_id)
            server = self._servers.get(guild_id)
            if state is not None and server is not None:
                return state, server
            await asyncio.wait_for(self._event_for(guild_id).wait(), timeout=deadline - time.monotonic())
            self._event_for(guild_id).clear()
        raise TimeoutError("Timed out waiting for Discord voice state/server updates")

    async def connect(
        self,
        guild_id: int,
        channel_id: int,
        *,
        user_id: int,
        self_mute: bool = False,
        self_deaf: bool = False,
        config: VoiceGatewayConfig | None = None,
        wait_timeout: float = 30.0,
    ) -> VoiceConnection:
        voice_state, server = await self.request_join(
            guild_id,
            channel_id,
            self_mute=self_mute,
            self_deaf=self_deaf,
            wait_timeout=wait_timeout,
        )
        connection = VoiceConnection(
            bot=self._bot,
            guild_id=guild_id,
            user_id=user_id,
            state=voice_state,
            server=server,
            config=config or VoiceGatewayConfig(),
        )
        await connection.connect(wait_timeout=wait_timeout)
        return connection


class VoiceConnection:
    def __init__(
        self,
        *,
        bot: Bot,
        guild_id: int,
        user_id: int,
        state: VoiceState,
        server: VoiceServerUpdate,
        config: VoiceGatewayConfig,
    ) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.state = state
        self.server = server
        self.config = config
        self.ready: VoiceReady | None = None
        self.session_description: VoiceSessionDescription | None = None
        self.udp: VoiceUDPClient | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._last_sequence: int = -1

    async def connect(self, *, wait_timeout: float = 30.0) -> None:
        session = await self.bot._create_session()
        self._ws = await session.ws_connect(f"{self.server.websocket_url}?v={self.config.version}")
        await self.identify()
        await asyncio.wait_for(self._receive_until_ready(), timeout=wait_timeout)

    async def identify(self) -> None:
        await self._send(
            0,
            {
                "server_id": str(self.guild_id),
                "user_id": str(self.user_id),
                "session_id": self.state.session_id,
                "token": self.server.token,
                "max_dave_protocol_version": self.config.max_dave_protocol_version,
            },
        )

    async def select_protocol(self, address: str, port: int, mode: str) -> None:
        await self._send(1, {"protocol": "udp", "data": {"address": address, "port": port, "mode": mode}})

    async def set_speaking(self, speaking: int, *, delay: int = 0) -> None:
        if self.ready is None:
            raise RuntimeError("Voice connection is not ready")
        await self._send(5, {"speaking": speaking, "delay": delay, "ssrc": self.ready.ssrc})

    async def close(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self.udp is not None:
            await self.udp.close()
            self.udp = None
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()

    async def _send(self, op: int, data: Any) -> None:
        if self._ws is None:
            raise RuntimeError("Voice websocket is not connected")
        await self._ws.send_json({"op": op, "d": data})

    async def _receive_until_ready(self) -> None:
        if self._ws is None:
            raise RuntimeError("Voice websocket is not connected")
        async for message in self._ws:
            if message.type != aiohttp.WSMsgType.TEXT:
                continue
            payload = message.json()
            if "seq" in payload:
                self._last_sequence = int(payload["seq"])
            op = int(payload.get("op", -1))
            data = payload.get("d") or {}
            if op == 8:
                interval = float(data["heartbeat_interval"]) / 1000
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))
            elif op == 2:
                self.ready = VoiceReady(
                    ssrc=int(data["ssrc"]),
                    ip=data["ip"],
                    port=int(data["port"]),
                    modes=tuple(data.get("modes", ())),
                    raw_data=dict(data),
                )
                self.udp = VoiceUDPClient(self.ready.ip, self.ready.port)
                return
            elif op == 4:
                self.session_description = VoiceSessionDescription(
                    mode=data["mode"],
                    secret_key=bytes(data["secret_key"]),
                    dave_protocol_version=data.get("dave_protocol_version"),
                    raw_data=dict(data),
                )

    async def _heartbeat_loop(self, interval: float) -> None:
        while True:
            await self._send(3, {"t": int(time.time() * 1000), "seq_ack": self._last_sequence})
            await asyncio.sleep(interval)
