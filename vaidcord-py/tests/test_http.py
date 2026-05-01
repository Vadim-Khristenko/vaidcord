from __future__ import annotations

import logging

import pytest

from vaidcord.http import DiscordError, HTTPClient, HTTPConfig
from vaidcord.metadata import __version__


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
