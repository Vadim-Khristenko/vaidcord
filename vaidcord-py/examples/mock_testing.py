"""Deterministic mock-layer example for fast bot tests."""

from __future__ import annotations

import asyncio

from vaidcord import F, MockBot, create_mock_event
from vaidcord.mock import MockHTTPResponse, MockSettings


async def main() -> None:
    bot = MockBot(settings=MockSettings(auto_ready_event=False))
    seen_messages: list[str] = []

    @bot.on_message(F.message.content.startswith("/ping"))
    async def ping(event) -> None:
        seen_messages.append(event.message.content)

    bot.http.set_response(
        "GET",
        "/users/123",
        MockHTTPResponse(status=200, data={"id": "123", "username": "tester"}),
    )

    await bot.simulate_message("/ping hello")
    await bot.emit_event(create_mock_event(content="plain text"))

    user = await bot.http.request("GET", "/users/123")
    history = bot.http.get_request_history()

    print("seen_messages:", seen_messages)
    print("mock user:", user)
    print("history:", [item["endpoint"] for item in history])


if __name__ == "__main__":
    asyncio.run(main())
