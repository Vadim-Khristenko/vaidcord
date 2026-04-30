"""Tests for router middleware chaining and FSM policy support."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import pytest

from vaidcord.fsm import FSMMiddleware, FSMScope, MemoryFSMStorage, StorageKey
from vaidcord.filters import F
from vaidcord.dispatcher import Dispatcher
from vaidcord.router import Router
from vaidcord.types import Channel, ChannelType, Event, EventType, Message, User

MiddlewareHandler = Callable[[Event], Awaitable[Any]]


def _make_message_event(content: str = "hello") -> Event:
    user = User(id=100, username="tester")
    channel = Channel(id=200, type=ChannelType.TEXT)
    message = Message(
        id=300,
        channel=channel,
        author=user,
        content=content,
        timestamp=datetime.now(),
    )
    return Event(
        type=EventType.MESSAGE_CREATE,
        data={"user_id": str(user.id), "channel_id": str(channel.id), "guild_id": "500"},
        message=message,
        user=user,
        channel=channel,
    )


@pytest.mark.asyncio
async def test_middlewares_wrap_handler_in_priority_order() -> None:
    router = Router()
    calls: list[str] = []

    @router.middleware(priority=5)
    async def mw_mid(event: Event, handler: MiddlewareHandler):
        calls.append("mid_before")
        result = await handler(event)
        calls.append("mid_after")
        return result

    @router.middleware(priority=10)
    async def mw_high(event: Event, handler: MiddlewareHandler):
        calls.append("high_before")
        result = await handler(event)
        calls.append("high_after")
        return result

    @router.on_message()
    async def handler(event: Event) -> str:
        calls.append("handler")
        return "ok"

    result = await router.propagate_event(_make_message_event())
    assert result == "ok"
    assert calls == [
        "high_before",
        "mid_before",
        "handler",
        "mid_after",
        "high_after",
    ]


@pytest.mark.asyncio
async def test_message_alias_works_like_on_message() -> None:
    router = Router()
    calls: list[str] = []

    @router.message()
    async def handler(event: Event) -> None:
        calls.append("ok")

    await router.propagate_event(_make_message_event())
    assert calls == ["ok"]


@pytest.mark.asyncio
async def test_middleware_can_be_scoped_to_event_types() -> None:
    router = Router()
    calls: list[str] = []

    @router.middleware(event_types=[EventType.GUILD_CREATE])
    async def only_guild(event: Event, handler: MiddlewareHandler):
        calls.append("guild_mw")
        return await handler(event)

    @router.on_message()
    async def on_message(event: Event) -> None:
        calls.append("message_handler")

    await router.propagate_event(_make_message_event())
    assert calls == ["message_handler"]


@pytest.mark.asyncio
async def test_parent_middlewares_apply_to_child_handlers() -> None:
    parent = Router(name="parent")
    child = Router(name="child")
    parent.include_router(child)
    calls: list[str] = []

    @parent.middleware(priority=50)
    async def parent_mw(event: Event, handler: MiddlewareHandler):
        calls.append("parent_before")
        result = await handler(event)
        calls.append("parent_after")
        return result

    @child.middleware(priority=10)
    async def child_mw(event: Event, handler: MiddlewareHandler):
        calls.append("child_before")
        result = await handler(event)
        calls.append("child_after")
        return result

    @child.on_message()
    async def handler(event: Event) -> str:
        calls.append("handler")
        return "ok"

    result = await parent.propagate_event(_make_message_event())
    assert result == "ok"
    assert calls == [
        "parent_before",
        "child_before",
        "handler",
        "child_after",
        "parent_after",
    ]


@pytest.mark.asyncio
async def test_fsm_middleware_builds_multi_scope_contexts() -> None:
    storage = MemoryFSMStorage()
    router = Router(name="fsm")
    router.add_middleware(FSMMiddleware(storage=storage))
    captured_context: dict[str, Any] = {}

    @router.on_message()
    async def handler(event: Event) -> None:
        captured_context.update(event.context)

    event = _make_message_event("hello")
    await router.propagate_event(event)

    fsm_map = captured_context["fsm_map"]
    assert FSMScope.USER in fsm_map
    assert FSMScope.CHANNEL in fsm_map
    assert FSMScope.GUILD in fsm_map
    assert FSMScope.MEMBER in fsm_map
    assert captured_context["fsm"] is fsm_map[FSMScope.MEMBER]


@pytest.mark.asyncio
async def test_fsm_state_filter_works_for_member_and_channel_scopes() -> None:
    storage = MemoryFSMStorage()
    router = Router(name="fsm")
    router.add_middleware(FSMMiddleware(storage=storage))
    captured: list[str] = []

    await storage.set_state(StorageKey.member(guild_id=500, user_id=100), "member:step")
    await storage.set_state(StorageKey.channel(channel_id=200), "channel:locked")

    @router.on_message_state("member:step", scope=FSMScope.MEMBER)
    async def member_handler(event: Event) -> None:
        captured.append("member")

    @router.on_message_state("channel:locked", scope=FSMScope.CHANNEL)
    async def channel_handler(event: Event) -> None:
        captured.append("channel")

    await router.propagate_event(_make_message_event("hello"))
    assert captured == ["member", "channel"]


@pytest.mark.asyncio
async def test_storage_supports_fast_bulk_policy_updates() -> None:
    storage = MemoryFSMStorage()
    await storage.set_many_states(
        {
            StorageKey.topic(900): "topic:active",
            StorageKey.channel(200): "channel:active",
            StorageKey.user(100): "user:active",
        }
    )
    await storage.set_state_for(
        FSMScope.MEMBER,
        "member:active",
        guild_id=500,
        user_id=100,
    )

    assert await storage.get_state(StorageKey.topic(900)) == "topic:active"
    assert await storage.get_state(StorageKey.channel(200)) == "channel:active"
    assert await storage.get_state(StorageKey.user(100)) == "user:active"
    assert (
        await storage.get_state(StorageKey.member(guild_id=500, user_id=100))
        == "member:active"
    )


@pytest.mark.asyncio
async def test_router_dependency_injection_and_filter_data_injection() -> None:
    router = Router(name="di")
    router.provide("service_name", "svc")
    captured: dict[str, Any] = {}

    @router.on_message(F.message.content.startswith("/start"))
    async def handler(event: Event, service_name: str, startswith: str) -> None:
        captured["service_name"] = service_name
        captured["startswith"] = startswith
        captured["content"] = event.message.content if event.message else ""

    await router.propagate_event(_make_message_event("/start hello"))
    assert captured["service_name"] == "svc"
    assert captured["startswith"] == "/start"
    assert captured["content"] == "/start hello"


@pytest.mark.asyncio
async def test_dispatcher_lifecycle_hooks_startup_shutdown_reconnect() -> None:
    dp = Dispatcher()
    calls: list[str] = []

    @dp.on_startup()
    async def _on_startup() -> None:
        calls.append("startup")

    @dp.on_shutdown()
    async def _on_shutdown() -> None:
        calls.append("shutdown")

    @dp.on_reconnect()
    async def _on_reconnect() -> None:
        calls.append("reconnect")

    await dp.startup()
    await dp.reconnect()
    await dp.shutdown()

    assert calls == ["startup", "reconnect", "shutdown"]


@pytest.mark.asyncio
async def test_dispatcher_include_routers_and_start_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    dp = Dispatcher()
    r1 = Router(name="r1")
    r2 = Router(name="r2")
    dp.include_routers(r1, r2)
    assert len(dp._routers) == 2

    class FakeBot:
        def __init__(self) -> None:
            self.included = []
            self.started = False

        def include_router(self, router: Router) -> None:
            self.included.append(router)

        async def start(self) -> None:
            self.started = True

    bot = FakeBot()
    await dp.start_polling(bot)  # type: ignore[arg-type]
    assert bot.started is True
    assert bot.included == [dp]


@pytest.mark.asyncio
async def test_dispatcher_auto_registers_fsm_middleware() -> None:
    dp = Dispatcher()
    assert dp.fsm is not None
    assert any(config.middleware is dp.fsm for config in dp._middlewares)


@pytest.mark.asyncio
async def test_dispatcher_start_webhook_calls_delete_webhook() -> None:
    dp = Dispatcher()
    calls: list[bool] = []

    class FakeBot:
        def include_router(self, router: Router) -> None:
            self.router = router

        async def start(self) -> None:
            return None

        async def delete_webhook(self, *, drop_pending_updates: bool = False) -> None:
            calls.append(drop_pending_updates)

    bot = FakeBot()
    await dp.start_webhook(bot, drop_pending_updates=True)  # type: ignore[arg-type]
    assert calls == [True]


def test_dispatcher_cannot_include_dispatcher() -> None:
    root = Dispatcher()
    child = Dispatcher()
    with pytest.raises(ValueError):
        root.include_router(child)
