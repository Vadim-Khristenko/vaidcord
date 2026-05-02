from __future__ import annotations

import asyncio
import logging
import struct
import time
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any

import aiohttp

from .audio import (
    AudioBackendError,
    MissingVoiceDependency,
    check_voice_dependencies,
    iter_opus_frames,
)
from .dave import DaveOutboundPayload, DaveProtocolController, DaveUnsupportedError
from .models import (
    VoiceGatewayConfig,
    VoiceReady,
    VoiceServerUpdate,
    VoiceSessionDescription,
    VoiceSpeakingFlag,
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
        self._states.pop(guild_id, None)
        self._servers.pop(guild_id, None)
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
        self._last_heartbeat_sent_at: float | None = None
        self._latency: float = 0.0
        self._rtp_sequence: int = 0
        self._rtp_timestamp: int = 0
        self._rtp_nonce: int = 0
        self._dave_outbound: list[DaveOutboundPayload] = []
        self.dave = DaveProtocolController(
            backend=self.config.dave_backend,
            fail_fast=self.config.dave_fail_fast,
            send_payload=self._dave_outbound.append,
        )

    async def connect(self, *, wait_timeout: float = 30.0) -> None:
        session = await self.bot._create_session()
        self._ws = await session.ws_connect(f"{self.server.websocket_url}?v={self.config.version}&encoding=json")
        await self.identify()
        await asyncio.wait_for(self._receive_until(lambda: self.ready is not None), timeout=wait_timeout)
        await asyncio.wait_for(self._establish_udp_transport(), timeout=wait_timeout)
        await asyncio.wait_for(
            self._receive_until(lambda: self.session_description is not None),
            timeout=wait_timeout,
        )

    async def identify(self) -> None:
        payload = {
            "server_id": str(self.guild_id),
            "user_id": str(self.user_id),
            "session_id": self.state.session_id,
            "token": self.server.token,
            **self.dave.identify_fields(),
        }
        if self.config.dave_backend is not None and self.config.max_dave_protocol_version > 0:
            payload["max_dave_protocol_version"] = min(
                self.config.max_dave_protocol_version,
                self.dave.max_protocol_version,
            )
        await self._send(0, payload)

    async def resume(self) -> None:
        await self._send(
            7,
            {
                "server_id": str(self.guild_id),
                "session_id": self.state.session_id,
                "token": self.server.token,
                "seq_ack": self._last_sequence if self._last_sequence >= 0 else -1,
            },
        )

    async def reconnect(self, *, resume: bool = True, wait_timeout: float = 30.0) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        session = await self.bot._create_session()
        self._ws = await session.ws_connect(f"{self.server.websocket_url}?v={self.config.version}&encoding=json")
        if resume and self.state.session_id:
            await self.resume()
        else:
            await self.identify()
        await asyncio.wait_for(self._receive_until(lambda: self.ready is not None), timeout=wait_timeout)

    async def select_protocol(self, address: str, port: int, mode: str) -> None:
        await self._send(1, {"protocol": "udp", "data": {"address": address, "port": port, "mode": mode}})

    async def set_speaking(self, speaking: int, *, delay: int = 0) -> None:
        if self.ready is None:
            raise RuntimeError("Voice connection is not ready")
        await self._send(5, {"speaking": speaking, "delay": delay, "ssrc": self.ready.ssrc})

    async def start_speaking(self, speaking: int = int(VoiceSpeakingFlag.MICROPHONE)) -> None:
        await self.set_speaking(speaking, delay=0)

    async def stop_speaking(self) -> None:
        await self.set_speaking(0, delay=0)

    def build_rtp_packet(self, payload: bytes, *, payload_type: int = 0x78) -> bytes:
        if self.ready is None:
            raise RuntimeError("Voice connection is not ready")
        header = struct.pack(
            ">BBHII",
            0x80,
            payload_type & 0x7F,
            self._rtp_sequence & 0xFFFF,
            self._rtp_timestamp & 0xFFFFFFFF,
            self.ready.ssrc,
        )
        return header + payload

    async def send_audio_frame(
        self,
        payload: bytes,
        *,
        timestamp_step: int = 960,
        payload_type: int = 0x78,
        encrypt: bool = True,
    ) -> None:
        if self.udp is None:
            raise RuntimeError("Voice UDP transport is not connected")
        header = self.build_rtp_packet(b"", payload_type=payload_type)
        body = payload
        if self.ready is not None:
            body = self.dave.encrypt_frame(ssrc=self.ready.ssrc, frame=body)
        if encrypt:
            body = self._encrypt_voice_payload(header, body)
        packet = header + body
        await self.udp.send(packet)
        self._rtp_sequence = (self._rtp_sequence + 1) & 0xFFFF
        self._rtp_timestamp = (self._rtp_timestamp + timestamp_step) & 0xFFFFFFFF
        self._rtp_nonce = (self._rtp_nonce + 1) & 0xFFFFFFFF

    async def stream_audio(
        self,
        frames: AsyncIterator[bytes],
        *,
        frame_duration_ms: float = 20.0,
        timestamp_step: int = 960,
        payload_type: int = 0x78,
        speaking: bool = True,
    ) -> int:
        if speaking:
            await self.start_speaking()
        sent_frames = 0
        try:
            async for frame in frames:
                if not frame:
                    continue
                await self.send_audio_frame(
                    frame,
                    timestamp_step=timestamp_step,
                    payload_type=payload_type,
                    encrypt=True,
                )
                sent_frames += 1
                await asyncio.sleep(frame_duration_ms / 1000.0)
        finally:
            if speaking:
                await self.send_silence_frames()
                await self.stop_speaking()
        return sent_frames

    async def play_file(
        self,
        path: str,
        *,
        chunk_size: int = 3840,
        frame_duration_ms: float = 20.0,
        timestamp_step: int = 960,
        payload_type: int = 0x78,
    ) -> int:
        status = check_voice_dependencies()
        status.raise_for_playback()
        sent_frames = await self.stream_audio(
            iter_opus_frames(path, frame_duration_ms=int(frame_duration_ms)),
            frame_duration_ms=frame_duration_ms,
            timestamp_step=timestamp_step,
            payload_type=payload_type,
            speaking=True,
        )
        if sent_frames == 0:
            raise AudioBackendError(f"Audio file produced no Opus frames: {path}")
        logger.info(
            "Voice playback sent %d Opus frames from %s",
            sent_frames,
            path,
        )
        return sent_frames

    async def send_silence_frames(
        self,
        *,
        frames: int = 5,
        frame: bytes = b"\xF8\xFF\xFE",
        frame_duration_ms: float = 20.0,
        timestamp_step: int = 960,
        payload_type: int = 0x78,
    ) -> None:
        for _ in range(max(0, frames)):
            await self.send_audio_frame(frame, timestamp_step=timestamp_step, payload_type=payload_type)
            await asyncio.sleep(frame_duration_ms / 1000.0)

    def _encrypt_voice_payload(self, header: bytes, payload: bytes) -> bytes:
        if self.session_description is None:
            return payload
        mode = self.session_description.mode
        secret = self.session_description.secret_key
        nonce4 = self._rtp_nonce.to_bytes(4, byteorder="big")
        if mode == "aead_xchacha20_poly1305_rtpsize":
            try:
                from nacl.bindings import (  # type: ignore[import-not-found]
                    crypto_aead_xchacha20poly1305_ietf_encrypt,
                )
            except ImportError as error:  # pragma: no cover - dependency gate
                raise MissingVoiceDependency(
                    "XChaCha20-Poly1305 voice encryption requires PyNaCl. "
                    "Install optional voice deps with `pip install 'vaidcord[voice]'`."
                ) from error
            nonce = nonce4 + b"\x00" * 20
            encrypted = crypto_aead_xchacha20poly1305_ietf_encrypt(payload, bytes(header), nonce, secret)
            return bytes(encrypted) + nonce4
        if mode == "aead_aes256_gcm_rtpsize":
            try:
                from cryptography.hazmat.primitives.ciphers.aead import (
                    AESGCM,  # type: ignore[import-not-found]
                )
            except ImportError as error:  # pragma: no cover - dependency gate
                raise MissingVoiceDependency(
                    "AES256-GCM voice encryption requires `cryptography`. "
                    "Install optional voice deps with `pip install 'vaidcord[voice]'`."
                ) from error
            box = AESGCM(secret)
            nonce = nonce4 + b"\x00" * 8
            encrypted = box.encrypt(nonce, payload, bytes(header))
            return encrypted + nonce4
        raise RuntimeError(f"Unsupported voice encryption mode: {mode}")

    async def close(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
        if self.udp is not None:
            await self.udp.close()
            self.udp = None
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()

    async def _send(self, op: int, data: Any) -> None:
        if self._ws is None or self._ws.closed:
            raise RuntimeError("Voice websocket is not connected")
        await self._ws.send_json({"op": op, "d": data})

    async def _receive_until(self, done: Callable[[], bool]) -> None:
        if done():
            return
        if self._ws is None:
            raise RuntimeError("Voice websocket is not connected")
        async for message in self._ws:
            if message.type != aiohttp.WSMsgType.TEXT:
                continue
            payload = message.json()
            await self._handle_ws_payload(payload)
            if done():
                return
        close_code = self._ws.close_code if self._ws is not None else None
        if close_code == 4017:
            raise DaveUnsupportedError(
                "Voice websocket closed with 4017: this channel requires DAVE/E2EE voice. "
                "VaidCord currently provides DAVE diagnostics but not a production MLS/libdave backend."
            )
        raise RuntimeError(f"Voice websocket closed before handshake finished (close_code={close_code})")

    async def _handle_ws_payload(self, payload: dict[str, Any]) -> None:
        if "seq" in payload:
            self._last_sequence = int(payload["seq"])
        op = int(payload.get("op", -1))
        data = payload.get("d") or {}
        if op == 8:
            interval = float(data["heartbeat_interval"]) / 1000
            if self._heartbeat_task is not None:
                self._heartbeat_task.cancel()
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))
        elif op == 6:
            if self._last_heartbeat_sent_at is not None:
                self._latency = time.monotonic() - self._last_heartbeat_sent_at
        elif op == 2:
            self.ready = VoiceReady(
                ssrc=int(data["ssrc"]),
                ip=data["ip"],
                port=int(data["port"]),
                modes=tuple(data.get("modes", ())),
                raw_data=dict(data),
            )
            self.udp = VoiceUDPClient(self.ready.ip, self.ready.port)
        elif op == 4:
            self.dave.handle_session_description(data)
            self.session_description = VoiceSessionDescription(
                mode=data["mode"],
                secret_key=bytes(data["secret_key"]),
                dave_protocol_version=data.get("dave_protocol_version"),
                raw_data=dict(data),
            )
        elif 21 <= op <= 31:
            self.dave.handle_gateway_payload(op, data)
            await self._flush_dave_outbound()

    async def _flush_dave_outbound(self) -> None:
        while self._dave_outbound:
            outbound = self._dave_outbound.pop(0)
            if outbound.binary:
                if self._ws is None or self._ws.closed:
                    raise RuntimeError("Voice websocket is not connected")
                if not isinstance(outbound.data, (bytes, bytearray, memoryview)):
                    raise TypeError("Binary DAVE outbound payloads must contain bytes-like data")
                await self._ws.send_bytes(bytes(outbound.data))
            else:
                await self._send(outbound.op, dict(outbound.data))

    async def _heartbeat_loop(self, interval: float) -> None:
        while True:
            self._last_heartbeat_sent_at = time.monotonic()
            try:
                await self._send(3, {"t": int(time.time() * 1000), "seq_ack": self._last_sequence})
            except RuntimeError:
                return
            await asyncio.sleep(interval)

    async def _establish_udp_transport(self) -> None:
        if self.ready is None:
            raise RuntimeError("Voice READY payload not received")
        if self.udp is None:
            self.udp = VoiceUDPClient(self.ready.ip, self.ready.port)
        await self.udp.connect()
        address, port = await self.udp.discover_ip(self.ready.ssrc)
        mode = self.ready.select_mode(self.config)
        await self.select_protocol(address, port, mode)
