"""Tests for router middleware chaining and FSM policy support."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, cast

import pytest

from vaidcord.dispatcher import Dispatcher
from vaidcord.filters import F
from vaidcord.fsm import (
    FSMContext,
    FSMMiddleware,
    FSMScope,
    MemoryFSMStorage,
    StorageKey,
)
from vaidcord.router import Router
from vaidcord.types import (
    Channel,
    ChannelType,
    Event,
    EventType,
    Message,
    User,
    WebhookEventType,
)

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
async def test_topic_message_shortcut_accepts_media_channels() -> None:
    router = Router()
    calls: list[str] = []

    @router.on_topic_message()
    async def handler(_event: Event) -> None:
        calls.append("media")

    event = _make_message_event("media")
    event.channel = Channel(id=200, type=ChannelType.GUILD_MEDIA)
    event.message = Message(
        id=300,
        channel=event.channel,
        author=event.user,
        content="media",
        timestamp=datetime.now(),
    )

    await router.propagate_event(event)

    assert calls == ["media"]


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
    router.add_outer_middleware(FSMMiddleware(storage=storage))
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
    router.add_outer_middleware(FSMMiddleware(storage=storage))
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
async def test_fsm_state_handlers_use_pre_event_snapshot() -> None:
    storage = MemoryFSMStorage()
    router = Router(name="fsm")
    router.add_outer_middleware(FSMMiddleware(storage=storage))
    captured: list[str] = []

    @router.on_message_create()
    async def start(_event: Event, fsm: FSMContext) -> None:
        captured.append("start")
        await fsm.set_state("profile:name")

    @router.on_message_state("profile:name")
    async def capture(_event: Event) -> None:
        captured.append("capture")

    event = _make_message_event("/profile")
    await router.propagate_event(event)
    await router.propagate_event(_make_message_event("Alice"))

    assert captured == ["start", "start", "capture"]


@pytest.mark.asyncio
async def test_fsm_state_filter_defaults_to_primary_scope_for_dm_flows() -> None:
    storage = MemoryFSMStorage()
    router = Router(name="fsm")
    router.add_outer_middleware(FSMMiddleware(storage=storage))
    captured: list[str] = []

    event = _make_message_event("Alice")
    event.data.pop("guild_id", None)
    await storage.set_state(StorageKey.user(100), "profile:name")

    @router.on_message_state("profile:name")
    async def capture(_event: Event) -> None:
        captured.append("capture")

    await router.propagate_event(event)

    assert captured == ["capture"]


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
async def test_handler_can_receive_only_injected_bot_dependency() -> None:
    router = Router(name="di-only")
    sentinel = object()
    captured: list[object] = []
    router.provide("bot", sentinel)

    @router.on_ready()
    async def ready(bot: object) -> None:
        captured.append(bot)

    await router.propagate_event(Event(type=EventType.READY, data={}))

    assert captured == [sentinel]


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
async def test_dispatcher_start_polling_many_can_share_dispatcher() -> None:
    dp = Dispatcher()
    started: list[str] = []

    class FakeBot(Router):
        def __init__(self, name: str) -> None:
            super().__init__(name=name)
            self.bot_name = name

        async def start(self) -> None:
            started.append(self.bot_name)

        async def delete_webhook(self, *, drop_pending_updates: bool = False) -> dict[str, Any]:
            return {"drop_pending_updates": drop_pending_updates}

    bot_a = FakeBot("a")
    bot_b = FakeBot("b")

    await dp.start_polling_many([bot_a, bot_b])

    assert sorted(started) == ["a", "b"]
    assert dp in bot_a._routers
    assert dp in bot_b._routers


@pytest.mark.asyncio
async def test_event_bot_context_overrides_shared_dispatcher_dependency() -> None:
    dp = Dispatcher()
    captured: list[object] = []
    bot_a = object()
    bot_b = object()

    @dp.on_ready()
    async def ready(bot: object) -> None:
        captured.append(bot)

    event_a = Event(type=EventType.READY, data={})
    event_a.bot = cast(Any, bot_a)
    event_b = Event(type=EventType.READY, data={})
    event_b.bot = cast(Any, bot_b)

    dp.provide("bot", bot_b)
    await dp.propagate_event(event_a)
    await dp.propagate_event(event_b)

    assert captured == [bot_a, bot_b]


@pytest.mark.asyncio
async def test_dispatcher_auto_registers_fsm_middleware() -> None:
    dp = Dispatcher()
    assert dp.fsm is not None
    assert any(config.middleware is dp.fsm for config in dp._outer_middlewares)


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


@pytest.mark.asyncio
async def test_outer_middleware_runs_before_filter_resolution() -> None:
    router = Router()
    seen: list[str] = []

    @router.outer_middleware(priority=100)
    async def gate(event: Event, next_handler):
        event.context["allowed"] = True
        seen.append("outer")
        return await next_handler(event)

    @router.on_message(lambda event: event.context.get("allowed") is True)
    async def handler(_event: Event) -> None:
        seen.append("handler")

    await router.propagate_event(_make_message_event(content="hello"))
    assert seen == ["outer", "handler"]


@pytest.mark.asyncio
async def test_middleware_layer_registration_alias() -> None:
    router = Router()
    hits: list[str] = []

    @router.middleware(layer="outer", priority=10)
    async def outer(event: Event, next_handler):
        hits.append("outer")
        return await next_handler(event)

    @router.on_message()
    async def handler(_event: Event) -> None:
        hits.append("handler")

    await router.propagate_event(_make_message_event(content="x"))
    assert hits == ["outer", "handler"]


@pytest.mark.asyncio
async def test_stop_propagation_helper_drops_event() -> None:
    router = Router()
    hits: list[str] = []

    @router.outer_middleware()
    async def dropper(event: Event, next_handler):
        _ = next_handler
        Router.stop_propagation()

    @router.on_message()
    async def handler(_event: Event) -> None:
        hits.append("handler")

    result = await router.propagate_event(_make_message_event(content="x"))
    assert result is None
    assert hits == []


@pytest.mark.asyncio
async def test_class_based_middlewares_can_be_chained() -> None:
    from vaidcord.middleware import BaseMiddleware

    router = Router()
    trace: list[str] = []

    class OuterA(BaseMiddleware):
        async def __call__(self, handler, event, data):
            trace.append("A:before")
            data["a"] = True
            result = await handler(event, data)
            trace.append("A:after")
            return result

    class OuterB(BaseMiddleware):
        async def __call__(self, handler, event, data):
            trace.append("B:before")
            data["b"] = True
            result = await handler(event, data)
            trace.append("B:after")
            return result

    router.add_outer_middleware(OuterA(), priority=20)
    router.add_outer_middleware(OuterB(), priority=10)

    @router.on_message(lambda event: event.context.get("a") and event.context.get("b"))
    async def handler(_event: Event) -> None:
        trace.append("handler")

    await router.propagate_event(_make_message_event(content="ok"))
    assert trace == ["A:before", "B:before", "handler", "B:after", "A:after"]


@pytest.mark.asyncio
async def test_new_event_shortcut_decorators_register_and_dispatch() -> None:
    router = Router()
    hits: list[str] = []

    @router.on_hello()
    async def on_hello(_event: Event) -> None:
        hits.append("hello")

    @router.on_ready()
    async def on_ready(_event: Event) -> None:
        hits.append("ready")

    @router.on_resume()
    async def on_resume(_event: Event) -> None:
        hits.append("resume")

    @router.on_update_message()
    async def on_update(_event: Event) -> None:
        hits.append("update")

    @router.on_delete_message()
    async def on_delete(_event: Event) -> None:
        hits.append("delete")

    @router.on_delete_message_many()
    async def on_delete_many(_event: Event) -> None:
        hits.append("delete_many")

    @router.on_reaction()
    async def on_reaction(_event: Event) -> None:
        hits.append("reaction")

    @router.on_delete_reaction()
    async def on_delete_reaction(_event: Event) -> None:
        hits.append("reaction_delete")

    @router.on_delete_all_reaction()
    async def on_delete_all(_event: Event) -> None:
        hits.append("reaction_delete_all")

    @router.on_delete_emoji_for_reaction()
    async def on_delete_emoji(_event: Event) -> None:
        hits.append("reaction_delete_emoji")

    for event_type in [
        EventType.HELLO,
        EventType.READY,
        EventType.RESUMED,
        EventType.MESSAGE_UPDATE,
        EventType.MESSAGE_DELETE,
        EventType.MESSAGE_DELETE_BULK,
        EventType.REACTION_ADD,
        EventType.REACTION_REMOVE,
        EventType.MESSAGE_REACTION_REMOVE_ALL,
        EventType.MESSAGE_REACTION_REMOVE_EMOJI,
    ]:
        await router.propagate_event(Event(type=event_type, data={}))

    assert hits == [
        "hello",
        "ready",
        "resume",
        "update",
        "delete",
        "delete_many",
        "reaction",
        "reaction_delete",
        "reaction_delete_all",
        "reaction_delete_emoji",
    ]


@pytest.mark.asyncio
async def test_gateway_event_name_shortcut_and_reconnect_helpers() -> None:
    router = Router()
    hits: list[str] = []

    @router.on_gateway_event("RECONNECT")
    async def reconnect_by_name(_event: Event) -> None:
        hits.append("reconnect_name")

    @router.on_reconnect()
    async def reconnect_by_shortcut(_event: Event) -> None:
        hits.append("reconnect_shortcut")

    @router.on_invalid_session()
    async def invalid(_event: Event) -> None:
        hits.append("invalid")

    @router.on_rate_limited()
    async def rate(_event: Event) -> None:
        hits.append("rate")

    @router.on_message_poll_vote_add()
    async def poll_add(_event: Event) -> None:
        hits.append("poll_add")

    @router.on_message_poll_vote_remove()
    async def poll_remove(_event: Event) -> None:
        hits.append("poll_remove")

    for event_type in [
        EventType.RECONNECT,
        EventType.INVALID_SESSION,
        EventType.RATE_LIMITED,
        EventType.MESSAGE_POLL_VOTE_ADD,
        EventType.MESSAGE_POLL_VOTE_REMOVE,
    ]:
        await router.propagate_event(Event(type=event_type, data={}))

    assert hits == [
        "reconnect_name",
        "reconnect_shortcut",
        "invalid",
        "rate",
        "poll_add",
        "poll_remove",
    ]


def test_router_has_shortcuts_for_all_gateway_receive_event_types() -> None:
    special_names = {
        EventType.RECONNECT: "on_reconnect_event",
    }
    missing = []
    for event_type in EventType:
        method_name = special_names.get(event_type, f"on_{event_type.name.lower()}")
        if not hasattr(Router, method_name):
            missing.append(method_name)

    assert missing == []


def test_router_has_common_short_aliases() -> None:
    aliases = {
        "on_message": EventType.MESSAGE_CREATE,
        "on_reaction_add": EventType.MESSAGE_REACTION_ADD,
        "on_reaction_remove": EventType.MESSAGE_REACTION_REMOVE,
        "on_reaction_remove_all": EventType.MESSAGE_REACTION_REMOVE_ALL,
        "on_reaction_remove_emoji": EventType.MESSAGE_REACTION_REMOVE_EMOJI,
        "on_member_join": EventType.GUILD_MEMBER_ADD,
        "on_member_leave": EventType.GUILD_MEMBER_REMOVE,
        "on_member_update": EventType.GUILD_MEMBER_UPDATE,
        "on_guild_join": EventType.GUILD_CREATE,
        "on_guild_leave": EventType.GUILD_DELETE,
        "on_typing": EventType.TYPING_START,
        "on_interaction": EventType.INTERACTION_CREATE,
        "on_poll_vote_add": EventType.MESSAGE_POLL_VOTE_ADD,
        "on_poll_vote_remove": EventType.MESSAGE_POLL_VOTE_REMOVE,
    }

    for method_name, event_type in aliases.items():
        router = Router()

        async def handler(_event: Event) -> None:
            return None

        getattr(router, method_name)()(handler)

        assert router.get_handlers(event_type)


def test_router_has_shortcuts_for_all_webhook_event_types() -> None:
    missing = []
    for event_type in WebhookEventType:
        method_name = f"on_webhook_{event_type.name.lower()}"
        if not hasattr(Router, method_name):
            missing.append(method_name)

    assert missing == []


def test_webhook_event_shortcut_registers_separate_from_gateway_event() -> None:
    router = Router()

    async def handler(_event: Event) -> None:
        return None

    router.on_webhook_entitlement_create()(handler)

    assert router.get_handlers(WebhookEventType.ENTITLEMENT_CREATE)
    assert router.get_handlers(EventType.ENTITLEMENT_CREATE) == []
