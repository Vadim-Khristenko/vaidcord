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
    assert await expr(event) is True

    expr_not = ~F.message.content.contains("ban")
    assert await expr_not(event) is True


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
