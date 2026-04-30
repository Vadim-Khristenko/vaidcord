"""Tests for powerful filter system and router shortcuts."""

from __future__ import annotations

from datetime import datetime

import pytest

from vaidcord.filters import (
    F,
    CommandFilter,
    CommandHelpFilter,
    CommandSettingsFilter,
    CommandStartFilter,
    CustomFilter,
    RegexFilter,
    UserFilter,
    as_filter,
    run_filter_with_data,
)
from vaidcord.router import Router
from vaidcord.types import Channel, ChannelType, Event, EventType, Message, User


def _event_with_text(text: str, user_id: int = 10, username: str = "tester") -> Event:
    user = User(id=user_id, username=username, bot=False)
    channel = Channel(id=77, type=ChannelType.TEXT)
    message = Message(
        id=100,
        channel=channel,
        author=user,
        content=text,
        timestamp=datetime.now(),
    )
    return Event(
        type=EventType.MESSAGE_CREATE,
        data={},
        message=message,
        user=user,
        channel=channel,
    )


def _event_with_channel_type(text: str, channel_type: ChannelType, guild_id: str | None) -> Event:
    event = _event_with_text(text)
    event.channel = Channel(id=event.channel.id, type=channel_type)
    event.message = Message(
        id=event.message.id,
        channel=event.channel,
        author=event.message.author,
        content=event.message.content,
        timestamp=event.message.timestamp,
    )
    event.data = {"guild_id": guild_id} if guild_id is not None else {}
    return event


@pytest.mark.asyncio
async def test_magic_filters_composition() -> None:
    event = _event_with_text("!admin ping")
    expr = F.message.content.startswith("!admin") & F.user.id.in_({10, 11})
    assert bool(await expr(event)) is True

    expr_not = ~F.message.content.contains("ban")
    assert await expr_not(event) is True
    assert await (F.user.id == 10)(event) is True
    assert await (F.user.id != 11)(event) is True
    assert await (F.user.id > 5)(event) is True
    assert await (F.user.id @ {9, 10, 11})(event) is True
    assert bool(await F.message.content.regexp(r"^!admin")(event)) is True
    assert await (F.message.content.lower() == "!admin ping")(event) is True
    assert await (F.message.content.len() == 11)(event) is True


@pytest.mark.asyncio
async def test_command_filters() -> None:
    assert await CommandFilter(("start",))(_event_with_text("/start")) is True
    assert await CommandStartFilter()(_event_with_text("/start payload")) is True
    assert await CommandHelpFilter()(_event_with_text("!help")) is True
    assert await CommandSettingsFilter()(_event_with_text(".settings")) is True
    assert await CommandSettingsFilter()(_event_with_text("/other")) is False


@pytest.mark.asyncio
async def test_regex_user_custom_filters() -> None:
    link_event = _event_with_text("https://example.com")
    assert await RegexFilter(r"^https?://")(link_event) is True
    assert await UserFilter(user_ids={10}, usernames={"tester"})(link_event) is True
    assert await UserFilter(user_ids={999})(link_event) is False

    custom = CustomFilter(lambda event: "example" in event.message.content)
    assert await custom(link_event) is True


@pytest.mark.asyncio
async def test_router_command_shortcuts_and_middleware_filter_check() -> None:
    router = Router()
    hits: list[str] = []

    @router.middleware()
    async def mw(event: Event, handler):
        if await Router.check_filter(event, F.message.content.contains("start")):
            event.context["has_start"] = True
        return await handler(event)

    @router.on_command_start()
    async def start_handler(event: Event) -> None:
        if event.context.get("has_start"):
            hits.append("start")

    @router.on_command("ping")
    async def ping_handler(event: Event) -> None:
        hits.append("ping")

    await router.propagate_event(_event_with_text("/start"))
    await router.propagate_event(_event_with_text("!ping"))
    assert hits == ["start", "ping"]


@pytest.mark.asyncio
async def test_as_filter_accepts_plain_callables() -> None:
    event = _event_with_text("abc")
    assert await as_filter(lambda e: e.message.content == "abc")(event) is True


@pytest.mark.asyncio
async def test_filter_dict_data_propagation_to_event_context() -> None:
    router = Router()
    captured: dict = {}

    async def inject_filter(_event: Event):
        return {"role": "admin", "tenant": "main"}

    @router.on_message(inject_filter)
    async def handler(event: Event) -> None:
        captured.update(event.context.get("filter_data", {}))

    await router.propagate_event(_event_with_text("hello"))
    assert captured == {"role": "admin", "tenant": "main"}


@pytest.mark.asyncio
async def test_filter_expr_and_merges_dict_with_bool() -> None:
    event = _event_with_text("hello")
    left = as_filter(lambda _e: {"role": "admin"})
    right = as_filter(lambda _e: True)

    passed, data = await run_filter_with_data(left & right, event)
    assert passed is True
    assert data == {"role": "admin"}


@pytest.mark.asyncio
async def test_filter_expr_and_merges_dict_with_dict() -> None:
    event = _event_with_text("hello")
    left = as_filter(lambda _e: {"role": "admin"})
    right = as_filter(lambda _e: {"tenant": "main"})

    passed, data = await run_filter_with_data(left & right, event)
    assert passed is True
    assert data == {"role": "admin", "tenant": "main"}


@pytest.mark.asyncio
async def test_filter_expr_or_uses_first_successful_branch_data() -> None:
    event = _event_with_text("hello")
    first = as_filter(lambda _e: {"source": "first"})
    second = as_filter(lambda _e: {"source": "second"})

    passed, data = await run_filter_with_data(first | second, event)
    assert passed is True
    assert data == {"source": "first"}


@pytest.mark.asyncio
async def test_filter_expr_or_uses_second_branch_data_when_first_fails() -> None:
    event = _event_with_text("hello")
    first = as_filter(lambda _e: False)
    second = as_filter(lambda _e: {"source": "second"})

    passed, data = await run_filter_with_data(first | second, event)
    assert passed is True
    assert data == {"source": "second"}


@pytest.mark.asyncio
async def test_router_global_filter_applies_to_all_handlers() -> None:
    router = Router()
    hits: list[str] = []
    router.add_filter(F.message.content.contains("ok"))

    @router.on_message()
    async def first(event: Event) -> None:
        hits.append("first")

    @router.on_command("ping")
    async def second(event: Event) -> None:
        hits.append("second")

    await router.propagate_event(_event_with_text("!ping"))
    assert hits == []

    await router.propagate_event(_event_with_text("ok !ping"))
    assert hits == ["first"]

    await router.propagate_event(_event_with_text("!ping ok"))
    assert hits == ["first", "first", "second"]


@pytest.mark.asyncio
async def test_specialized_message_handlers() -> None:
    router = Router()
    hits: list[str] = []

    @router.on_topic_message()
    async def topic(event: Event) -> None:
        hits.append("topic")

    @router.on_private_message()
    async def private(event: Event) -> None:
        hits.append("private")

    @router.on_guild_message()
    async def guild(event: Event) -> None:
        hits.append("guild")

    await router.propagate_event(
        _event_with_channel_type("t", ChannelType.PUBLIC_THREAD, guild_id="500")
    )
    await router.propagate_event(_event_with_channel_type("d", ChannelType.DM, guild_id=None))

    assert hits == ["topic", "guild", "private"]
