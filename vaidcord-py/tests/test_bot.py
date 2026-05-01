"""Tests for bot lifecycle and convenience API."""

from datetime import datetime
from typing import Any, cast

import pytest

from vaidcord.bot import Bot, BotState, GatewayIntent
from vaidcord.errors import DiscordAPIError, ForbiddenError
from vaidcord.gateway_runtime import GatewayRuntime
from vaidcord.logging import get_default_bot_id, set_default_bot_id
from vaidcord.metadata import __version__
from vaidcord.types import Channel, ChannelType, Message, User


@pytest.mark.asyncio
async def test_ready_sets_user_and_state() -> None:
    """READY event should set bot.user and state."""
    bot = Bot(token="test-token")

    try:
        set_default_bot_id(None)
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
        assert get_default_bot_id() == "42"
    finally:
        set_default_bot_id(None)


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


def test_parse_channel_accepts_guild_media_type() -> None:
    bot = Bot(token="test-token")

    channel = bot._parse_channel(
        {
            "id": "123",
            "guild_id": "456",
            "type": 16,
            "name": "media",
            "available_tags": [{"id": "1", "name": "clips"}],
        }
    )

    assert channel.type is ChannelType.GUILD_MEDIA
    assert ChannelType.MEDIA is ChannelType.GUILD_MEDIA
    assert channel.available_tags == [{"id": "1", "name": "clips"}]


@pytest.mark.asyncio
async def test_get_current_user_remembers_bot_id(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = Bot(token="test-token")

    async def fake_get_current_user() -> dict[str, str]:
        return {"id": "99", "username": "rest-bot", "discriminator": "0"}

    try:
        set_default_bot_id(None)
        monkeypatch.setattr(bot.api_client, "get_current_user", fake_get_current_user)

        user = await bot.get_current_user()

        assert user.id == 99
        assert bot.id == 99
        assert get_default_bot_id() == "99"
    finally:
        set_default_bot_id(None)


@pytest.mark.asyncio
async def test_bot_direct_session_uses_library_metadata_headers() -> None:
    bot = Bot(token="test-token")

    session = await bot._create_session()
    try:
        assert f"vaidcord/{__version__}" in session.headers["User-Agent"]
        assert session.headers["X-VaidCord-Version"] == __version__
    finally:
        await bot._close_session()


@pytest.mark.asyncio
async def test_bot_api_client_reuses_gateway_session() -> None:
    bot = Bot(token="test-token")

    api_session = await bot.api_client._http._create_session()
    gateway_session = await bot._create_session()

    assert api_session is gateway_session

    await bot.api_client.close()
    assert bot._session is None


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
async def test_reply_can_disable_author_mention(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = Bot(token="test-token")
    calls: list[dict] = []

    async def fake_request(method: str, endpoint: str, **kwargs):
        calls.append(kwargs["json"])
        return {"id": "x"}

    monkeypatch.setattr(bot, "request", fake_request)

    await bot.reply(
        channel_id=100,
        message_id=55,
        content="pong",
        mention_author=False,
    )

    assert calls[0]["allowed_mentions"] == {"replied_user": False}


@pytest.mark.asyncio
async def test_wait_until_ready_timeout() -> None:
    """wait_until_ready should return False on timeout."""
    bot = Bot(token="test-token")
    assert await bot.wait_until_ready(wait_timeout=0.01) is False


@pytest.mark.asyncio
async def test_drop_pending_updates_skips_until_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = Bot(token="test-token")
    bot.enable_drop_pending_updates()
    seen: list[str] = []

    async def fake_propagate(_event):
        seen.append("handled")

    monkeypatch.setattr(bot, "propagate_event", fake_propagate)

    await bot._handle_dispatch(
        {
            "t": "MESSAGE_CREATE",
            "s": 1,
            "d": {
                "id": "100",
                "channel_id": "200",
                "timestamp": datetime.now().isoformat(),
                "author": {"id": "42", "username": "tester", "discriminator": "0"},
                "content": "hello",
            },
        }
    )

    assert seen == []

    await bot._handle_dispatch(
        {
            "t": "READY",
            "s": 2,
            "d": {
                "user": {"id": "42", "username": "vaidcord-bot", "discriminator": "0"},
                "guilds": [],
                "session_id": "abc",
            },
        }
    )
    assert bot._drop_pending_updates is False


@pytest.mark.asyncio
async def test_ignore_self_messages_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = Bot(token="test-token")
    await bot._handle_ready(
        {
            "user": {"id": "42", "username": "vaidcord-bot", "discriminator": "0"},
            "guilds": [],
            "session_id": "abc",
        }
    )

    seen: list[str] = []

    async def fake_propagate(_event):
        seen.append("handled")

    monkeypatch.setattr(bot, "propagate_event", fake_propagate)

    await bot._handle_dispatch(
        {
            "t": "MESSAGE_CREATE",
            "s": 1,
            "d": {
                "id": "100",
                "channel_id": "200",
                "timestamp": datetime.now().isoformat(),
                "author": {"id": "42", "username": "tester", "discriminator": "0"},
                "content": "hello",
            },
        }
    )

    assert seen == []


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
    monkeypatch.setattr(bot.api_client, "request", fake_request)

    await bot._connect_gateway()
    assert calls == [("GET", "/gateway/bot")]


def test_gateway_intent_presets() -> None:
    """Intent presets should be consistent and non-empty."""
    assert GatewayIntent.default() > 0
    assert GatewayIntent.all() >= GatewayIntent.default()


def test_gateway_close_logs_privileged_intent_hint(caplog: pytest.LogCaptureFixture) -> None:
    bot = Bot(token="test-token")
    runtime = GatewayRuntime(bot)
    runtime._ws = cast(Any, type("FakeWebSocket", (), {"close_code": 4014})())

    with caplog.at_level("WARNING", logger="vaidcord.gateway_runtime"):
        runtime._log_close_code()

    assert "privileged intent" in caplog.text


@pytest.mark.asyncio
async def test_gateway_runtime_sends_immediate_heartbeat_request() -> None:
    bot = Bot(token="test-token")
    runtime = GatewayRuntime(bot)
    sent: list[dict[str, Any]] = []

    class FakeWebSocket:
        closed = False

        async def send_json(self, payload: dict[str, Any]) -> None:
            sent.append(payload)

    runtime._ws = cast(Any, FakeWebSocket())
    bot._sequence = 55

    await runtime._send_heartbeat()

    assert sent == [{"op": 1, "d": 55}]
    assert runtime._heartbeat_ack_received is False


@pytest.mark.asyncio
async def test_gateway_runtime_resume_payload_uses_cached_session() -> None:
    bot = Bot(token="test-token")
    runtime = GatewayRuntime(bot)
    sent: list[dict[str, Any]] = []

    class FakeWebSocket:
        closed = False

        async def send_json(self, payload: dict[str, Any]) -> None:
            sent.append(payload)

    runtime._ws = cast(Any, FakeWebSocket())
    bot._session_id = "session"
    bot._sequence = 99

    await runtime.resume()

    assert sent == [
        {
            "op": 6,
            "d": {"token": "test-token", "session_id": "session", "seq": 99},
        }
    ]


@pytest.mark.asyncio
async def test_gateway_runtime_reconnects_when_heartbeat_ack_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = Bot(token="test-token")
    runtime = GatewayRuntime(bot)
    calls: list[bool] = []

    async def fake_reconnect(*, resume: bool) -> None:
        calls.append(resume)

    monkeypatch.setattr(runtime, "reconnect", fake_reconnect)
    runtime._heartbeat_ack_received = False
    runtime._heartbeat_interval = 0
    bot._running = True

    await runtime._heartbeat()

    assert calls == [True]


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


@pytest.mark.asyncio
async def test_send_dm_success_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """send_dm should open DM channel first and then send message."""
    bot = Bot(token="test-token")
    calls: list[tuple[str, str, dict]] = []

    async def fake_request(method: str, endpoint: str, **kwargs):
        calls.append((method, endpoint, kwargs))
        return {"id": "999", "type": 1}

    async def fake_send_message(channel_id: int, content: str | None = None, **kwargs):
        assert channel_id == 999
        assert content == "hello dm"
        assert kwargs["embeds"] == [{"title": "DM"}]
        return {
            "id": "12345",
            "channel_id": str(channel_id),
            "content": content,
            "timestamp": "2026-04-30T00:00:00Z",
            "author": {"id": "42", "username": "bot", "discriminator": "0", "bot": True},
        }

    monkeypatch.setattr(bot, "request", fake_request)
    monkeypatch.setattr(bot, "send_message", fake_send_message)

    message = await bot.send_dm(user_id=777, content="hello dm", embeds=[{"title": "DM"}])
    assert message.channel.id == 999
    assert message.content == "hello dm"
    assert calls == [
        ("POST", "/users/@me/channels", {"json": {"recipient_id": "777"}}),
    ]


@pytest.mark.asyncio
async def test_send_dm_open_channel_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """send_dm should map 403 opening DM channel to ForbiddenError."""
    bot = Bot(token="test-token")

    async def fake_request(method: str, endpoint: str, **kwargs):
        raise DiscordAPIError("Forbidden", status=403, code=50007)

    monkeypatch.setattr(bot, "request", fake_request)

    with pytest.raises(ForbiddenError):
        await bot.send_dm(user_id=111, content="hi")


@pytest.mark.asyncio
async def test_send_message_to_user_alias_forwards_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_message_to_user should proxy to send_dm and preserve kwargs."""
    bot = Bot(token="test-token")
    calls: list[tuple[int, str, dict]] = []

    async def fake_send_dm(user_id: int, content: str, **kwargs):
        calls.append((user_id, content, kwargs))
        return Message(
            id=1,
            channel=Channel(id=2, type=ChannelType.DM),
            author=User(id=3, username="bot", discriminator="0", bot=True),
            content=content,
            timestamp=datetime.now(),
            bot=bot,
        )

    monkeypatch.setattr(bot, "send_dm", fake_send_dm)

    await bot.send_message_to_user(
        user_id=1234,
        content="payload",
        embeds=[{"title": "E"}],
        components=[{"type": 1, "components": []}],
    )
    assert calls == [
        (
            1234,
            "payload",
            {"embeds": [{"title": "E"}], "components": [{"type": 1, "components": []}]},
        )
    ]
