from __future__ import annotations

import asyncio
import enum
import logging
import struct
import time
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any

import aiohttp

from .audio import (
    AudioBackendError,
    check_voice_dependencies,
    iter_opus_frames,
)
from .crypto import VoiceBox, create_voice_box
from .dave import DaveOutboundPayload, DaveProtocolController, DaveUnsupportedError
from .models import (
    VoiceGatewayConfig,
    VoiceReady,
    VoiceServerUpdate,
    VoiceSessionDescription,
    VoiceSpeakingFlag,
    VoiceState,
)
from .player import AudioPlayer
from .receive import AudioSink, VoiceReceiver
from .sources import AudioSource
from .udp import VoiceUDPClient

if TYPE_CHECKING:
    from vaidcord.bot import Bot

logger = logging.getLogger(__name__)

SpeakingCallback = Callable[[int, int, int], Any]


class VoiceCloseAction(enum.Enum):
    """What to do when the voice websocket closes with a given code."""

    RESUME = "resume"
    REJOIN = "rejoin"
    FATAL = "fatal"


#: Close codes after which reconnecting is pointless or forbidden.
FATAL_VOICE_CLOSE_CODES = frozenset(
    {4001, 4002, 4003, 4004, 4005, 4011, 4012, 4014, 4016, 4017}
)
#: Close codes that invalidate the session and require a fresh join.
REJOIN_VOICE_CLOSE_CODES = frozenset({4006, 4009})


def classify_voice_close_code(close_code: int | None) -> VoiceCloseAction:
    if close_code in FATAL_VOICE_CLOSE_CODES:
        return VoiceCloseAction.FATAL
    if close_code in REJOIN_VOICE_CLOSE_CODES:
        return VoiceCloseAction.REJOIN
    # Unknown/network-level closes (None, 1000, 1001, 1006, 4015, ...) are
    # worth a resume attempt; the server will reject it if the session died.
    return VoiceCloseAction.RESUME


class VoiceManager:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._states: dict[int, VoiceState] = {}
        self._servers: dict[int, VoiceServerUpdate] = {}
        self._waiters: dict[int, asyncio.Event] = {}
        self._connections: dict[int, VoiceConnection] = {}

    @property
    def connections(self) -> dict[int, VoiceConnection]:
        return dict(self._connections)

    def get(self, guild_id: int) -> VoiceConnection | None:
        return self._connections.get(guild_id)

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
            update = VoiceServerUpdate(
                guild_id=guild_id,
                token=data["token"],
                endpoint=data["endpoint"],
                raw_data=dict(data),
            )
            self._servers[guild_id] = update
            self._event_for(guild_id).set()
            connection = self._connections.get(guild_id)
            if connection is not None and connection.is_connected:
                # Voice server failover: reconnect the live session to the
                # new endpoint without tearing down the high-level object.
                with suppress(RuntimeError):
                    asyncio.get_running_loop().create_task(
                        connection.migrate_to(update)
                    )

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

    async def request_leave(self, guild_id: int) -> None:
        await self._bot.runtime.send_payload(
            {
                "op": 4,
                "d": {
                    "guild_id": str(guild_id),
                    "channel_id": None,
                    "self_mute": False,
                    "self_deaf": False,
                },
            }
        )

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
        existing = self._connections.get(guild_id)
        if existing is not None:
            await existing.close()
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
        self._connections[guild_id] = connection
        try:
            await connection.connect(wait_timeout=wait_timeout)
        except BaseException:
            self._connections.pop(guild_id, None)
            raise
        return connection

    async def disconnect(self, guild_id: int) -> None:
        connection = self._connections.pop(guild_id, None)
        await self.request_leave(guild_id)
        if connection is not None:
            await connection.close()

    def _forget(self, guild_id: int, connection: VoiceConnection) -> None:
        if self._connections.get(guild_id) is connection:
            self._connections.pop(guild_id, None)


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
        self._reader_task: asyncio.Task[None] | None = None
        self._last_sequence: int = -1
        self._last_heartbeat_sent_at: float | None = None
        self._latency: float = 0.0
        self._rtp_sequence: int = 0
        self._rtp_timestamp: int = 0
        self._rtp_nonce: int = 0
        self._voice_box: VoiceBox | None = None
        self._ssrc_map: dict[int, int] = {}
        self._speaking_callbacks: list[SpeakingCallback] = []
        self._closing = False
        self._resumed_event = asyncio.Event()
        self._player: AudioPlayer | None = None
        self._receiver: VoiceReceiver | None = None
        self._dave_outbound: list[DaveOutboundPayload] = []
        self.dave = DaveProtocolController(
            backend=self.config.dave_backend,
            fail_fast=self.config.dave_fail_fast,
            send_payload=self._dave_outbound.append,
        )

    # ------------------------------------------------------------------ #
    # Introspection                                                      #
    # ------------------------------------------------------------------ #

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and not self._ws.closed and not self._closing

    @property
    def latency(self) -> float:
        """Voice websocket heartbeat latency in seconds."""
        return self._latency

    @property
    def voice_box(self) -> VoiceBox | None:
        """The negotiated transport-encryption strategy, if any."""
        return self._voice_box

    def ssrc_to_user(self, ssrc: int) -> int | None:
        return self._ssrc_map.get(ssrc)

    def on_speaking(self, callback: SpeakingCallback) -> SpeakingCallback:
        """Register ``callback(user_id, ssrc, flags)`` for op-5 events of others."""
        self._speaking_callbacks.append(callback)
        return callback

    # ------------------------------------------------------------------ #
    # Connection lifecycle                                               #
    # ------------------------------------------------------------------ #

    async def connect(self, *, wait_timeout: float = 30.0) -> None:
        self._closing = False
        session = await self.bot._create_session()
        self._ws = await session.ws_connect(f"{self.server.websocket_url}?v={self.config.version}&encoding=json")
        await self.identify()
        await asyncio.wait_for(self._receive_until(lambda: self.ready is not None), timeout=wait_timeout)
        await asyncio.wait_for(self._establish_udp_transport(), timeout=wait_timeout)
        await asyncio.wait_for(
            self._receive_until(lambda: self.session_description is not None),
            timeout=wait_timeout,
        )
        self._start_reader()

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
        await self._stop_reader()
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        session = await self.bot._create_session()
        self._ws = await session.ws_connect(f"{self.server.websocket_url}?v={self.config.version}&encoding=json")
        if resume and self.state.session_id:
            self._resumed_event.clear()
            await self.resume()
            await asyncio.wait_for(
                self._receive_until(lambda: self._resumed_event.is_set() or self.ready is not None),
                timeout=wait_timeout,
            )
        else:
            self.ready = None
            self.session_description = None
            self._voice_box = None
            await self.identify()
            await asyncio.wait_for(self._receive_until(lambda: self.ready is not None), timeout=wait_timeout)
            await asyncio.wait_for(self._establish_udp_transport(), timeout=wait_timeout)
            await asyncio.wait_for(
                self._receive_until(lambda: self.session_description is not None),
                timeout=wait_timeout,
            )
        self._start_reader()

    async def migrate_to(self, server: VoiceServerUpdate, *, wait_timeout: float = 30.0) -> None:
        """Reconnect to a new voice server after VOICE_SERVER_UPDATE failover."""
        logger.info("Voice server migration for guild %s -> %s", self.guild_id, server.endpoint)
        self.server = server
        if self.udp is not None:
            await self.udp.close()
            self.udp = None
        await self.reconnect(resume=False, wait_timeout=wait_timeout)

    async def disconnect(self) -> None:
        """Leave the voice channel (main-gateway op 4) and close this connection."""
        manager = getattr(self.bot, "voice", None)
        if manager is not None:
            manager._forget(self.guild_id, self)
            await manager.request_leave(self.guild_id)
        await self.close()

    async def close(self) -> None:
        self._closing = True
        if self._player is not None:
            self._player.stop()
            self._player = None
        if self._receiver is not None:
            receiver = self._receiver
            self._receiver = None
            await receiver.stop()
        await self._stop_reader()
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

    # ------------------------------------------------------------------ #
    # Speaking / outbound audio                                          #
    # ------------------------------------------------------------------ #

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

    def play(
        self,
        source: AudioSource,
        *,
        after: Callable[[Exception | None], Any] | None = None,
        speaking_flags: int = int(VoiceSpeakingFlag.MICROPHONE),
        bitrate_kbps: int = 128,
    ) -> AudioPlayer:
        """Start playing an :class:`AudioSource` in the background.

        Returns the :class:`AudioPlayer`; use ``await player.wait()`` to
        block until playback finishes.
        """
        if self._player is not None and not self._player._done.is_set():
            raise RuntimeError("Already playing audio; call stop() first")
        player = AudioPlayer(
            source,
            self,
            after=after,
            speaking_flags=speaking_flags,
            bitrate_kbps=bitrate_kbps,
        )
        self._player = player
        player.start()
        return player

    @property
    def player(self) -> AudioPlayer | None:
        return self._player

    @property
    def is_playing(self) -> bool:
        return self._player is not None and self._player.is_playing

    def pause(self) -> None:
        if self._player is not None:
            self._player.pause()

    def resume_playback(self) -> None:
        if self._player is not None:
            self._player.resume()

    def stop(self) -> None:
        if self._player is not None:
            self._player.stop()

    # ------------------------------------------------------------------ #
    # Inbound audio                                                      #
    # ------------------------------------------------------------------ #

    def listen(self, sink: AudioSink) -> VoiceReceiver:
        """Start receiving audio from the channel into ``sink``."""
        if self._receiver is not None and self._receiver.is_running:
            raise RuntimeError("Already listening; call stop_listening() first")
        if self.udp is None:
            raise RuntimeError("Voice UDP transport is not connected")
        receiver = VoiceReceiver(self, sink)
        self._receiver = receiver
        receiver.start()
        return receiver

    @property
    def is_listening(self) -> bool:
        return self._receiver is not None and self._receiver.is_running

    async def stop_listening(self) -> None:
        if self._receiver is not None:
            receiver = self._receiver
            self._receiver = None
            await receiver.stop()

    # ------------------------------------------------------------------ #
    # Legacy iterator-based playback helpers                             #
    # ------------------------------------------------------------------ #

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
        loop = asyncio.get_running_loop()
        next_deadline = loop.time()
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
                next_deadline += frame_duration_ms / 1000.0
                delay = next_deadline - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                elif delay < -0.1:
                    next_deadline = loop.time()
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
            if frame_duration_ms > 0:
                await asyncio.sleep(frame_duration_ms / 1000.0)

    def _encrypt_voice_payload(self, header: bytes, payload: bytes) -> bytes:
        if self.session_description is None:
            return payload
        if self._voice_box is None:
            self._voice_box = create_voice_box(
                self.session_description.mode, self.session_description.secret_key
            )
        return self._voice_box.seal(header, payload, self._rtp_nonce)

    # ------------------------------------------------------------------ #
    # Websocket plumbing                                                 #
    # ------------------------------------------------------------------ #

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

    def _start_reader(self) -> None:
        if self._reader_task is not None and not self._reader_task.done():
            return
        self._reader_task = asyncio.create_task(self._read_loop(), name="vaidcord-voice-reader")

    async def _stop_reader(self) -> None:
        task = self._reader_task
        self._reader_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _read_loop(self) -> None:
        """Keep consuming the voice websocket after the handshake.

        Dispatches speaking/DAVE/heartbeat traffic and drives the
        reconnect policy when the socket closes unexpectedly.
        """
        backoff = 1.0
        while not self._closing:
            ws = self._ws
            if ws is None:
                return
            try:
                async for message in ws:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_ws_payload(message.json())
                    elif message.type == aiohttp.WSMsgType.BINARY:
                        self._handle_binary_payload(message.data)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Voice websocket reader crashed; attempting reconnect")
            if self._closing:
                return
            close_code = ws.close_code
            action = classify_voice_close_code(close_code)
            logger.info(
                "Voice websocket closed (code=%s) for guild %s; action=%s",
                close_code,
                self.guild_id,
                action.value,
            )
            if action is VoiceCloseAction.FATAL:
                if close_code == 4017:
                    logger.error(
                        "Voice channel requires DAVE/E2EE (close 4017); not reconnecting."
                    )
                self._closing = True
                return
            try:
                await self._attempt_reconnect(action)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Voice reconnect failed for guild %s; retrying in %.1fs",
                    self.guild_id,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def _attempt_reconnect(self, action: VoiceCloseAction) -> None:
        if action is VoiceCloseAction.REJOIN:
            await self._rejoin()
            return
        try:
            await self._reconnect_transport(resume=True)
        except Exception:
            logger.info("Voice resume failed for guild %s; trying a fresh identify", self.guild_id)
            await self._reconnect_transport(resume=False)

    async def _reconnect_transport(self, *, resume: bool, wait_timeout: float = 30.0) -> None:
        """Like :meth:`reconnect`, but safe to call from inside the reader task."""
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        session = await self.bot._create_session()
        self._ws = await session.ws_connect(
            f"{self.server.websocket_url}?v={self.config.version}&encoding=json"
        )
        if resume and self.state.session_id:
            self._resumed_event.clear()
            await self.resume()
            await asyncio.wait_for(
                self._receive_until(lambda: self._resumed_event.is_set() or self.ready is not None),
                timeout=wait_timeout,
            )
        else:
            self.ready = None
            self.session_description = None
            self._voice_box = None
            await self.identify()
            await asyncio.wait_for(self._receive_until(lambda: self.ready is not None), timeout=wait_timeout)
            await asyncio.wait_for(self._establish_udp_transport(), timeout=wait_timeout)
            await asyncio.wait_for(
                self._receive_until(lambda: self.session_description is not None),
                timeout=wait_timeout,
            )

    async def _rejoin(self, *, wait_timeout: float = 30.0) -> None:
        manager = getattr(self.bot, "voice", None)
        channel_id = self.state.channel_id
        if manager is None or channel_id is None:
            raise RuntimeError("Cannot rejoin voice: no manager or channel available")
        state, server = await manager.request_join(
            self.guild_id, channel_id, wait_timeout=wait_timeout
        )
        self.state = state
        self.server = server
        if self.udp is not None:
            await self.udp.close()
            self.udp = None
        await self._reconnect_transport(resume=False, wait_timeout=wait_timeout)

    def _handle_binary_payload(self, data: bytes) -> None:
        # Voice gateway v8 binary frames: uint16 sequence + uint8 opcode + body.
        if len(data) < 3:
            return
        seq, op = struct.unpack_from(">HB", data, 0)
        self._last_sequence = seq
        try:
            self.dave.handle_gateway_payload(op, {"binary": data[3:]})
        except Exception:
            logger.debug("Unhandled binary voice payload (op=%s)", op, exc_info=True)

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
            self._voice_box = None
        elif op == 5:
            self._handle_speaking(data)
        elif op == 9:
            self._resumed_event.set()
        elif op == 12:
            # Video announcement also carries the sender's audio SSRC.
            user_id = data.get("user_id")
            audio_ssrc = data.get("audio_ssrc")
            if user_id is not None and audio_ssrc:
                self._map_ssrc(int(audio_ssrc), int(user_id))
        elif op == 13:
            user_id = data.get("user_id")
            if user_id is not None:
                self._forget_user(int(user_id))
        elif 21 <= op <= 31:
            self.dave.handle_gateway_payload(op, data)
            await self._flush_dave_outbound()

    def _handle_speaking(self, data: dict[str, Any]) -> None:
        ssrc = data.get("ssrc")
        user_id = data.get("user_id")
        if ssrc is None or user_id is None:
            return
        speaking = int(data.get("speaking", 0))
        self._map_ssrc(int(ssrc), int(user_id))
        for callback in self._speaking_callbacks:
            try:
                callback(int(user_id), int(ssrc), speaking)
            except Exception:
                logger.exception("on_speaking callback raised")

    def _map_ssrc(self, ssrc: int, user_id: int) -> None:
        is_new = self._ssrc_map.get(ssrc) != user_id
        self._ssrc_map[ssrc] = user_id
        if is_new and self._receiver is not None:
            try:
                self._receiver.sink.on_speaking_start(user_id, ssrc)
            except Exception:
                logger.exception("Sink on_speaking_start raised")

    def _forget_user(self, user_id: int) -> None:
        for ssrc, mapped in list(self._ssrc_map.items()):
            if mapped == user_id:
                del self._ssrc_map[ssrc]
        if self._receiver is not None:
            try:
                self._receiver.sink.on_speaking_stop(user_id)
            except Exception:
                logger.exception("Sink on_speaking_stop raised")

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


# Backwards-compatible aliases used elsewhere in the package.
__all__ = [
    "FATAL_VOICE_CLOSE_CODES",
    "REJOIN_VOICE_CLOSE_CODES",
    "VoiceCloseAction",
    "VoiceConnection",
    "VoiceManager",
    "classify_voice_close_code",
]
