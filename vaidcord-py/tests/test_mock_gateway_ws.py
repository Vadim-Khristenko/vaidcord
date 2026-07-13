"""Tests for the mock server's networked WebSocket gateway (``/gateway``)."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import aiohttp
import pytest

from vaidcord.mock import MockDiscordServer, MockServerConfig

pytestmark = pytest.mark.asyncio


async def _recv(ws: aiohttp.ClientWebSocketResponse, wait_timeout: float = 5.0) -> dict[str, Any]:
    return await asyncio.wait_for(ws.receive_json(), timeout=wait_timeout)


async def _identify(
    ws: aiohttp.ClientWebSocketResponse,
    *,
    token: str = "mock-token",
    intents: int = 513,
) -> dict[str, Any]:
    """Send IDENTIFY and return the READY dispatch payload."""
    await ws.send_json(
        {
            "op": 2,
            "d": {
                "token": token,
                "intents": intents,
                "properties": {"os": "test", "browser": "test", "device": "test"},
            },
        }
    )
    return await _recv(ws)


@pytest.fixture
async def server():
    server = MockDiscordServer(port=0)
    await server.start()
    yield server
    await server.stop()


async def test_gateway_bot_returns_local_ws_url(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{server.base_url}/v10/gateway/bot") as resp:
            assert resp.status == 200
            data = await resp.json()
    assert data["url"] == server.ws_url
    assert data["url"].startswith("ws://127.0.0.1:")
    assert data["url"].endswith("/gateway")
    assert data["shards"] == 1
    assert "session_start_limit" in data


async def test_hello_identify_ready_and_heartbeat_ack(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(server.ws_url) as ws:
            hello = await _recv(ws)
            assert hello["op"] == 10
            assert hello["d"]["heartbeat_interval"] == server.config.heartbeat_interval_ms

            ready = await _identify(ws)
            assert ready["op"] == 0
            assert ready["t"] == "READY"
            assert ready["s"] == 1
            assert ready["d"]["user"]["username"] == "MockBot"
            assert ready["d"]["session_id"]
            assert ready["d"]["resume_gateway_url"] == server.ws_url
            assert ready["d"]["guilds"][0]["id"] == "999"

            await ws.send_json({"op": 1, "d": 1})
            ack = await _recv(ws)
            assert ack["op"] == 11


async def test_identify_without_token_closes_4004(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(server.ws_url) as ws:
            await _recv(ws)  # HELLO
            await ws.send_json({"op": 2, "d": {"token": "", "intents": 0}})
            msg = await asyncio.wait_for(ws.receive(), timeout=5)
            assert msg.type == aiohttp.WSMsgType.CLOSE
            assert msg.data == 4004


async def test_rest_message_create_broadcasts_to_gateway(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(server.ws_url) as ws:
            await _recv(ws)  # HELLO
            await _identify(ws)

            async with session.post(
                f"{server.base_url}/v10/channels/123/messages",
                json={"content": "broadcast me"},
            ) as resp:
                assert resp.status == 200
                created = await resp.json()

            dispatch = await _recv(ws)
            assert dispatch["op"] == 0
            assert dispatch["t"] == "MESSAGE_CREATE"
            assert dispatch["s"] == 2  # READY was s=1
            assert dispatch["d"]["id"] == created["id"]
            assert dispatch["d"]["content"] == "broadcast me"


async def test_control_plane_injection_broadcasts_to_gateway(
    server: MockDiscordServer,
) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(server.ws_url) as ws:
            await _recv(ws)  # HELLO
            await _identify(ws)

            async with session.post(
                f"{server.local_url}api/mock/messages",
                json={"content": "injected", "author_username": "Injector"},
            ) as resp:
                assert resp.status == 200

            dispatch = await _recv(ws)
            assert dispatch["t"] == "MESSAGE_CREATE"
            assert dispatch["d"]["content"] == "injected"
            assert dispatch["d"]["author"]["username"] == "Injector"


async def test_typing_edit_delete_dispatch_gateway_events(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(server.ws_url) as ws:
            await _recv(ws)  # HELLO
            await _identify(ws)

            async with session.post(
                f"{server.base_url}/v10/channels/123/messages",
                json={"content": "will change"},
            ) as resp:
                created = await resp.json()
            assert (await _recv(ws))["t"] == "MESSAGE_CREATE"

            async with session.patch(
                f"{server.base_url}/v10/channels/123/messages/{created['id']}",
                json={"content": "changed"},
            ) as resp:
                assert resp.status == 200
            update = await _recv(ws)
            assert update["t"] == "MESSAGE_UPDATE"
            assert update["d"]["content"] == "changed"

            async with session.delete(
                f"{server.base_url}/v10/channels/123/messages/{created['id']}"
            ) as resp:
                assert resp.status == 204
            delete = await _recv(ws)
            assert delete["t"] == "MESSAGE_DELETE"
            assert delete["d"]["id"] == created["id"]

            async with session.post(f"{server.base_url}/v10/channels/123/typing") as resp:
                assert resp.status == 204
            typing = await _recv(ws)
            assert typing["t"] == "TYPING_START"
            assert typing["d"]["channel_id"] == "123"


async def test_resume_replays_buffered_events(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(server.ws_url) as ws:
            await _recv(ws)  # HELLO
            ready = await _identify(ws)
            session_id = ready["d"]["session_id"]
            last_seq = ready["s"]

        # Socket is now closed; events keep buffering against the session.
        for content in ("missed one", "missed two"):
            async with session.post(
                f"{server.local_url}api/mock/messages",
                json={"content": content},
            ) as resp:
                assert resp.status == 200

        async with session.ws_connect(server.ws_url) as ws:
            await _recv(ws)  # HELLO
            await ws.send_json(
                {
                    "op": 6,
                    "d": {"token": "mock-token", "session_id": session_id, "seq": last_seq},
                }
            )
            first = await _recv(ws)
            second = await _recv(ws)
            resumed = await _recv(ws)

    assert first["t"] == "MESSAGE_CREATE"
    assert first["d"]["content"] == "missed one"
    assert first["s"] == last_seq + 1
    assert second["d"]["content"] == "missed two"
    assert second["s"] == last_seq + 2
    assert resumed["t"] == "RESUMED"
    assert resumed["s"] == last_seq + 3


async def test_resume_unknown_session_gets_invalid_session(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(server.ws_url) as ws:
            await _recv(ws)  # HELLO
            await ws.send_json(
                {"op": 6, "d": {"token": "mock-token", "session_id": "nope", "seq": 42}}
            )
            payload = await _recv(ws)
            assert payload["op"] == 9
            assert payload["d"] is False


async def test_op7_and_op9_can_be_pushed_from_control_plane(
    server: MockDiscordServer,
) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(server.ws_url) as ws:
            await _recv(ws)  # HELLO
            await _identify(ws)

            async with session.post(
                f"{server.local_url}api/mock/gateway/reconnect", json={}
            ) as resp:
                assert (await resp.json())["sent"] == 1
            reconnect = await _recv(ws)
            assert reconnect["op"] == 7

            async with session.post(
                f"{server.local_url}api/mock/gateway/invalidate",
                json={"resumable": True},
            ) as resp:
                assert (await resp.json())["sent"] == 1
            invalid = await _recv(ws)
            assert invalid["op"] == 9
            assert invalid["d"] is True


async def test_gateway_sessions_are_tracked(server: MockDiscordServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(server.ws_url) as ws:
            await _recv(ws)  # HELLO
            ready = await _identify(ws)
            await ws.send_json({"op": 1, "d": 1})
            await _recv(ws)  # ACK

            async with session.get(f"{server.local_url}api/mock/gateway") as resp:
                state = await resp.json()

            assert state["ws_url"] == server.ws_url
            assert len(state["sessions"]) == 1
            info = state["sessions"][0]
            assert info["session_id"] == ready["d"]["session_id"]
            assert info["connected"] is True
            assert info["heartbeats"] == 1

        # After the socket closes the session lingers for RESUME but reports
        # disconnected.
        async with aiohttp.ClientSession() as session2:
            async with session2.get(f"{server.local_url}api/mock/gateway") as resp:
                state = await resp.json()
            assert state["sessions"][0]["connected"] is False


async def test_custom_gateway_url_is_honored() -> None:
    server = MockDiscordServer(port=0, gateway_url="wss://example.invalid/gw")
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{server.base_url}/v10/gateway/bot") as resp:
                data = await resp.json()
        assert data["url"] == "wss://example.invalid/gw"
    finally:
        await server.stop()


async def test_event_buffer_size_is_configurable() -> None:
    server = MockDiscordServer(port=0, config=MockServerConfig(event_buffer_size=1))
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(server.ws_url) as ws:
                await _recv(ws)  # HELLO
                ready = await _identify(ws)
                session_id = ready["d"]["session_id"]

            for content in ("dropped", "kept"):
                async with session.post(
                    f"{server.local_url}api/mock/messages",
                    json={"content": content},
                ) as resp:
                    assert resp.status == 200

            async with session.ws_connect(server.ws_url) as ws:
                await _recv(ws)  # HELLO
                await ws.send_json(
                    {"op": 6, "d": {"token": "t", "session_id": session_id, "seq": 1}}
                )
                replayed = await _recv(ws)
                resumed = await _recv(ws)
        assert replayed["d"]["content"] == "kept"
        assert resumed["t"] == "RESUMED"
    finally:
        await server.stop()


async def test_real_bot_connects_end_to_end(server: MockDiscordServer) -> None:
    from vaidcord.bot import Bot, BotConfig

    bot = Bot(
        config=BotConfig(
            token="test-token",
            base_url=server.base_url,
            api_version="10",
            auto_sync_commands=False,
        )
    )
    received: asyncio.Queue[str] = asyncio.Queue()

    @bot.on_message()
    async def _on_message(event):  # noqa: ANN001
        if event.message is not None:
            await received.put(event.message.content)

    run_task = asyncio.create_task(bot.start())
    try:
        assert await bot.wait_until_ready(5.0)
        assert bot.user is not None
        assert bot.user.username == "MockBot"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{server.local_url}api/mock/messages",
                json={"content": "hello real bot", "author_id": "2"},
            ) as resp:
                assert resp.status == 200

        content = await asyncio.wait_for(received.get(), timeout=5.0)
        assert content == "hello real bot"
    finally:
        await bot.stop()
        run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run_task
        await bot.api_client.close()
