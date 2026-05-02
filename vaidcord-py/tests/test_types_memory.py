from __future__ import annotations

from datetime import datetime

from vaidcord.types import Channel, ChannelType, Event, EventType, Message, User


def test_hot_gateway_models_are_slotted() -> None:
    user = User(id=1, username="tester")
    channel = Channel(id=2, type=ChannelType.TEXT)
    message = Message(
        id=3,
        channel=channel,
        author=user,
        content="hello",
        timestamp=datetime.now(),
    )

    assert not hasattr(user, "__dict__")
    assert not hasattr(channel, "__dict__")
    assert not hasattr(message, "__dict__")


def test_event_remains_mutable_runtime_container() -> None:
    event = Event(type=EventType.MESSAGE_CREATE, data={})
    event.context["value"] = "ok"
    event.event_id = "event-1"

    assert event.context == {"value": "ok"}
    assert event.event_id == "event-1"

