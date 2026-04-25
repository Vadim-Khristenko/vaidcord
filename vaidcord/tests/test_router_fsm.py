"""Tests for router middleware chaining and FSM integration."""

from __future__ import annotations

from datetime import datetime
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from vaidcord.fsm import FSMMiddleware, MemoryFSMStorage, StorageKey
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
        data={"user_id": str(user.id), "channel_id": str(channel.id)},
        message=message,
        user=user,
        channel=channel,
    )


@pytest.mark.asyncio
async def test_middlewares_wrap_handler_in_registration_order() -> None:
    router = Router()
    calls: list[str] = []

    @router.middleware()
    async def mw_one(event: Event, handler: MiddlewareHandler):
        calls.append("mw1_before")
        result = await handler(event)
        calls.append("mw1_after")
        return result

    @router.middleware()
    async def mw_two(event: Event, handler: MiddlewareHandler):
        calls.append("mw2_before")
        result = await handler(event)
        calls.append("mw2_after")
        return result

    @router.on_message()
    async def handler(event: Event) -> str:
        calls.append("handler")
        return "ok"

    result = await router.propagate_event(_make_message_event())
    assert result == "ok"
    assert calls == [
        "mw1_before",
        "mw2_before",
        "handler",
        "mw2_after",
        "mw1_after",
    ]


@pytest.mark.asyncio
async def test_parent_middlewares_apply_to_child_handlers() -> None:
    parent = Router(name="parent")
    child = Router(name="child")
    parent.include_router(child)
    calls: list[str] = []

    @parent.middleware()
    async def parent_mw(event: Event, handler: MiddlewareHandler):
        calls.append("parent_before")
        result = await handler(event)
        calls.append("parent_after")
        return result

    @child.middleware()
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
async def test_fsm_middleware_and_state_filter() -> None:
    storage = MemoryFSMStorage()
    router = Router(name="fsm")
    router.add_middleware(FSMMiddleware(storage=storage))
    captured: list[str] = []

    @router.on_message_state("awaiting_name")
    async def by_state(event: Event) -> None:
        captured.append(event.message.content)

    event = _make_message_event("hello")
    await storage.set_state(StorageKey(user_id=100, chat_id=200), "awaiting_name")
    await router.propagate_event(event)
    await storage.set_state(StorageKey(user_id=100, chat_id=200), "done")
    await router.propagate_event(event)

    assert captured == ["hello"]
