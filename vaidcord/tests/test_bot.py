"""Tests for bot lifecycle and convenience API."""

import pytest

from vaidcord.bot import Bot, BotState


@pytest.mark.asyncio
async def test_ready_sets_user_and_state() -> None:
    """READY event should set bot.user and state."""
    bot = Bot(token="test-token")

    await bot._handle_ready(
        {
            "user": {"id": "42", "username": "vaidcord-bot", "discriminator": "0"},
            "guilds": [],
            "session_id": "abc",
        }
    )

    assert bot.user is not None
    assert bot.user.id == 42
    assert bot.state == BotState.READY
    assert bot.is_ready


@pytest.mark.asyncio
async def test_send_message_uses_async_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """send_message should call request with normalized payload."""
    bot = Bot(token="test-token")

    calls: list[tuple[str, str, dict]] = []

    async def fake_request(method: str, endpoint: str, **kwargs):
        calls.append((method, endpoint, kwargs))
        return {"id": "1", "content": kwargs["json"]["content"]}

    monkeypatch.setattr(bot, "request", fake_request)

    response = await bot.send_message(100, "Hello")

    assert response["content"] == "Hello"
    assert calls == [
        (
            "POST",
            "/channels/100/messages",
            {"json": {"content": "Hello", "tts": False}},
        )
    ]
