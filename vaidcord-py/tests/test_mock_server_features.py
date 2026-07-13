"""Tests for mock server simulation features.

Covers rate limiting, chaos injection, request validation, permissions,
snowflakes, state snapshots, the scenario runner and the SSE event feed.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime

import aiohttp
import pytest

from vaidcord.mock import MockDiscordServer, MockServerConfig, snowflake_time
from vaidcord.mock.snowflake import SnowflakeGenerator

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def server():
    server = MockDiscordServer(port=0)
    await server.start()
    yield server
    await server.stop()


# --------------------------------------------------------------------------- #
# Snowflakes                                                                   #
# --------------------------------------------------------------------------- #


async def test_snowflake_generator_encodes_current_time() -> None:
    generator = SnowflakeGenerator()
    snowflake = generator.generate()
    decoded = snowflake_time(snowflake)
    assert abs((datetime.now(UTC) - decoded).total_seconds()) < 5


async def test_snowflake_generator_is_strictly_increasing() -> None:
    generator = SnowflakeGenerator()
    values = [generator.generate() for _ in range(5000)]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


async def test_message_ids_are_timestamped_snowflakes(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.base_url}/v10/channels/123/messages",
            json={"content": "snowflake please"},
        ) as resp:
            message = await resp.json()
    decoded = snowflake_time(message["id"])
    assert abs((datetime.now(UTC) - decoded).total_seconds()) < 10


# --------------------------------------------------------------------------- #
# Validation                                                                   #
# --------------------------------------------------------------------------- #


async def test_empty_message_returns_50006(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.base_url}/v10/channels/123/messages",
            json={"content": "   "},
        ) as resp:
            assert resp.status == 400
            body = await resp.json()
    assert body["code"] == 50006
    assert body["message"] == "Cannot send an empty message"


async def test_oversized_content_returns_50035(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.base_url}/v10/channels/123/messages",
            json={"content": "x" * 2001},
        ) as resp:
            assert resp.status == 400
            body = await resp.json()
    assert body["code"] == 50035
    assert body["errors"]["content"]["_errors"][0]["code"] == "BASE_TYPE_MAX_LENGTH"


async def test_invalid_json_body_returns_50109(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.base_url}/v10/channels/123/messages",
            data=b"this is not json",
            headers={"Content-Type": "application/json"},
        ) as resp:
            assert resp.status == 400
            body = await resp.json()
    assert body["code"] == 50109


async def test_embed_only_message_is_accepted(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.base_url}/v10/channels/123/messages",
            json={"embeds": [{"title": "no content needed"}]},
        ) as resp:
            assert resp.status == 200
            body = await resp.json()
    assert body["embeds"][0]["title"] == "no content needed"


async def test_strict_validation_can_be_disabled() -> None:
    server = MockDiscordServer(port=0, config=MockServerConfig(strict_validation=False))
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{server.base_url}/v10/channels/123/messages",
                json={},
            ) as resp:
                assert resp.status == 200
    finally:
        await server.stop()


# --------------------------------------------------------------------------- #
# Rate limiting                                                                #
# --------------------------------------------------------------------------- #


async def test_per_route_rate_limit_headers_and_429() -> None:
    config = MockServerConfig(
        rate_limit_enabled=True,
        rate_limit_per_route=2,
        rate_limit_window=30.0,
        global_rate_limit=1000,
    )
    server = MockDiscordServer(port=0, config=config)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{server.base_url}/v10/users/@me") as resp:
                assert resp.status == 200
                assert resp.headers["X-RateLimit-Limit"] == "2"
                assert resp.headers["X-RateLimit-Remaining"] == "1"
                assert float(resp.headers["X-RateLimit-Reset-After"]) > 0
                bucket = resp.headers["X-RateLimit-Bucket"]

            async with session.get(f"{server.base_url}/v10/users/@me") as resp:
                assert resp.status == 200
                assert resp.headers["X-RateLimit-Remaining"] == "0"
                assert resp.headers["X-RateLimit-Bucket"] == bucket

            async with session.get(f"{server.base_url}/v10/users/@me") as resp:
                assert resp.status == 429
                body = await resp.json()
                assert body["message"] == "You are being rate limited."
                assert body["retry_after"] > 0
                assert body["global"] is False
                assert resp.headers["X-RateLimit-Remaining"] == "0"
                assert "Retry-After" in resp.headers

            # A different route has its own bucket and is not limited.
            async with session.get(f"{server.base_url}/v10/guilds/999") as resp:
                assert resp.status == 200
    finally:
        await server.stop()


async def test_global_rate_limit_returns_global_429() -> None:
    config = MockServerConfig(
        rate_limit_enabled=True,
        rate_limit_per_route=100,
        global_rate_limit=3,
        global_rate_limit_window=30.0,
    )
    server = MockDiscordServer(port=0, config=config)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            for _ in range(3):
                async with session.get(f"{server.base_url}/v10/users/@me") as resp:
                    assert resp.status == 200
            async with session.get(f"{server.base_url}/v10/guilds/999") as resp:
                assert resp.status == 429
                body = await resp.json()
                assert body["global"] is True
                assert resp.headers["X-RateLimit-Global"] == "true"
    finally:
        await server.stop()


async def test_rate_limits_can_be_toggled_at_runtime(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        # Off by default.
        async with session.get(f"{server.base_url}/v10/users/@me") as resp:
            assert "X-RateLimit-Limit" not in resp.headers

        async with session.patch(
            f"{server.local_url}api/mock/ratelimit",
            json={"enabled": True, "per_route_limit": 1, "per_route_window": 30},
        ) as resp:
            assert resp.status == 200
            body = await resp.json()
            assert body["enabled"] is True
            assert body["per_route_limit"] == 1

        async with session.get(f"{server.base_url}/v10/users/@me") as resp:
            assert resp.status == 200
        async with session.get(f"{server.base_url}/v10/users/@me") as resp:
            assert resp.status == 429

        async with session.patch(
            f"{server.local_url}api/mock/ratelimit",
            json={"enabled": False},
        ) as resp:
            assert resp.status == 200
        async with session.get(f"{server.base_url}/v10/users/@me") as resp:
            assert resp.status == 200

        # Control plane itself is never rate limited.
        async with session.get(f"{server.local_url}api/mock/ratelimit") as resp:
            assert resp.status == 200
            assert (await resp.json())["enabled"] is False


# --------------------------------------------------------------------------- #
# Chaos                                                                        #
# --------------------------------------------------------------------------- #


async def test_chaos_error_injection(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.local_url}api/mock/chaos",
            json={"error_rate": 1.0, "error_status": 503, "error_code": 0},
        ) as resp:
            assert resp.status == 200
            body = await resp.json()
            assert body["error_rate"] == 1.0

        async with session.get(f"{server.base_url}/v10/users/@me") as resp:
            assert resp.status == 503
            body = await resp.json()
            assert body["message"] == "Mock chaos error injected"
            assert resp.headers["X-Mock-Chaos"] == "error"

        # Control plane must stay reachable while chaos is on.
        async with session.post(
            f"{server.local_url}api/mock/chaos", json={"error_rate": 0.0}
        ) as resp:
            assert resp.status == 200

        async with session.get(f"{server.base_url}/v10/users/@me") as resp:
            assert resp.status == 200


async def test_chaos_latency_injection(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.local_url}api/mock/chaos", json={"latency_ms": 80}
        ) as resp:
            assert resp.status == 200

        started = time.perf_counter()
        async with session.get(f"{server.base_url}/v10/users/@me") as resp:
            assert resp.status == 200
        elapsed = time.perf_counter() - started
        assert elapsed >= 0.07


async def test_chaos_settings_visible_in_state(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.local_url}api/mock/chaos", json={"latency_ms": 5, "jitter_ms": 3}
        ) as resp:
            assert resp.status == 200
        async with session.get(f"{server.local_url}api/mock/state") as resp:
            state = await resp.json()
    assert state["chaos"]["latency_ms"] == 5
    assert state["chaos"]["jitter_ms"] == 3


# --------------------------------------------------------------------------- #
# Permissions                                                                  #
# --------------------------------------------------------------------------- #


async def test_permission_denied_channels_return_403(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.local_url}api/mock/permissions",
            json={"enforce": True, "channel_id": "123"},
        ) as resp:
            body = await resp.json()
            assert body["enforce"] is True
            assert body["denied_channels"] == ["123"]

        async with session.get(f"{server.base_url}/v10/channels/123") as resp:
            assert resp.status == 403
            body = await resp.json()
            assert body["code"] == 50001
            assert body["message"] == "Missing Access"

        async with session.post(
            f"{server.local_url}api/mock/permissions",
            json={"channel_id": "123", "allow": True},
        ) as resp:
            assert (await resp.json())["denied_channels"] == []

        async with session.get(f"{server.base_url}/v10/channels/123") as resp:
            assert resp.status == 200


# --------------------------------------------------------------------------- #
# Snapshots                                                                    #
# --------------------------------------------------------------------------- #


async def test_state_export_import_roundtrip(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.local_url}api/mock/messages",
            json={"content": "snapshot me", "channel_id": "123"},
        ) as resp:
            message = await resp.json()

        async with session.get(f"{server.local_url}api/mock/state/export") as resp:
            assert resp.status == 200
            snapshot = await resp.json()
        assert snapshot["version"] == 1
        assert snapshot["messages"][0]["content"] == "snapshot me"

        async with session.post(f"{server.local_url}api/mock/reset") as resp:
            assert resp.status == 200
        async with session.get(
            f"{server.base_url}/v10/channels/123/messages/{message['id']}"
        ) as resp:
            assert resp.status == 404

        async with session.post(
            f"{server.local_url}api/mock/state/import", json=snapshot
        ) as resp:
            assert resp.status == 200
            summary = await resp.json()
            assert summary["ok"] is True
            assert summary["messages"] == 1

        async with session.get(
            f"{server.base_url}/v10/channels/123/messages/{message['id']}"
        ) as resp:
            assert resp.status == 200
            restored = await resp.json()
            assert restored["content"] == "snapshot me"


async def test_state_import_rejects_bad_payload(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.local_url}api/mock/state/import", json={"users": []}
        ) as resp:
            assert resp.status == 400
            body = await resp.json()
            assert body["code"] == 50035


# --------------------------------------------------------------------------- #
# Scenario runner                                                              #
# --------------------------------------------------------------------------- #


async def _wait_for_scenario(
    session: aiohttp.ClientSession,
    server: MockDiscordServer,
    scenario_id: str,
    *,
    wait_timeout: float = 5.0,
) -> dict:
    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        async with session.get(f"{server.local_url}api/mock/scenario") as resp:
            scenarios = {item["id"]: item for item in await resp.json()}
        record = scenarios.get(scenario_id)
        if record is not None and record["status"] != "running":
            return record
        await asyncio.sleep(0.02)
    raise AssertionError(f"scenario {scenario_id} did not finish within {wait_timeout}s")


async def test_scenario_runner_executes_timed_steps(server: MockDiscordServer) -> None:
    steps = [
        {"at": 0.0, "action": "message", "data": {"content": "step one", "channel_id": "123"}},
        {"at": 0.05, "action": "typing", "data": {"channel_id": "123", "user_id": "2"}},
        {"at": 0.1, "action": "message", "data": {"content": "step two", "channel_id": "123"}},
    ]
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.local_url}api/mock/scenario",
            json={"name": "demo", "steps": steps},
        ) as resp:
            assert resp.status == 202
            record = await resp.json()
            assert record["status"] == "running"
            assert record["steps_total"] == 3

        finished = await _wait_for_scenario(session, server, record["id"])
        assert finished["status"] == "completed"
        assert finished["steps_done"] == 3

        async with session.get(f"{server.local_url}api/mock/state") as resp:
            state = await resp.json()
    contents = [message["content"] for message in state["messages"]]
    assert contents == ["step one", "step two"]
    assert state["typing_events"][0]["channel_id"] == "123"


async def test_scenario_rejects_unknown_action(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.local_url}api/mock/scenario",
            json={"steps": [{"at": 0, "action": "explode"}]},
        ) as resp:
            assert resp.status == 400
            body = await resp.json()
            assert body["code"] == 50035


async def test_scenario_can_be_cancelled(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.local_url}api/mock/scenario",
            json={"steps": [{"at": 30.0, "action": "message", "data": {"content": "late"}}]},
        ) as resp:
            record = await resp.json()

        async with session.delete(
            f"{server.local_url}api/mock/scenario/{record['id']}"
        ) as resp:
            assert resp.status == 200

        finished = await _wait_for_scenario(session, server, record["id"])
        assert finished["status"] == "cancelled"


async def test_scenario_chaos_step_applies_settings(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.local_url}api/mock/scenario",
            json={"steps": [{"at": 0.0, "action": "chaos", "data": {"error_rate": 1.0}}]},
        ) as resp:
            record = await resp.json()
        finished = await _wait_for_scenario(session, server, record["id"])
        assert finished["status"] == "completed"

        async with session.get(f"{server.local_url}api/mock/chaos") as resp:
            assert (await resp.json())["error_rate"] == 1.0


# --------------------------------------------------------------------------- #
# SSE event feed                                                               #
# --------------------------------------------------------------------------- #


async def test_sse_feed_streams_dispatches(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{server.local_url}api/mock/events") as resp:
            assert resp.status == 200
            assert resp.headers["Content-Type"].startswith("text/event-stream")

            async def read_until_dispatch() -> dict:
                while True:
                    line = await resp.content.readline()
                    text = line.decode().strip()
                    if text.startswith("data: "):
                        payload = json.loads(text[len("data: "):])
                        if payload.get("kind") == "dispatch":
                            return payload

            reader = asyncio.create_task(read_until_dispatch())
            await asyncio.sleep(0.05)
            async with session.post(
                f"{server.local_url}api/mock/messages",
                json={"content": "sse ping"},
            ) as inject:
                assert inject.status == 200
            payload = await asyncio.wait_for(reader, timeout=5.0)
    assert payload["t"] == "MESSAGE_CREATE"


# --------------------------------------------------------------------------- #
# Reset & request inspector metadata                                           #
# --------------------------------------------------------------------------- #


async def test_reset_restores_simulation_defaults(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server.local_url}api/mock/chaos", json={"error_rate": 1.0}
        ) as resp:
            assert resp.status == 200
        async with session.patch(
            f"{server.local_url}api/mock/ratelimit", json={"enabled": True}
        ) as resp:
            assert resp.status == 200

        async with session.post(f"{server.local_url}api/mock/reset") as resp:
            assert resp.status == 200

        async with session.get(f"{server.local_url}api/mock/chaos") as resp:
            assert (await resp.json())["error_rate"] == 0.0
        async with session.get(f"{server.local_url}api/mock/ratelimit") as resp:
            assert (await resp.json())["enabled"] is False
        async with session.get(f"{server.base_url}/v10/users/@me") as resp:
            assert resp.status == 200


async def test_request_log_records_status_and_duration(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{server.base_url}/v10/users/@me") as resp:
            assert resp.status == 200
        async with session.get(f"{server.base_url}/v10/users/does-not-exist") as resp:
            assert resp.status == 404
        # Give the middleware a tick to finalize entries.
        await asyncio.sleep(0)
    ok_entry = next(entry for entry in server.requests if entry["path"] == "/api/v10/users/@me")
    missing_entry = next(
        entry for entry in server.requests if entry["path"] == "/api/v10/users/does-not-exist"
    )
    assert ok_entry["status"] == 200
    assert ok_entry["duration_ms"] >= 0
    assert missing_entry["status"] == 404
