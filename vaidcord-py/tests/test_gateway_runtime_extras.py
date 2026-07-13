"""Tests for gateway presence/member-request helpers and zlib-stream support."""

from __future__ import annotations

import json
import zlib
from typing import Any

import pytest

from vaidcord.gateway_runtime import GatewayRuntime


class FakeWS:
    closed = False

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


class FakeBot:
    def __init__(self) -> None:
        self._sequence = 0
        self._running = True

    def _log_extra(self) -> dict[str, Any]:
        return {}


def make_runtime() -> tuple[GatewayRuntime, FakeWS]:
    runtime = GatewayRuntime(FakeBot())  # type: ignore[arg-type]
    ws = FakeWS()
    runtime._ws = ws  # type: ignore[assignment]
    return runtime, ws


@pytest.mark.asyncio
async def test_update_presence_sends_op3() -> None:
    runtime, ws = make_runtime()
    await runtime.update_presence(
        status="idle",
        activities=[{"name": "vaidcord", "type": 0}],
        afk=True,
        since=123,
    )
    assert ws.payloads == [
        {
            "op": 3,
            "d": {
                "since": 123,
                "activities": [{"name": "vaidcord", "type": 0}],
                "status": "idle",
                "afk": True,
            },
        }
    ]


@pytest.mark.asyncio
async def test_request_guild_members_query_form() -> None:
    runtime, ws = make_runtime()
    await runtime.request_guild_members(42, query="vai", limit=5, presences=True)
    assert ws.payloads == [
        {
            "op": 8,
            "d": {"guild_id": "42", "limit": 5, "presences": True, "query": "vai"},
        }
    ]


@pytest.mark.asyncio
async def test_request_guild_members_user_ids_form_with_nonce() -> None:
    runtime, ws = make_runtime()
    await runtime.request_guild_members(42, user_ids=[1, 2], nonce="abc")
    payload = ws.payloads[0]["d"]
    assert payload["user_ids"] == ["1", "2"]
    assert "query" not in payload
    assert payload["nonce"] == "abc"


def test_zlib_stream_inflate_reassembles_split_frames() -> None:
    runtime, _ = make_runtime()
    runtime._inflator = zlib.decompressobj()

    message = {"op": 11, "d": None}
    compressor = zlib.compressobj()
    compressed = compressor.compress(json.dumps(message).encode())
    compressed += compressor.flush(zlib.Z_SYNC_FLUSH)

    # Split across two websocket frames: no payload until the flush marker.
    midpoint = len(compressed) // 2
    assert runtime._inflate(compressed[:midpoint]) is None
    assert runtime._inflate(compressed[midpoint:]) == message


def test_zlib_stream_inflate_handles_consecutive_payloads() -> None:
    runtime, _ = make_runtime()
    runtime._inflator = zlib.decompressobj()
    compressor = zlib.compressobj()

    first = compressor.compress(json.dumps({"op": 1}).encode()) + compressor.flush(zlib.Z_SYNC_FLUSH)
    second = compressor.compress(json.dumps({"op": 2}).encode()) + compressor.flush(zlib.Z_SYNC_FLUSH)

    assert runtime._inflate(first) == {"op": 1}
    assert runtime._inflate(second) == {"op": 2}
