"""Tests for bot lifecycle and convenience API."""

from datetime import datetime

import pytest

from vaidcord.bot import Bot, BotState, GatewayIntent
from vaidcord.types import Channel, ChannelType, Message, User


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


@pytest.mark.asyncio
async def test_send_message_supports_discord_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_message should pass through advanced Discord message fields."""
    bot = Bot(token="test-token")
    calls: list[dict] = []

    async def fake_request(method: str, endpoint: str, **kwargs):
        calls.append({"method": method, "endpoint": endpoint, "kwargs": kwargs})
        return {"ok": True}

    monkeypatch.setattr(bot, "request", fake_request)

    await bot.send_message(
        channel_id=200,
        content="Hi",
        embeds=[{"title": "x"}],
        components=[{"type": 1, "components": []}],
        allowed_mentions={"parse": []},
        message_reference={"message_id": "10"},
        flags=4,
    )

    assert calls[0] == {
        "method": "POST",
        "endpoint": "/channels/200/messages",
        "kwargs": {
            "json": {
                "content": "Hi",
                "tts": False,
                "embeds": [{"title": "x"}],
                "components": [{"type": 1, "components": []}],
                "allowed_mentions": {"parse": []},
                "message_reference": {"message_id": "10"},
                "flags": 4,
            }
        },
    }


@pytest.mark.asyncio
async def test_send_poll_builds_discord_poll_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_poll should normalize payload into Discord poll object."""
    bot = Bot(token="test-token")
    calls: list[dict] = []

    async def fake_request(method: str, endpoint: str, **kwargs):
        calls.append(kwargs["json"])
        return {"id": "42"}

    monkeypatch.setattr(bot, "request", fake_request)

    await bot.send_poll(
        channel_id=777,
        question="Best language?",
        answers=["Python", "Rust"],
        duration_hours=24,
        allow_multiselect=True,
    )

    assert calls[0]["poll"]["question"] == {"text": "Best language?"}
    assert calls[0]["poll"]["answers"] == [
        {"poll_media": {"text": "Python"}},
        {"poll_media": {"text": "Rust"}},
    ]
    assert calls[0]["poll"]["duration"] == 24
    assert calls[0]["poll"]["allow_multiselect"] is True


@pytest.mark.asyncio
async def test_send_poll_validates_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """send_poll should validate question/answers/duration bounds."""
    bot = Bot(token="test-token")

    async def fake_request(method: str, endpoint: str, **kwargs):  # pragma: no cover
        return {"ok": True}

    monkeypatch.setattr(bot, "request", fake_request)

    with pytest.raises(ValueError):
        await bot.send_poll(channel_id=1, question="", answers=["a", "b"])
    with pytest.raises(ValueError):
        await bot.send_poll(channel_id=1, question="Q", answers=["a"])
    with pytest.raises(ValueError):
        await bot.send_poll(channel_id=1, question="Q", answers=["a", "b"], duration_hours=999)


@pytest.mark.asyncio
async def test_send_message_requires_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """send_message should fail if no content fields are provided."""
    bot = Bot(token="test-token")

    async def fake_request(method: str, endpoint: str, **kwargs):  # pragma: no cover
        return {"ok": True}

    monkeypatch.setattr(bot, "request", fake_request)

    with pytest.raises(ValueError):
        await bot.send_message(channel_id=1, content=None)


@pytest.mark.asyncio
async def test_reply_builds_message_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    """reply should map to send_message with message_reference payload."""
    bot = Bot(token="test-token")
    calls: list[dict] = []

    async def fake_request(method: str, endpoint: str, **kwargs):
        calls.append(kwargs["json"])
        return {"id": "x"}

    monkeypatch.setattr(bot, "request", fake_request)

    await bot.reply(channel_id=100, message_id=55, content="pong")
    assert calls[0]["message_reference"] == {"message_id": "55"}


@pytest.mark.asyncio
async def test_wait_until_ready_timeout() -> None:
    """wait_until_ready should return False on timeout."""
    bot = Bot(token="test-token")
    assert await bot.wait_until_ready(wait_timeout=0.01) is False


@pytest.mark.asyncio
async def test_connect_gateway_uses_gateway_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gateway connection bootstrap should call /gateway/bot."""
    bot = Bot(token="test-token")
    calls: list[tuple[str, str]] = []

    class FakeSession:
        async def ws_connect(self, *_args, **_kwargs):
            return object()

    async def fake_create_session():
        bot._session = FakeSession()  # type: ignore[assignment]
        return bot._session  # type: ignore[return-value]

    async def fake_request(method: str, endpoint: str, **_kwargs):
        calls.append((method, endpoint))
        return {"url": "wss://gateway.discord.gg"}

    monkeypatch.setattr(bot, "_create_session", fake_create_session)
    monkeypatch.setattr(bot, "request", fake_request)

    await bot._connect_gateway()
    assert calls == [("GET", "/gateway/bot")]


def test_gateway_intent_presets() -> None:
    """Intent presets should be consistent and non-empty."""
    assert GatewayIntent.default() > 0
    assert GatewayIntent.all() >= GatewayIntent.default()


@pytest.mark.asyncio
async def test_message_reply_calls_bot_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    """Message.reply should delegate to bot.reply with message id reference."""
    bot = Bot(token="test-token")
    calls: list[tuple[int, int, str]] = []

    async def fake_reply(channel_id: int, message_id: int, content: str, **kwargs):
        calls.append((channel_id, message_id, content))
        return {"ok": True, "kwargs": kwargs}

    monkeypatch.setattr(bot, "reply", fake_reply)

    msg = Message(
        id=55,
        channel=Channel(id=100, type=ChannelType.TEXT),
        author=User(id=1, username="u", discriminator="0"),
        content="hello",
        timestamp=datetime.now(),
        bot=bot,
    )

    response = await msg.reply("pong", tts=True)
    assert calls == [(100, 55, "pong")]
    assert response["ok"] is True


@pytest.mark.asyncio
async def test_message_answer_calls_send_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Message.answer should delegate to bot.send_message for same channel."""
    bot = Bot(token="test-token")
    calls: list[tuple[int, str]] = []

    async def fake_send(channel_id: int, content: str, **kwargs):
        calls.append((channel_id, content))
        return {"ok": True, "kwargs": kwargs}

    monkeypatch.setattr(bot, "send_message", fake_send)

    msg = Message(
        id=12,
        channel=Channel(id=777, type=ChannelType.TEXT),
        author=User(id=2, username="u2", discriminator="0"),
        content="hello",
        timestamp=datetime.now(),
        bot=bot,
    )

    response = await msg.answer("plain", embeds=[{"title": "x"}])
    assert calls == [(777, "plain")]
    assert response["ok"] is True
