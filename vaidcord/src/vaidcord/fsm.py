"""
Finite-state machine primitives for conversational flows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, TypeAlias

from vaidcord.types import Event

StateValue: TypeAlias = str | StrEnum


class FSMScope(StrEnum):
    """Policy/scope for state partitioning."""

    USER = "user"
    CHANNEL = "channel"
    TOPIC = "topic"
    GUILD = "guild"
    MEMBER = "member"  # user scoped inside a guild
    CUSTOM = "custom"


@dataclass(frozen=True)
class StorageKey:
    """Key for FSM storage records."""

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
        """Compatibility helper for old `(user_id, chat_id)` key usage."""
        return cls(scope=FSMScope.MEMBER, guild_id=chat_id, user_id=user_id)


class BaseFSMStorage(Protocol):
    """Storage interface for FSM state and per-state data."""

    async def get_state(self, key: StorageKey) -> str | None: ...

    async def set_state(self, key: StorageKey, state: StateValue | None) -> None: ...

    async def get_data(self, key: StorageKey) -> dict[str, Any]: ...

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None: ...

    async def update_data(self, key: StorageKey, **kwargs: Any) -> dict[str, Any]: ...

    async def clear(self, key: StorageKey) -> None: ...


class MemoryFSMStorage:
    """In-memory FSM storage implementation for simple bots/tests."""

    def __init__(self) -> None:
        self._states: dict[StorageKey, str | None] = {}
        self._data: dict[StorageKey, dict[str, Any]] = {}

    @staticmethod
    def _normalize_state(state: StateValue | None) -> str | None:
        return str(state) if state is not None else None

    async def get_state(self, key: StorageKey) -> str | None:
        return self._states.get(key)

    async def set_state(self, key: StorageKey, state: StateValue | None) -> None:
        normalized = self._normalize_state(state)
        if normalized is None:
            self._states.pop(key, None)
            return
        self._states[key] = normalized

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        return dict(self._data.get(key, {}))

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        self._data[key] = dict(data)

    async def update_data(self, key: StorageKey, **kwargs: Any) -> dict[str, Any]:
        current = self._data.setdefault(key, {})
        current.update(kwargs)
        return dict(current)

    async def clear(self, key: StorageKey) -> None:
        self._states.pop(key, None)
        self._data.pop(key, None)

    async def set_many_states(
        self,
        assignments: dict[StorageKey, StateValue | None],
    ) -> None:
        """Fast bulk update for many keys/policies."""
        for key, state in assignments.items():
            await self.set_state(key, state)

    async def set_state_for(
        self,
        scope: FSMScope,
        state: StateValue | None,
        *,
        guild_id: int | None = None,
        channel_id: int | None = None,
        topic_id: int | None = None,
        user_id: int | None = None,
        custom_id: str | None = None,
    ) -> None:
        """Fast state setter by policy dimensions."""
        key = StorageKey(
            scope=scope,
            guild_id=guild_id,
            channel_id=channel_id,
            topic_id=topic_id,
            user_id=user_id,
            custom_id=custom_id,
        )
        await self.set_state(key, state)


@dataclass
class FSMContext:
    """Context wrapper bound to a storage key for a single conversation."""

    storage: BaseFSMStorage
    key: StorageKey

    async def get_state(self) -> str | None:
        return await self.storage.get_state(self.key)

    async def set_state(self, state: StateValue | None) -> None:
        await self.storage.set_state(self.key, state)

    async def get_data(self) -> dict[str, Any]:
        return await self.storage.get_data(self.key)

    async def set_data(self, data: dict[str, Any]) -> None:
        await self.storage.set_data(self.key, data)

    async def update_data(self, **kwargs: Any) -> dict[str, Any]:
        return await self.storage.update_data(self.key, **kwargs)

    async def clear(self) -> None:
        await self.storage.clear(self.key)


@dataclass
class FSMManager:
    """Builder/factory for strongly scoped FSM contexts."""

    storage: BaseFSMStorage

    def user(self, user_id: int) -> FSMContext:
        return FSMContext(self.storage, StorageKey.user(user_id))

    def channel(self, channel_id: int) -> FSMContext:
        return FSMContext(self.storage, StorageKey.channel(channel_id))

    def topic(self, topic_id: int) -> FSMContext:
        return FSMContext(self.storage, StorageKey.topic(topic_id))

    def guild(self, guild_id: int) -> FSMContext:
        return FSMContext(self.storage, StorageKey.guild(guild_id))

    def member(self, guild_id: int, user_id: int) -> FSMContext:
        return FSMContext(self.storage, StorageKey.member(guild_id, user_id))

    def custom(self, custom_id: str) -> FSMContext:
        return FSMContext(self.storage, StorageKey.custom(custom_id))


@dataclass
class FSMMiddleware:
    """
    Middleware that attaches FSM contexts for multiple scope policies.

    Populates:
    - `event.context['fsm']` (primary policy context)
    - `event.context['fsm_map']` (all resolved policy contexts)
    - `event.context['fsm_manager']` (helper manager)
    """

    storage: BaseFSMStorage = field(default_factory=MemoryFSMStorage)
    primary_scope: FSMScope = FSMScope.MEMBER
    scopes: tuple[FSMScope, ...] = (
        FSMScope.MEMBER,
        FSMScope.USER,
        FSMScope.CHANNEL,
        FSMScope.TOPIC,
        FSMScope.GUILD,
    )

    async def __call__(self, event: Event, handler: Any) -> Any:
        manager = FSMManager(self.storage)
        event.context["fsm_manager"] = manager

        ids = self._resolve_ids(event)
        fsm_map = self._build_fsm_map(manager, ids)
        if fsm_map:
            event.context["fsm_map"] = fsm_map
            primary = fsm_map.get(self.primary_scope)
            if primary is not None:
                event.context["fsm"] = primary

        return await handler(event)

    def _build_fsm_map(
        self,
        manager: FSMManager,
        ids: dict[str, int | None],
    ) -> dict[FSMScope, FSMContext]:
        fsm_map: dict[FSMScope, FSMContext] = {}
        for scope in self.scopes:
            if scope == FSMScope.USER and ids["user_id"] is not None:
                fsm_map[scope] = manager.user(ids["user_id"])
            elif scope == FSMScope.CHANNEL and ids["channel_id"] is not None:
                fsm_map[scope] = manager.channel(ids["channel_id"])
            elif scope == FSMScope.TOPIC and ids["topic_id"] is not None:
                fsm_map[scope] = manager.topic(ids["topic_id"])
            elif scope == FSMScope.GUILD and ids["guild_id"] is not None:
                fsm_map[scope] = manager.guild(ids["guild_id"])
            elif (
                scope == FSMScope.MEMBER
                and ids["guild_id"] is not None
                and ids["user_id"] is not None
            ):
                fsm_map[scope] = manager.member(ids["guild_id"], ids["user_id"])
        return fsm_map

    @staticmethod
    def _resolve_ids(event: Event) -> dict[str, int | None]:
        user_id = (
            event.user.id
            if event.user is not None
            else event.message.author.id
            if event.message is not None
            else _to_int(event.data.get("user_id"))
        )
        channel_id = (
            event.channel.id
            if event.channel is not None
            else event.message.channel.id
            if event.message is not None
            else _to_int(event.data.get("channel_id"))
        )
        guild_id = (
            event.guild.id
            if event.guild is not None
            else event.message.guild.id
            if event.message is not None and event.message.guild is not None
            else _to_int(event.data.get("guild_id"))
        )
        topic_id = _to_int(event.data.get("topic_id")) or _to_int(event.data.get("thread_id"))
        return {
            "user_id": user_id,
            "channel_id": channel_id,
            "guild_id": guild_id,
            "topic_id": topic_id,
        }


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
