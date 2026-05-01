from __future__ import annotations

from typing import Any

import pytest

from vaidcord.api_client import APIClient


@pytest.mark.asyncio
async def test_api_client_resource_helpers_build_expected_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = APIClient("token")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_request(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((method, endpoint, kwargs))
        return {"ok": True}

    monkeypatch.setattr(client, "request", fake_request)

    await client.crosspost_message(1, 2)
    await client.add_reaction(1, 2, "wave:123")
    await client.bulk_delete_messages(1, [2, 3])
    await client.pin_message(1, 2)
    await client.create_channel_invite(1, {"max_age": 60})
    await client.start_thread_from_message(1, 2, {"name": "thread"})
    await client.list_guild_roles(9)
    await client.modify_guild_member(9, 8, {"nick": "neo"})
    await client.fetch_invite("abc", with_counts=True)
    await client.execute_webhook(7, "token", {"content": "hello"}, wait=True)
    await client.create_global_command(5, {"name": "ping"})
    await client.create_interaction_response(4, "itoken", {"type": 4})

    assert calls == [
        ("POST", "/channels/1/messages/2/crosspost", {}),
        ("PUT", "/channels/1/messages/2/reactions/wave%3A123/@me", {}),
        ("POST", "/channels/1/messages/bulk-delete", {"json": {"messages": ["2", "3"]}}),
        ("PUT", "/channels/1/pins/2", {}),
        ("POST", "/channels/1/invites", {"json": {"max_age": 60}}),
        ("POST", "/channels/1/messages/2/threads", {"json": {"name": "thread"}}),
        ("GET", "/guilds/9/roles", {}),
        ("PATCH", "/guilds/9/members/8", {"json": {"nick": "neo"}}),
        ("GET", "/invites/abc", {"params": {"with_counts": True}}),
        ("POST", "/webhooks/7/token", {"json": {"content": "hello"}, "params": {"wait": True}}),
        ("POST", "/applications/5/commands", {"json": {"name": "ping"}}),
        ("POST", "/interactions/4/itoken/callback", {"json": {"type": 4}}),
    ]


@pytest.mark.asyncio
async def test_bot_resource_wrappers_delegate_to_api_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vaidcord import Bot

    bot = Bot(token="token")
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def fake_execute_webhook(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(("execute_webhook", args, kwargs))
        return {"ok": True}

    async def fake_create_interaction_response(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(("create_interaction_response", args, kwargs))
        return {"ok": True}

    monkeypatch.setattr(bot.api_client, "execute_webhook", fake_execute_webhook)
    monkeypatch.setattr(
        bot.api_client,
        "create_interaction_response",
        fake_create_interaction_response,
    )

    await bot.execute_webhook(7, "token", content="hello")
    await bot.create_interaction_response(4, "itoken", type=4)

    assert calls == [
        ("execute_webhook", (7, "token", {"content": "hello"}), {}),
        ("create_interaction_response", (4, "itoken", {"type": 4}), {}),
    ]
