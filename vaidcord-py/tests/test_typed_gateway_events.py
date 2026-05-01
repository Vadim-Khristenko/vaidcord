from __future__ import annotations

from datetime import datetime

import pytest

from vaidcord.bot import Bot
from vaidcord.router import Router
from vaidcord.types import (
    Channel,
    ChannelType,
    DeletedMessage,
    Event,
    EventType,
    Guild,
    Message,
    PollVote,
    RawGatewayEvent,
    Reaction,
    Ready,
    Resume,
    TypingStart,
    User,
)


def _message_event() -> Event:
    author = User(id=10, username="tester")
    channel = Channel(id=20, type=ChannelType.TEXT)
    message = Message(
        id=30,
        channel=channel,
        author=author,
        content="hello",
        timestamp=datetime.now(),
    )
    return Event(
        type=EventType.MESSAGE_CREATE,
        data={},
        message=message,
        user=author,
        channel=channel,
    )


@pytest.mark.asyncio
async def test_handler_can_receive_message_by_annotation_with_any_name() -> None:
    router = Router()
    seen: list[str] = []

    @router.on_message()
    async def handler(payload: Message) -> None:
        seen.append(payload.content)

    await router.propagate_event(_message_event())

    assert seen == ["hello"]


@pytest.mark.asyncio
async def test_handler_can_mix_event_and_typed_payload() -> None:
    router = Router()
    seen: list[tuple[EventType, int]] = []

    @router.on_message()
    async def handler(event: Event, msg: Message) -> None:
        seen.append((event.type, msg.id))

    await router.propagate_event(_message_event())

    assert seen == [(EventType.MESSAGE_CREATE, 30)]


@pytest.mark.asyncio
async def test_ready_and_resumed_payloads_are_typed() -> None:
    bot = Bot(token="token")
    ready = await bot._parse_event(
        EventType.READY,
        {
            "v": 10,
            "user": {"id": "1", "username": "bot", "discriminator": "0"},
            "guilds": [{"id": "2", "name": "Guild", "unavailable": True}],
            "session_id": "session",
            "resume_gateway_url": "wss://gateway.discord.gg",
            "shard": [0, 1],
        },
    )
    resumed = await bot._parse_event(EventType.RESUMED, {})

    assert isinstance(ready.ready, Ready)
    assert ready.ready.user is not None
    assert ready.ready.user.id == 1
    assert ready.ready.guilds[0].id == 2
    assert isinstance(resumed.resume, Resume)


@pytest.mark.asyncio
async def test_gateway_resource_events_are_typed() -> None:
    bot = Bot(token="token")

    guild_event = await bot._parse_event(EventType.GUILD_CREATE, {"id": "10", "name": "Prod"})
    channel_event = await bot._parse_event(
        EventType.CHANNEL_CREATE,
        {"id": "20", "type": 16, "guild_id": "10", "name": "media"},
    )
    delete_event = await bot._parse_event(
        EventType.MESSAGE_DELETE,
        {"id": "30", "channel_id": "20", "guild_id": "10"},
    )
    reaction_event = await bot._parse_event(
        EventType.MESSAGE_REACTION_ADD,
        {
            "user_id": "1",
            "channel_id": "20",
            "message_id": "30",
            "guild_id": "10",
            "emoji": {"id": None, "name": "x"},
        },
    )
    typing_event = await bot._parse_event(
        EventType.TYPING_START,
        {"channel_id": "20", "user_id": "1", "timestamp": 123},
    )
    poll_event = await bot._parse_event(
        EventType.MESSAGE_POLL_VOTE_ADD,
        {"user_id": "1", "channel_id": "20", "message_id": "30", "answer_id": 2},
    )

    assert isinstance(guild_event.guild, Guild)
    assert isinstance(channel_event.channel, Channel)
    assert channel_event.channel.type is ChannelType.MEDIA
    assert isinstance(delete_event.deleted_message, DeletedMessage)
    assert isinstance(reaction_event.reaction, Reaction)
    assert isinstance(typing_event.typing, TypingStart)
    assert isinstance(poll_event.poll_vote, PollVote)


@pytest.mark.asyncio
async def test_unknown_typed_dispatch_falls_back_to_raw_gateway_event() -> None:
    bot = Bot(token="token")
    event = await bot._parse_event(EventType.PRESENCE_UPDATE, {"guild_id": "1"})
    assert isinstance(event.object, RawGatewayEvent)
