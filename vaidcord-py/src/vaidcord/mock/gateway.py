from __future__ import annotations

import asyncio

from vaidcord.types import EventType

from .config import MockSettings
from .types import MockEvent


class MockGateway:
    def __init__(self, settings: MockSettings | None = None) -> None:
        self.settings = settings or MockSettings()
        self._events: list[MockEvent] = []
        self._event_index = 0
        self._connected = False
        self._sequence = 0
        self._session_id = "mock_session_123"

    def add_event(self, event: MockEvent) -> None:
        self._events.append(event)

    def add_events(self, events: list[MockEvent]) -> None:
        self._events.extend(events)

    def clear_events(self) -> None:
        self._events.clear()
        self._event_index = 0

    async def receive_event(self) -> dict | None:
        if not self._connected or self._event_index >= len(self._events):
            return None

        mock_event = self._events[self._event_index]
        self._event_index += 1

        if mock_event.delay > 0:
            await asyncio.sleep(mock_event.delay)

        self._sequence += 1
        return {
            "op": 0,
            "t": mock_event.event_type.value,
            "s": self._sequence,
            "d": mock_event.data,
        }

    async def connect(self) -> None:
        self._connected = True
        self._sequence = 0
        if self.settings.auto_ready_event:
            self._events.insert(
                0,
                MockEvent(
                    event_type=EventType.READY,
                    data={
                        "user": {
                            "id": "999999999999999999",
                            "username": "TestBot",
                            "discriminator": "0000",
                            "bot": True,
                        },
                        "session_id": self._session_id,
                        "guilds": [],
                    },
                ),
            )

    async def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected
