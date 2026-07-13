"""Tests for multipart file upload support in APIClient."""

from __future__ import annotations

import io
import json
from typing import Any

import aiohttp
import pytest

from vaidcord.api_client import APIClient
from vaidcord.types import AttachmentFile


def form_fields(form: aiohttp.FormData) -> list[tuple[dict[str, Any], Any]]:
    """Extract (type_options, value) pairs from an aiohttp FormData."""
    return [(dict(opts), value) for opts, _headers, value in form._fields]


def payload_json_of(form: aiohttp.FormData) -> dict[str, Any]:
    for opts, value in form_fields(form):
        if opts["name"] == "payload_json":
            return json.loads(value)
    raise AssertionError("payload_json part missing")


def test_attachment_file_spoiler_filename() -> None:
    plain = AttachmentFile(filename="cat.png", data=b"x")
    spoiler = AttachmentFile(filename="cat.png", data=b"x", spoiler=True)
    already = AttachmentFile(filename="SPOILER_cat.png", data=b"x", spoiler=True)

    assert plain.upload_filename == "cat.png"
    assert spoiler.upload_filename == "SPOILER_cat.png"
    assert already.upload_filename == "SPOILER_cat.png"


def test_attachment_file_read_bytes_from_bytes_and_io() -> None:
    from_bytes = AttachmentFile(filename="a.bin", data=b"abc")
    from_io = AttachmentFile(filename="b.bin", data=io.BytesIO(b"def"))

    assert from_bytes.read_bytes() == b"abc"
    assert from_io.read_bytes() == b"def"


def test_build_attachment_form_layout() -> None:
    files = [
        AttachmentFile(filename="cat.png", data=b"PNG", content_type="image/png"),
        AttachmentFile(filename="log.txt", data=b"LOG", description="the log", spoiler=True),
    ]
    form = APIClient._build_attachment_form({"content": "hello"}, files)

    body = payload_json_of(form)
    assert body["content"] == "hello"
    assert body["attachments"] == [
        {"id": 0, "filename": "cat.png"},
        {"id": 1, "filename": "SPOILER_log.txt", "description": "the log"},
    ]

    fields = form_fields(form)
    assert fields[0][0]["name"] == "payload_json"
    assert fields[1][0] == {"name": "files[0]", "filename": "cat.png"}
    assert fields[1][1] == b"PNG"
    assert fields[2][0] == {"name": "files[1]", "filename": "SPOILER_log.txt"}
    assert fields[2][1] == b"LOG"


def test_build_attachment_form_preserves_existing_attachments() -> None:
    payload = {"content": "edit", "attachments": [{"id": "123456"}]}
    form = APIClient._build_attachment_form(
        payload, [AttachmentFile(filename="new.png", data=b"n")]
    )

    body = payload_json_of(form)
    assert body["attachments"] == [{"id": "123456"}, {"id": 0, "filename": "new.png"}]
    # The original payload dict must not be mutated.
    assert payload["attachments"] == [{"id": "123456"}]


@pytest.fixture()
def client_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[APIClient, list[tuple[str, str, dict[str, Any]]]]:
    client = APIClient("token")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_request(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((method, endpoint, kwargs))
        return {"ok": True}

    monkeypatch.setattr(client, "request", fake_request)
    return client, calls


@pytest.mark.asyncio
async def test_send_message_with_files_uses_multipart(client_calls: Any) -> None:
    client, calls = client_calls
    files = [AttachmentFile(filename="cat.png", data=b"PNG", content_type="image/png")]

    await client.send_message(1, {"content": "look"}, files=files)

    method, endpoint, kwargs = calls[0]
    assert (method, endpoint) == ("POST", "/channels/1/messages")
    assert "json" not in kwargs
    assert isinstance(kwargs["data"], aiohttp.FormData)
    assert payload_json_of(kwargs["data"])["content"] == "look"


@pytest.mark.asyncio
async def test_send_message_without_files_keeps_json_path(client_calls: Any) -> None:
    client, calls = client_calls

    await client.send_message(1, {"content": "plain"})

    assert calls == [("POST", "/channels/1/messages", {"json": {"content": "plain"}})]


@pytest.mark.asyncio
async def test_files_kwarg_on_edit_webhook_and_interaction_helpers(client_calls: Any) -> None:
    client, calls = client_calls
    files = [AttachmentFile(filename="f.txt", data=b"F")]

    await client.edit_message(1, 2, {"content": "e"}, files=files)
    await client.execute_webhook(7, "tok", {"content": "w"}, files=files, wait=True)
    await client.edit_webhook_message(7, "tok", 2, {"content": "wm"}, files=files)
    await client.create_interaction_response(4, "itok", {"type": 4}, files=files)
    await client.create_followup_message(5, "itok", {"content": "f"}, files=files)
    await client.edit_original_interaction_response(5, "itok", {"content": "o"}, files=files)
    await client.edit_followup_message(5, "itok", 2, {"content": "fu"}, files=files)
    await client.start_thread_in_forum(1, {"name": "t", "message": {"content": "m"}}, files=files)

    expected_routes = [
        ("PATCH", "/channels/1/messages/2"),
        ("POST", "/webhooks/7/tok"),
        ("PATCH", "/webhooks/7/tok/messages/2"),
        ("POST", "/interactions/4/itok/callback"),
        ("POST", "/webhooks/5/itok"),
        ("PATCH", "/webhooks/5/itok/messages/@original"),
        ("PATCH", "/webhooks/5/itok/messages/2"),
        ("POST", "/channels/1/threads"),
    ]
    assert [(method, endpoint) for method, endpoint, _ in calls] == expected_routes
    for method, endpoint, kwargs in calls:
        assert "json" not in kwargs, (method, endpoint)
        assert isinstance(kwargs["data"], aiohttp.FormData), (method, endpoint)
    # execute_webhook keeps its query params alongside the form body.
    assert calls[1][2]["params"] == {"wait": True}


@pytest.mark.asyncio
async def test_create_guild_sticker_builds_multipart_form(client_calls: Any) -> None:
    client, calls = client_calls

    await client.create_guild_sticker(
        9,
        name="boing",
        description="a boing",
        tags="fun",
        file=AttachmentFile(filename="boing.png", data=b"PNG", content_type="image/png"),
        reason="new sticker",
    )

    method, endpoint, kwargs = calls[0]
    assert (method, endpoint) == ("POST", "/guilds/9/stickers")
    assert kwargs["headers"] == {"X-Audit-Log-Reason": "new sticker"}
    fields = form_fields(kwargs["data"])
    assert [(opts["name"], value) for opts, value in fields[:3]] == [
        ("name", "boing"),
        ("description", "a boing"),
        ("tags", "fun"),
    ]
    assert fields[3][0] == {"name": "file", "filename": "boing.png"}
    assert fields[3][1] == b"PNG"
