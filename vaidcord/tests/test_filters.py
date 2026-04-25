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
