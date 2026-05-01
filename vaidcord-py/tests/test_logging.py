from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from vaidcord.logging import (
    VaidcordContextFilter,
    VaidcordFormatter,
    set_default_bot_id,
)


@pytest.fixture(autouse=True)
def reset_default_bot_id() -> Iterator[None]:
    set_default_bot_id(None)
    yield
    set_default_bot_id(None)


def test_logging_formatter_includes_context_fields() -> None:
    record = logging.LogRecord(
        name="vaidcord.router",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    VaidcordContextFilter().filter(record)
    formatter = VaidcordFormatter(use_color=False, prefix="VAIDCORD")
    text = formatter.format(record)

    assert "VAIDCORD | [INFO] | [ROUTING]" in text
    assert "Bot id=\"-\"" in text
    assert "Event id=\"-\"" in text
    assert "Request id=\"-\"" in text
    assert text.endswith("hello")


def test_logging_formatter_promotes_request_id_from_structured_message() -> None:
    record = logging.LogRecord(
        name="vaidcord.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg={"event": "http.request.done", "request_id": "req-1", "status": 200},
        args=(),
        exc_info=None,
    )

    VaidcordContextFilter().filter(record)
    formatter = VaidcordFormatter(use_color=False, prefix="VAIDCORD")
    text = formatter.format(record)

    assert "[API]" in text
    assert "Request id=\"req-1\"" in text
    assert "http.request.done status=200" in text


def test_logging_formatter_uses_default_bot_id_for_contextless_logs() -> None:
    try:
        set_default_bot_id("42")
        record = logging.LogRecord(
            name="vaidcord.http",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg={"event": "http.request.done", "request_id": "req-2", "status": 200},
            args=(),
            exc_info=None,
        )

        VaidcordContextFilter().filter(record)
        formatter = VaidcordFormatter(use_color=False, prefix="VAIDCORD")
        text = formatter.format(record)

        assert "Bot id=\"42\"" in text
        assert "Request id=\"req-2\"" in text
    finally:
        set_default_bot_id(None)


def test_logging_formatter_uses_accent_background_badges() -> None:
    record = logging.LogRecord(
        name="vaidcord.gateway",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="connected",
        args=(),
        exc_info=None,
    )

    VaidcordContextFilter().filter(record)
    formatter = VaidcordFormatter(use_color=True, prefix="VAIDCORD")
    text = formatter.format(record)

    assert "\x1b[48;5;" in text
    assert "\x1b[1m INFO " in text
    assert "\x1b[1m GATEWAY " in text
    assert text.endswith("connected")
