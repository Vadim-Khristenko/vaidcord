from __future__ import annotations

import struct
from typing import Any

import pytest

from vaidcord.voice import (
    VoiceEncryptionMode,
    VoiceGatewayConfig,
    VoiceManager,
    VoiceReady,
    VoiceServerUpdate,
    build_ip_discovery_packet,
    parse_ip_discovery_response,
)


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

    await emit_updates()
    state, server = await manager.request_join(10, 20, wait_timeout=0.1)

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
