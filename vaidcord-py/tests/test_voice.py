from __future__ import annotations

import asyncio
import struct
from typing import Any

import pytest

from vaidcord.voice import (
    AudioBackendStatus,
    DaveKeyPackage,
    DaveUnsupportedError,
    VoiceEncryptionMode,
    VoiceGatewayConfig,
    VoiceManager,
    VoiceReady,
    VoiceServerUpdate,
    VoiceSpeakingFlag,
    build_ip_discovery_packet,
    iter_file_chunks,
    parse_ip_discovery_response,
)
from vaidcord.voice.connection import VoiceConnection, VoiceState


class FakeRuntime:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def send_payload(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


class FakeBot:
    def __init__(self) -> None:
        self.runtime = FakeRuntime()


def test_voice_server_update_builds_websocket_url() -> None:
    update = VoiceServerUpdate(
        guild_id=1,
        token="token",
        endpoint="sweetwater-12345.discord.media:2048",
    )

    assert update.websocket_url == "wss://sweetwater-12345.discord.media:2048"


def test_voice_ready_selects_preferred_encryption_mode() -> None:
    ready = VoiceReady(
        ssrc=1,
        ip="127.0.0.1",
        port=5000,
        modes=("aead_xchacha20_poly1305_rtpsize",),
    )

    assert ready.select_mode(VoiceGatewayConfig()) == VoiceEncryptionMode.AEAD_XCHACHA20_POLY1305_RTPSIZE


def test_ip_discovery_packet_and_response_parser() -> None:
    packet = build_ip_discovery_packet(123)
    assert struct.unpack_from(">HHI", packet, 0) == (1, 70, 123)

    response = bytearray(74)
    struct.pack_into(">HHI", response, 0, 2, 70, 123)
    response[8:8 + len(b"203.0.113.10")] = b"203.0.113.10"
    struct.pack_into(">H", response, 72, 50000)

    assert parse_ip_discovery_response(bytes(response)) == ("203.0.113.10", 50000)


@pytest.mark.asyncio
async def test_voice_manager_waits_for_state_and_server_update() -> None:
    bot = FakeBot()
    manager = VoiceManager(bot)  # type: ignore[arg-type]

    async def emit_updates() -> None:
        await asyncio.sleep(0)
        manager.handle_gateway_event(
            "VOICE_STATE_UPDATE",
            {
                "guild_id": "10",
                "channel_id": "20",
                "user_id": "30",
                "session_id": "session",
            },
        )
        manager.handle_gateway_event(
            "VOICE_SERVER_UPDATE",
            {
                "guild_id": "10",
                "token": "token",
                "endpoint": "voice.example",
            },
        )

    emit_task = asyncio.create_task(emit_updates())
    state, server = await manager.request_join(10, 20, wait_timeout=0.1)
    await emit_task

    assert state.session_id == "session"
    assert server.token == "token"
    assert bot.runtime.payloads == [
        {
            "op": 4,
            "d": {
                "guild_id": "10",
                "channel_id": "20",
                "self_mute": False,
                "self_deaf": False,
            },
        }
    ]


@pytest.mark.asyncio
async def test_voice_connection_establishes_udp_transport_and_selects_mode() -> None:
    bot = FakeBot()
    connection = VoiceConnection(
        bot=bot,  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(),
    )
    connection.ready = VoiceReady(
        ssrc=1,
        ip="127.0.0.1",
        port=5000,
        modes=("aead_xchacha20_poly1305_rtpsize",),
    )

    class FakeUDP:
        def __init__(self) -> None:
            self.connect_calls = 0
            self.discover_calls: list[int] = []

        async def connect(self) -> None:
            self.connect_calls += 1

        async def discover_ip(self, ssrc: int) -> tuple[str, int]:
            self.discover_calls.append(ssrc)
            return "203.0.113.10", 54321

    sent: list[tuple[str, int, str]] = []

    async def fake_select_protocol(address: str, port: int, mode: str) -> None:
        sent.append((address, port, mode))

    udp = FakeUDP()
    connection.udp = udp  # type: ignore[assignment]
    connection.select_protocol = fake_select_protocol  # type: ignore[method-assign]

    await connection._establish_udp_transport()

    assert udp.connect_calls == 1
    assert udp.discover_calls == [1]
    assert sent == [("203.0.113.10", 54321, "aead_xchacha20_poly1305_rtpsize")]


@pytest.mark.asyncio
async def test_voice_connection_resume_sends_seq_ack_payload() -> None:
    bot = FakeBot()
    connection = VoiceConnection(
        bot=bot,  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(),
    )

    sent: list[dict[str, Any]] = []

    class FakeWS:
        closed = False

        async def send_json(self, payload: dict[str, Any]) -> None:
            sent.append(payload)

    connection._ws = FakeWS()  # type: ignore[assignment]
    connection._last_sequence = 15

    await connection.resume()

    assert sent == [
        {
            "op": 7,
            "d": {
                "server_id": "10",
                "session_id": "session",
                "token": "token",
                "seq_ack": 15,
            },
        }
    ]


@pytest.mark.asyncio
async def test_voice_connection_builds_rtp_packet_and_sends_audio_frame() -> None:
    bot = FakeBot()
    connection = VoiceConnection(
        bot=bot,  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(),
    )
    connection.ready = VoiceReady(
        ssrc=7,
        ip="127.0.0.1",
        port=5000,
        modes=("aead_xchacha20_poly1305_rtpsize",),
    )

    sent_packets: list[bytes] = []

    class FakeUDP:
        async def send(self, data: bytes) -> None:
            sent_packets.append(data)

    connection.udp = FakeUDP()  # type: ignore[assignment]
    await connection.send_audio_frame(b"\xAA\xBB")

    assert len(sent_packets) == 1
    packet = sent_packets[0]
    assert packet[:2] == b"\x80\x78"
    assert struct.unpack_from(">H", packet, 2)[0] == 0
    assert struct.unpack_from(">I", packet, 4)[0] == 0
    assert struct.unpack_from(">I", packet, 8)[0] == 7
    assert packet[12:] == b"\xAA\xBB"
    assert connection._rtp_sequence == 1
    assert connection._rtp_timestamp == 960


@pytest.mark.asyncio
async def test_voice_connection_stream_audio_controls_speaking() -> None:
    bot = FakeBot()
    connection = VoiceConnection(
        bot=bot,  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(),
    )
    connection.ready = VoiceReady(
        ssrc=7,
        ip="127.0.0.1",
        port=5000,
        modes=("aead_xchacha20_poly1305_rtpsize",),
    )

    class FakeUDP:
        async def send(self, data: bytes) -> None:
            return None

    class FakeWS:
        closed = False

        def __init__(self) -> None:
            self.payloads: list[dict[str, Any]] = []

        async def send_json(self, payload: dict[str, Any]) -> None:
            self.payloads.append(payload)

    ws = FakeWS()
    connection._ws = ws  # type: ignore[assignment]
    connection.udp = FakeUDP()  # type: ignore[assignment]

    async def frames():
        yield b"\x01"
        yield b"\x02"

    await connection.stream_audio(frames(), frame_duration_ms=0)

    assert ws.payloads[0]["op"] == 5
    assert ws.payloads[0]["d"]["speaking"] == 1
    assert ws.payloads[-1]["op"] == 5
    assert ws.payloads[-1]["d"]["speaking"] == 0


@pytest.mark.asyncio
async def test_voice_connection_stream_audio_returns_sent_frame_count() -> None:
    bot = FakeBot()
    connection = VoiceConnection(
        bot=bot,  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(),
    )
    connection.ready = VoiceReady(ssrc=7, ip="127.0.0.1", port=5000, modes=("aead_xchacha20_poly1305_rtpsize",))

    class FakeUDP:
        async def send(self, data: bytes) -> None:
            return None

    class FakeWS:
        closed = False

        async def send_json(self, payload: dict[str, Any]) -> None:
            return None

    connection._ws = FakeWS()  # type: ignore[assignment]
    connection.udp = FakeUDP()  # type: ignore[assignment]

    async def frames():
        yield b"\x01"
        yield b""
        yield b"\x02"

    assert await connection.stream_audio(frames(), frame_duration_ms=0) == 2


def test_audio_backend_status_reports_missing_groups() -> None:
    status = AudioBackendStatus(ffmpeg=False, opuslib=True, pynacl=False, cryptography=True)

    assert status.missing_playback == ("ffmpeg",)
    assert status.missing_encryption == ("PyNaCl",)


@pytest.mark.asyncio
async def test_voice_connection_reports_dave_required_close_code() -> None:
    bot = FakeBot()
    connection = VoiceConnection(
        bot=bot,  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(),
    )

    class FakeWS:
        close_code = 4017

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    connection._ws = FakeWS()  # type: ignore[assignment]

    with pytest.raises(DaveUnsupportedError, match="4017"):
        await connection._receive_until(lambda: False)


@pytest.mark.asyncio
async def test_voice_identify_uses_configured_dave_backend_version() -> None:
    class FakeDaveBackend:
        max_protocol_version = 1

    bot = FakeBot()
    connection = VoiceConnection(
        bot=bot,  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(dave_backend=FakeDaveBackend()),
    )

    sent: list[dict[str, Any]] = []

    class FakeWS:
        closed = False

        async def send_json(self, payload: dict[str, Any]) -> None:
            sent.append(payload)

    connection._ws = FakeWS()  # type: ignore[assignment]
    await connection.identify()

    assert sent[0]["d"]["max_dave_protocol_version"] == 1


@pytest.mark.asyncio
async def test_voice_connection_flushes_dave_transition_ready_payload() -> None:
    bot = FakeBot()
    connection = VoiceConnection(
        bot=bot,  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(),
    )

    sent: list[dict[str, Any]] = []

    class FakeWS:
        closed = False

        async def send_json(self, payload: dict[str, Any]) -> None:
            sent.append(payload)

    connection._ws = FakeWS()  # type: ignore[assignment]
    await connection._handle_ws_payload(
        {"op": 21, "d": {"transition_id": "abc", "protocol_version": 0}}
    )

    assert sent == [{"op": 23, "d": {"transition_id": "abc"}}]


@pytest.mark.asyncio
async def test_voice_connection_sends_dave_key_package_from_backend() -> None:
    class FakeDaveBackend:
        max_protocol_version = 1

        def prepare_epoch(self, transition):
            return DaveKeyPackage({"key_package": "payload"})

        def prepare_transition(self, transition) -> None:
            return None

        def execute_transition(self, transition) -> None:
            return None

        def set_external_sender(self, payload) -> None:
            return None

        def handle_proposals(self, payload):
            return None

        def handle_commit_welcome(self, payload) -> None:
            return None

        def handle_welcome(self, payload) -> None:
            return None

        def handle_invalid_commit_welcome(self, payload) -> None:
            return None

        def encrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
            return b"dave:" + frame

        def decrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
            return frame.removeprefix(b"dave:")

    bot = FakeBot()
    connection = VoiceConnection(
        bot=bot,  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(dave_backend=FakeDaveBackend()),
    )

    sent: list[dict[str, Any]] = []

    class FakeWS:
        closed = False

        async def send_json(self, payload: dict[str, Any]) -> None:
            sent.append(payload)

    connection._ws = FakeWS()  # type: ignore[assignment]
    await connection._handle_ws_payload(
        {"op": 24, "d": {"transition_id": "abc", "protocol_version": 1, "epoch": 7}}
    )

    assert sent == [
        {"op": 26, "d": {"key_package": "payload"}},
        {"op": 23, "d": {"transition_id": "abc"}},
    ]
    assert connection.dave.state.epoch == 7


@pytest.mark.asyncio
async def test_voice_connection_applies_dave_frame_encryption_before_transport() -> None:
    class FakeDaveBackend:
        max_protocol_version = 1

        def encrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
            return b"dave:" + frame

    bot = FakeBot()
    connection = VoiceConnection(
        bot=bot,  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(dave_backend=FakeDaveBackend()),
    )
    connection.ready = VoiceReady(ssrc=7, ip="127.0.0.1", port=5000, modes=())
    connection.dave.state.enabled = True

    sent_packets: list[bytes] = []

    class FakeUDP:
        async def send(self, data: bytes) -> None:
            sent_packets.append(data)

    connection.udp = FakeUDP()  # type: ignore[assignment]
    await connection.send_audio_frame(b"\x01", encrypt=False)

    assert sent_packets[0][12:] == b"dave:\x01"


@pytest.mark.asyncio
async def test_voice_connection_start_speaking_supports_bitmask() -> None:
    bot = FakeBot()
    connection = VoiceConnection(
        bot=bot,  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(),
    )
    connection.ready = VoiceReady(
        ssrc=7,
        ip="127.0.0.1",
        port=5000,
        modes=("aead_xchacha20_poly1305_rtpsize",),
    )

    class FakeWS:
        closed = False

        def __init__(self) -> None:
            self.payloads: list[dict[str, Any]] = []

        async def send_json(self, payload: dict[str, Any]) -> None:
            self.payloads.append(payload)

    ws = FakeWS()
    connection._ws = ws  # type: ignore[assignment]
    await connection.start_speaking(int(VoiceSpeakingFlag.MICROPHONE | VoiceSpeakingFlag.PRIORITY))
    assert ws.payloads[-1]["d"]["speaking"] == 5


@pytest.mark.asyncio
async def test_iter_file_chunks_reads_all_data(tmp_path) -> None:
    path = tmp_path / "audio.frames"
    path.write_bytes(b"abcdefgh")
    chunks: list[bytes] = []
    async for chunk in iter_file_chunks(str(path), chunk_size=3):
        chunks.append(chunk)
    assert chunks == [b"abc", b"def", b"gh"]
