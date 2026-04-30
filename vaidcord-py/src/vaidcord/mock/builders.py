from __future__ import annotations

from datetime import datetime
from typing import Any

from vaidcord.types import Channel, ChannelType, Event, EventType, Guild, Message, User


def create_mock_message(
    content: str = "Test message",
    author_id: int = 123456789012345678,
    channel_id: int = 111111111111111111,
    guild_id: int | None = None,
) -> Message:
    author = User(id=author_id, username="TestUser", discriminator="0000")
    channel = Channel(id=channel_id, type=ChannelType.TEXT, name="test")
    guild = Guild(id=guild_id, name="Test Guild") if guild_id else None

    return Message(
        id=555555555555555555,
        channel=channel,
        author=author,
        content=content,
        timestamp=datetime.now(),
        guild=guild,
    )


def create_mock_event(
    event_type: EventType = EventType.MESSAGE_CREATE,
    content: str = "Test",
) -> Event:
    message = create_mock_message(content=content)
    return Event(
        type=event_type,
        data={"content": content},
        message=message,
        user=message.author,
        channel=message.channel,
        guild=message.guild,
    )


class MockResponseBuilder:
    @staticmethod
    def user(
        user_id: int = 123456789012345678,
        username: str = "TestUser",
        is_bot: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": str(user_id),
            "username": username,
            "discriminator": "0000",
            "public_flags": 0,
            "bot": is_bot,
        }

    @staticmethod
    def guild(
        guild_id: int = 333333333333333333,
        name: str = "Test Guild",
        member_count: int = 100,
    ) -> dict[str, Any]:
        return {
            "id": str(guild_id),
            "name": name,
            "icon": None,
            "owner_id": str(123456789012345678),
            "member_count": member_count,
            "features": [],
        }

    @staticmethod
    def channel(
        channel_id: int = 111111111111111111,
        name: str = "test",
        channel_type: int = 0,
    ) -> dict[str, Any]:
        return {
            "id": str(channel_id),
            "name": name,
            "type": channel_type,
            "position": 0,
        }

    @staticmethod
    def message(
        message_id: int = 555555555555555555,
        content: str = "Test message",
        author_id: int = 123456789012345678,
        channel_id: int = 111111111111111111,
    ) -> dict[str, Any]:
        return {
            "id": str(message_id),
            "content": content,
            "channel_id": str(channel_id),
            "author": MockResponseBuilder.user(author_id),
            "timestamp": datetime.now().isoformat(),
            "edited_timestamp": None,
            "tts": False,
            "mention_everyone": False,
            "mentions": [],
            "mention_roles": [],
            "attachments": [],
            "embeds": [],
            "pinned": False,
            "type": 0,
        }

    @staticmethod
    def error(
        code: int = 50035,
        message: str = "Invalid Form Body",
        errors: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = {"code": code, "message": message}
        if errors:
            response["errors"] = errors
        return response
