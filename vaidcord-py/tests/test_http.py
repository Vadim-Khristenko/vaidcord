from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp
import pytest

from vaidcord.errors import ForbiddenError, RateLimitError
from vaidcord.http import DiscordError, HTTPClient, HTTPConfig
from vaidcord.metadata import PROJECT_URL, __version__, build_user_agent


def test_discord_error_is_raisable() -> None:
    error = DiscordError(
        code=50035,
        message="Invalid Form Body",
        errors={
            "content": {
                "_errors": [
                    {"code": "REQUIRED", "message": "Content is required"}
                ]
            }
        },
    )

    assert isinstance(error, Exception)
    assert "Invalid Form Body" in str(error)

    with pytest.raises(DiscordError):
        raise error


def test_http_logs_include_attached_bot_id(caplog: pytest.LogCaptureFixture) -> None:
    client = HTTPClient(HTTPConfig(token="token"))
    client.set_bot_id(42)

    with caplog.at_level(logging.INFO, logger="vaidcord.http"):
        client._log_http_event("http.request.start", "req-1", route="/users/@me")

    assert caplog.records
    assert caplog.records[0].msg == {
        "event": "http.request.start",
        "request_id": "req-1",
        "route": "/users/@me",
        "bot_id": "42",
    }


def test_http_config_uses_library_metadata_headers() -> None:
    client = HTTPClient(HTTPConfig(token="token"))

    assert f"vaidcord/{__version__}" in client.headers["User-Agent"]
    assert "Python/" in client.headers["User-Agent"]
    assert client.headers["X-VaidCord-Version"] == __version__
    assert "Content-Type" not in client.headers


def test_metadata_user_agent_uses_canonical_repository_url() -> None:
    assert PROJECT_URL == "https://github.com/Vadim-Khristenko/vaidcord"
    assert PROJECT_URL in build_user_agent()
    assert f"vaidcord/{__version__}" in build_user_agent()


@pytest.mark.asyncio
async def test_http_request_keeps_aiohttp_json_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    client = HTTPClient(HTTPConfig(token="token"))

    async def fake_request_with_retry(
        method: str,
        endpoint: str,
        request_id: str,
        **kwargs: Any,
    ):
        captured.update(kwargs)
        from vaidcord.http import HTTPResponseData

        return HTTPResponseData(status=204, headers={}, body=b"")

    monkeypatch.setattr(client, "_request_with_retry", fake_request_with_retry)

    await client.request("POST", "/channels/1/messages", json={"content": "hello"})

    assert captured["json"] == {"content": "hello"}
    assert "data" not in captured


@pytest.mark.asyncio
async def test_http_request_locks_only_matching_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    from vaidcord.http import HTTPResponseData

    client = HTTPClient(HTTPConfig(token="token"))
    calls: list[str] = []

    async def slow_request(
        method: str,
        endpoint: str,
        request_id: str,
        **kwargs: Any,
    ) -> HTTPResponseData:
        calls.append(endpoint)
        await asyncio.sleep(0.05)
        return HTTPResponseData(status=204, headers={}, body=b"")

    monkeypatch.setattr(client, "_request_with_retry", slow_request)

    started = time.perf_counter()
    await asyncio.gather(
        client.request("GET", "/channels/1"),
        client.request("GET", "/channels/2"),
    )
    elapsed = time.perf_counter() - started

    assert calls == ["/channels/1", "/channels/2"]
    assert elapsed < 0.09


@pytest.mark.asyncio
async def test_http_request_maps_errors_to_vaidcord_hierarchy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vaidcord.http import HTTPResponseData

    client = HTTPClient(HTTPConfig(token="token"))

    async def forbidden(*args: Any, **kwargs: Any) -> HTTPResponseData:
        return HTTPResponseData(
            status=403,
            headers={},
            body=b'{"code":50013,"message":"Missing Permissions"}',
        )

    monkeypatch.setattr(client, "_request_with_retry", forbidden)
    with pytest.raises(ForbiddenError):
        await client.request("GET", "/forbidden")

    async def limited(*args: Any, **kwargs: Any) -> HTTPResponseData:
        return HTTPResponseData(
            status=429,
            headers={},
            body=b'{"message":"rate limited","retry_after":1.5,"global":true}',
        )

    monkeypatch.setattr(client, "_request_with_retry", limited)
    with pytest.raises(RateLimitError) as exc_info:
        await client.request("GET", "/limited")

    assert exc_info.value.retry_after == 1.5
    assert exc_info.value.global_limit is True


@pytest.mark.asyncio
async def test_upload_file_uses_multipart_without_json_content_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    client = HTTPClient(HTTPConfig(token="token"))

    async def fake_request(
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        captured.update({"method": method, "endpoint": endpoint, **kwargs})
        return {"ok": True}

    monkeypatch.setattr(client, "request", fake_request)

    result = await client.upload_file(
        "/channels/1/messages",
        b"hello",
        "hello.txt",
        payload_json={"content": "file"},
    )

    assert result == {"ok": True}
    assert captured["method"] == "POST"
    assert isinstance(captured["data"], aiohttp.FormData)
    assert "Content-Type" not in client.headers
