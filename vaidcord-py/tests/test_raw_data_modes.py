"""Tests for the raw_data sharing modes added for issue #26."""

from __future__ import annotations

import pytest

from vaidcord._internal.event_parser import _EMPTY_RAW
from vaidcord.bot import Bot, BotConfig
from vaidcord.types import EventType

SAMPLE_PAYLOAD = {
    "id": "1",
    "channel_id": "10",
    "guild_id": "100",
    "content": "hi",
    "author": {"id": "2", "username": "alice", "discriminator": "0"},
    "timestamp": "2026-05-10T12:00:00.000+00:00",
}


@pytest.mark.asyncio
async def test_share_raw_data_default_avoids_copy():
    bot = Bot(config=BotConfig(token="t"))  # defaults: keep=True, share=True
    payload = dict(SAMPLE_PAYLOAD)
    event = await bot._parse_event(EventType.MESSAGE_CREATE, payload)
    # raw_data must be the *same object* as the input payload, not a copy.
    assert event.raw_data is payload
    assert event.message is not None
    assert event.message.raw_data is payload


@pytest.mark.asyncio
async def test_legacy_copy_raw_data_mode_still_works():
    bot = Bot(config=BotConfig(token="t", share_raw_data=False))
    payload = dict(SAMPLE_PAYLOAD)
    event = await bot._parse_event(EventType.MESSAGE_CREATE, payload)
    assert event.raw_data == payload
    assert event.raw_data is not payload  # defensive copy
    assert event.message is not None
    assert event.message.raw_data is not payload


@pytest.mark.asyncio
async def test_keep_raw_data_false_drops_payload():
    bot = Bot(config=BotConfig(token="t", keep_raw_data=False))
    payload = dict(SAMPLE_PAYLOAD)
    event = await bot._parse_event(EventType.MESSAGE_CREATE, payload)
    # The shared empty mapping is used so we don't allocate a fresh dict per parse.
    assert event.raw_data is _EMPTY_RAW
    assert event.message is not None
    assert event.message.raw_data is _EMPTY_RAW


@pytest.mark.asyncio
async def test_share_raw_data_does_not_mutate_user_payload():
    # The hot path does not mutate the source dict; verify by parsing many
    # events from the same payload and confirming nothing changed.
    bot = Bot(config=BotConfig(token="t"))
    payload = dict(SAMPLE_PAYLOAD)
    snapshot = dict(payload)
    for _ in range(50):
        await bot._parse_event(EventType.MESSAGE_CREATE, payload)
    assert payload == snapshot
