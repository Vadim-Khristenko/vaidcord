from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, TypeAlias

StateValue: TypeAlias = str | StrEnum


class FSMScope(StrEnum):
    USER = "user"
    CHANNEL = "channel"
    TOPIC = "topic"
    GUILD = "guild"
    MEMBER = "member"
    CUSTOM = "custom"


@dataclass(frozen=True)
class StorageKey:
    scope: FSMScope = FSMScope.CUSTOM
    guild_id: int | None = None
    channel_id: int | None = None
    topic_id: int | None = None
    user_id: int | None = None
    custom_id: str | None = None

    @classmethod
    def user(cls, user_id: int) -> StorageKey:
        return cls(scope=FSMScope.USER, user_id=user_id)

    @classmethod
    def channel(cls, channel_id: int) -> StorageKey:
        return cls(scope=FSMScope.CHANNEL, channel_id=channel_id)

    @classmethod
    def topic(cls, topic_id: int) -> StorageKey:
        return cls(scope=FSMScope.TOPIC, topic_id=topic_id)

    @classmethod
    def guild(cls, guild_id: int) -> StorageKey:
        return cls(scope=FSMScope.GUILD, guild_id=guild_id)

    @classmethod
    def member(cls, guild_id: int, user_id: int) -> StorageKey:
        return cls(scope=FSMScope.MEMBER, guild_id=guild_id, user_id=user_id)

    @classmethod
    def custom(cls, custom_id: str) -> StorageKey:
        return cls(scope=FSMScope.CUSTOM, custom_id=custom_id)

    @classmethod
    def from_legacy_ids(cls, *, user_id: int, chat_id: int) -> StorageKey:
        return cls(scope=FSMScope.MEMBER, guild_id=chat_id, user_id=user_id)


class BaseFSMStorage(Protocol):
    async def get_state(self, key: StorageKey) -> str | None: ...

    async def set_state(self, key: StorageKey, state: StateValue | None) -> None: ...

    async def get_data(self, key: StorageKey) -> dict[str, Any]: ...

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None: ...

    async def update_data(self, key: StorageKey, **kwargs: Any) -> dict[str, Any]: ...

    async def clear(self, key: StorageKey) -> None: ...
