"""Tests for VaidCord mock utilities."""

import logging
import shutil
import subprocess
from datetime import datetime

import pytest

from vaidcord import (
    MockBot,
    create_mock_event,
    create_mock_message,
)
from vaidcord.formatting import Formatter
from vaidcord.mock import MockSettings
from vaidcord.mock.ui import MOCK_UI_HTML, validate_mock_ui
from vaidcord.types import ChannelType, EventType


@pytest.mark.asyncio
async def test_mock_bot_creation():
    """Test creating a mock bot instance."""
    bot = MockBot()
    assert bot.user is not None
    assert bot.user.username == "TestBot"
    assert bot.is_ready is False


@pytest.mark.asyncio
async def test_mock_bot_start_stop():
    """Test starting and stopping mock bot."""
    bot = MockBot()
    await bot.start()
    assert bot.is_ready is True
    await bot.stop()
    assert bot.is_ready is False


@pytest.mark.asyncio
async def test_mock_settings_auto_ready_toggle():
    """READY auto-enqueue can be disabled for deterministic tests."""
    from vaidcord.mock import MockEvent

    bot = MockBot(settings=MockSettings(auto_ready_event=False))
    bot.gateway.add_event(MockEvent(event_type=EventType.MESSAGE_CREATE, data={"content": "x"}))
    await bot.start()
    event = await bot.gateway.receive_event()
    assert event is not None
    assert event["t"] == "MESSAGE_CREATE"
    await bot.stop()


@pytest.mark.asyncio
async def test_mock_bot_simulate_message():
    """Test simulating a message event."""
    bot = MockBot()
    await bot.start()

    handler_called = False

    @bot.on_message()
    async def test_handler(event):
        nonlocal handler_called
        handler_called = True
        assert event.message is not None
        assert event.message.content == "Hello, World!"

    await bot.simulate_message("Hello, World!")
    assert handler_called is True

    await bot.stop()


@pytest.mark.asyncio
async def test_mock_http_client():
    """Test mock HTTP client functionality."""
    bot = MockBot()
    http = bot.http

    # Set up mock response
    from vaidcord.mock import MockHTTPResponse

    http.set_response(
        "GET",
        "/users/123",
        MockHTTPResponse(status=200, data={"id": "123", "username": "test"}),
    )

    # Make request
    result = await http.request("GET", "/users/123")
    assert result["username"] == "test"

    # Check request history
    history = http.get_request_history()
    assert len(history) == 1
    assert history[0]["method"] == "GET"
    assert history[0]["endpoint"] == "/users/123"


@pytest.mark.asyncio
async def test_mock_http_client_raises_vaidcord_errors():
    """Mock HTTP errors should match the real client hierarchy."""
    from vaidcord.errors import ForbiddenError, NotFoundError, RateLimitError
    from vaidcord.mock import MockHTTPClient, MockHTTPResponse

    http = MockHTTPClient()
    http.set_response(
        "GET",
        "/forbidden",
        MockHTTPResponse(status=403, error_message="forbidden"),
    )
    http.set_response(
        "GET",
        "/missing",
        MockHTTPResponse(status=404, error_message="missing"),
    )
    http.set_response(
        "GET",
        "/limited",
        MockHTTPResponse(
            status=429,
            error_message="limited",
            headers={"Retry-After": "1.5"},
        ),
    )

    with pytest.raises(ForbiddenError):
        await http.request("GET", "/forbidden")

    with pytest.raises(NotFoundError):
        await http.request("GET", "/missing")

    with pytest.raises(RateLimitError):
        await http.request("GET", "/limited")


def test_mock_bot_configure_runtime_settings():
    """MockBot.configure should allow easy runtime tuning."""
    bot = MockBot()
    bot.configure(default_rate_limit=99, network_delay=0.01)
    assert bot.settings.default_rate_limit == 99
    assert bot.settings.network_delay == 0.01


def test_mock_ui_validates_generated_html() -> None:
    validate_mock_ui()


def test_mock_ui_embedded_javascript_has_valid_syntax(tmp_path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available")
    script = MOCK_UI_HTML.split("<script>", 1)[1].split("</script>", 1)[0]
    script_path = tmp_path / "mock-ui.js"
    script_path.write_text(script, encoding="utf-8")

    subprocess.run(
        [node, "--check", str(script_path)],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.asyncio
async def test_mock_gateway_events():
    """Test mock gateway event queuing."""
    from vaidcord.mock import MockEvent

    bot = MockBot()
    gateway = bot.gateway

    # Add custom events
    gateway.add_event(
        MockEvent(
            event_type=EventType.MESSAGE_CREATE,
            data={"content": "Test message", "channel_id": "123"},
        )
    )

    await gateway.connect()
    event = await gateway.receive_event()

    assert event is not None
    assert event["t"] == "READY"  # First event is always READY

    event = await gateway.receive_event()
    assert event is not None
    assert event["t"] == "MESSAGE_CREATE"
    assert event["d"]["content"] == "Test message"

    await gateway.disconnect()


def test_create_mock_message():
    """Test create_mock_message helper function."""
    msg = create_mock_message(content="Test content")
    assert msg.content == "Test content"
    assert msg.author.username == "TestUser"
    assert msg.channel.type == ChannelType.TEXT


def test_create_mock_event():
    """Test create_mock_event helper function."""
    evt = create_mock_event(content="Test event")
    assert evt.type == EventType.MESSAGE_CREATE
    assert evt.message is not None
    assert evt.message.content == "Test event"


def test_formatter_basic():
    """Test basic formatting functions."""
    assert Formatter.bold("text") == "**text**"
    assert Formatter.italic("text") == "*text*"
    assert Formatter.underline("text") == "__text__"
    assert Formatter.strikethrough("text") == "~~text~~"
    assert Formatter.spoiler("text") == "||text||"


def test_formatter_mentions():
    """Test mention formatting."""
    assert Formatter.mention_user(123) == "<@123>"
    assert Formatter.mention_role(456) == "<@&456>"
    assert Formatter.mention_channel(789) == "<#789>"


def test_formatter_code():
    """Test code formatting."""
    assert Formatter.inline_code("code") == "`code`"
    assert "```python" in Formatter.code_block("print('hi')", "python")
    assert "print('hi')" in Formatter.code_block("print('hi')", "python")


def test_formatter_timestamp():
    """Test timestamp formatting."""
    from vaidcord.formatting import TimestampStyle

    result = Formatter.timestamp(timestamp=1618953630, style=TimestampStyle.SHORT_TIME)
    assert result == "<t:1618953630:t>"


def test_formatter_link():
    """Test link formatting."""
    result = Formatter.link("Google", "https://google.com")
    assert result == "[Google](https://google.com)"

    with pytest.raises(ValueError):
        Formatter.link("Invalid", "not-a-url")


def test_formatter_combine_styles():
    """Test combining multiple styles."""
    from vaidcord.formatting import TextStyle

    result = Formatter.combine_styles("text", TextStyle.BOLD, TextStyle.ITALIC)
    assert result == "***text***"

    result = Formatter.combine_styles("text", TextStyle.BOLD, TextStyle.UNDERLINE)
    assert result == "__**text**__"


@pytest.mark.asyncio
async def test_mock_discord_server_smoke():
    import aiohttp

    from vaidcord.mock import MockDiscordServer

    server = MockDiscordServer(port=0)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{server.base_url}/v10/gateway/bot") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert "url" in data

            async with session.post(
                f"{server.base_url}/v10/channels/123/messages",
                json={"content": "hello"},
            ) as resp:
                assert resp.status == 200
                payload = await resp.json()
                assert payload["content"] == "hello"
                message_id = payload["id"]

            async with session.get(f"{server.base_url}/v10/channels/123") as resp:
                assert resp.status == 200
                channel = await resp.json()
                assert channel["id"] == "123"

            async with session.get(
                f"{server.base_url}/v10/channels/123/messages/{message_id}"
            ) as resp:
                assert resp.status == 200
                payload = await resp.json()
                assert payload["id"] == message_id
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_mock_discord_server_logs_structured_requests(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import aiohttp

    from vaidcord.mock import MockDiscordServer

    server = MockDiscordServer(port=0)
    with caplog.at_level(logging.INFO, logger="vaidcord.mock.server"):
        await server.start()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{server.base_url}/v10/gateway/bot") as resp:
                    assert resp.status == 200
        finally:
            await server.stop()

    events = [record.msg["event"] for record in caplog.records if isinstance(record.msg, dict)]
    assert "mock.server.started" in events
    assert "mock.request.start" in events
    assert "mock.request.done" in events
    assert "mock.server.stopped" in events
    assert server.requests[0]["request_id"]


@pytest.mark.asyncio
async def test_mock_discord_server_send_dm_flow():
    from vaidcord.bot import Bot, BotConfig
    from vaidcord.mock import MockDiscordServer

    server = MockDiscordServer(port=0)
    await server.start()
    try:
        bot = Bot(
            config=BotConfig(
                token="test-token",
                base_url=server.base_url,
                api_version="10",
            )
        )
        message = await bot.send_dm(user_id=123, content="hello from test")
        assert message.content == "hello from test"
        assert server.requests[0]["path"] == "/api/v10/users/@me/channels"
        assert server.requests[1]["path"] == "/api/v10/channels/1123/messages"
        await bot.api_client.close()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_mock_discord_server_local_ui_and_state():
    import aiohttp

    from vaidcord.mock import MockDiscordServer

    server = MockDiscordServer(port=0, enable_ui=True)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(server.local_url) as resp:
                assert resp.status == 200
                assert "VaidCord Mock Server" in await resp.text()

            async with session.post(
                f"{server.local_url}api/mock/messages",
                json={
                    "channel_id": "456",
                    "channel_name": "testing",
                    "guild_id": "777",
                    "guild_name": "UI Guild",
                    "author_id": "9",
                    "author_username": "UI User",
                    "content": "from ui",
                },
            ) as resp:
                assert resp.status == 200
                message = await resp.json()
                assert message["content"] == "from ui"
                assert message["author"]["username"] == "UI User"

            async with session.post(f"{server.base_url}/v10/channels/456/typing") as resp:
                assert resp.status == 204

            async with session.get(f"{server.local_url}api/mock/state") as resp:
                assert resp.status == 200
                state = await resp.json()
                assert state["base_url"] == server.base_url
                assert state["messages"][0]["channel_id"] == "456"
                assert state["users"][-1]["username"] == "UI User"
                assert state["guilds"][-1]["id"] == "777"
                assert state["typing_events"][0]["channel_id"] == "456"
                assert state["messages"][0]["timestamp"].endswith("Z")
                datetime.fromisoformat(state["messages"][0]["timestamp"].replace("Z", "+00:00"))
                assert len(state["requests"]) >= 4
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_mock_discord_server_supports_message_edit_delete_and_fetch_list():
    import aiohttp

    from vaidcord.mock import MockDiscordServer

    server = MockDiscordServer(port=0)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{server.base_url}/v10/channels/123/messages",
                json={"content": "before edit"},
            ) as resp:
                assert resp.status == 200
                created = await resp.json()

            message_id = created["id"]
            async with session.patch(
                f"{server.base_url}/v10/channels/123/messages/{message_id}",
                json={"content": "after edit"},
            ) as resp:
                assert resp.status == 200
                edited = await resp.json()
                assert edited["content"] == "after edit"

            async with session.get(
                f"{server.base_url}/v10/channels/123/messages"
            ) as resp:
                assert resp.status == 200
                messages = await resp.json()
                assert messages[0]["id"] == message_id

            async with session.delete(
                f"{server.base_url}/v10/channels/123/messages/{message_id}"
            ) as resp:
                assert resp.status == 204

            async with session.get(
                f"{server.base_url}/v10/channels/123/messages/{message_id}"
            ) as resp:
                assert resp.status == 404
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_mock_discord_server_exposes_common_rest_entities():
    import aiohttp

    from vaidcord.mock import MockDiscordServer

    server = MockDiscordServer(port=0)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{server.base_url}/v10/users/@me") as resp:
                assert resp.status == 200
                current_user = await resp.json()
                assert current_user["username"] == "MockBot"

            async with session.get(f"{server.base_url}/v10/users/2") as resp:
                assert resp.status == 200
                user = await resp.json()
                assert user["username"] == "MockUser"

            async with session.get(f"{server.base_url}/v10/guilds/999") as resp:
                assert resp.status == 200
                guild = await resp.json()
                assert guild["name"] == "Mock Guild"

            async with session.post(
                f"{server.base_url}/v10/users/@me/channels",
                json={"recipient_id": "55"},
            ) as resp:
                assert resp.status == 200
                channel = await resp.json()
                assert channel["id"] == "1055"
                assert channel["type"] == 1
                assert channel["recipients"][0]["id"] == "55"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_mock_discord_server_supports_channel_lifecycle_and_guild_channel_listing():
    import aiohttp

    from vaidcord.mock import MockDiscordServer

    server = MockDiscordServer(port=0)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{server.base_url}/v10/users/@me/guilds") as resp:
                assert resp.status == 200
                guilds = await resp.json()
                assert guilds[0]["id"] == "999"

            async with session.get(f"{server.base_url}/v10/guilds/999/channels") as resp:
                assert resp.status == 200
                channels = await resp.json()
                assert channels[0]["id"] == "123"

            async with session.patch(
                f"{server.base_url}/v10/channels/123",
                json={"name": "ops-room", "topic": "updated topic"},
            ) as resp:
                assert resp.status == 200
                channel = await resp.json()
                assert channel["name"] == "ops-room"
                assert channel["topic"] == "updated topic"

            async with session.delete(f"{server.base_url}/v10/channels/123") as resp:
                assert resp.status == 200
                deleted = await resp.json()
                assert deleted["id"] == "123"

            async with session.get(f"{server.base_url}/v10/channels/123") as resp:
                assert resp.status == 404
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_api_client_and_bot_message_channel_helpers_work_against_mock_server():
    from vaidcord import Bot, BotConfig
    from vaidcord.api_client import APIClient
    from vaidcord.mock import MockDiscordServer

    server = MockDiscordServer(port=0)
    await server.start()
    try:
        api = APIClient(token="test-token", base_url=server.base_url, api_version="10")
        bot = Bot(
            config=BotConfig(
                token="test-token",
                base_url=server.base_url,
                api_version="10",
            )
        )

        channel = await bot.modify_channel(123, name="support", topic="triage")
        assert channel.name == "support"
        assert channel.topic == "triage"

        guild_channels = await bot.list_guild_channels(999)
        assert guild_channels[0].id == 123

        await api.send_message(123, {"content": "first"})
        await api.send_message(123, {"content": "second"})

        listed = await bot.list_messages(123, limit=1)
        assert len(listed) == 1
        assert listed[0].content == "second"

        fetched = await bot.fetch_message(123, listed[0].id)
        assert fetched.content == "second"

        edited = await bot.edit_message(123, fetched.id, content="edited second")
        assert edited.content == "edited second"
        assert edited.edited_timestamp is not None

        raw_messages = await api.list_messages(123, after=10001)
        assert raw_messages[0]["content"] == "edited second"
        assert raw_messages[0]["edited_timestamp"].endswith("Z")

        deleted = await bot.delete_message(123, fetched.id)
        assert deleted == {}

        await api.close()
        await bot.api_client.close()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_mock_discord_server_ui_can_be_disabled():
    import aiohttp

    from vaidcord.mock import MockDiscordServer

    server = MockDiscordServer(port=0, enable_ui=False)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(server.local_url) as resp:
                assert resp.status == 404
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_mock_discord_server_profiles_can_be_created_updated_and_selected():
    import aiohttp

    from vaidcord.mock import MockDiscordServer

    server = MockDiscordServer(port=0)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{server.local_url}api/mock/profiles",
                json={
                    "id": "77",
                    "username": "SupportBot",
                    "global_name": "Support",
                    "discriminator": "4242",
                    "bot": True,
                },
            ) as resp:
                assert resp.status == 200
                created = await resp.json()
                assert created["id"] == "77"
                assert created["bot"] is True

            async with session.patch(
                f"{server.local_url}api/mock/profiles/77",
                json={"username": "SupportAgent", "bot": False},
            ) as resp:
                assert resp.status == 200
                updated = await resp.json()
                assert updated["username"] == "SupportAgent"
                assert updated["bot"] is False

            async with session.patch(
                f"{server.local_url}api/mock/current-user",
                json={"user_id": "77"},
            ) as resp:
                assert resp.status == 200
                current = await resp.json()
                assert current["id"] == "77"

            async with session.post(
                f"{server.base_url}/v10/channels/123/messages",
                json={"content": "sent as selected profile"},
            ) as resp:
                assert resp.status == 200
                message = await resp.json()
                assert message["author"]["id"] == "77"
                assert message["author"]["username"] == "SupportAgent"
    finally:
        await server.stop()
