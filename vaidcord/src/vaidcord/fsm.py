"""
Finite-state machine primitives for conversational flows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from vaidcord.types import Event


@dataclass(frozen=True)
class StorageKey:
    """Key for FSM storage records."""

    user_id: int
    chat_id: int


class BaseFSMStorage(Protocol):
    """Storage interface for FSM state and per-state data."""

    async def get_state(self, key: StorageKey) -> str | None: ...

    async def set_state(self, key: StorageKey, state: str | None) -> None: ...

    async def get_data(self, key: StorageKey) -> dict[str, Any]: ...

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None: ...

    async def update_data(self, key: StorageKey, **kwargs: Any) -> dict[str, Any]: ...

    async def clear(self, key: StorageKey) -> None: ...


class MemoryFSMStorage:
    """In-memory FSM storage implementation for simple bots/tests."""

    def __init__(self) -> None:
        self._states: dict[StorageKey, str | None] = {}
        self._data: dict[StorageKey, dict[str, Any]] = {}

    async def get_state(self, key: StorageKey) -> str | None:
        return self._states.get(key)

    async def set_state(self, key: StorageKey, state: str | None) -> None:
        if state is None:
            self._states.pop(key, None)
            return
        self._states[key] = state

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


@dataclass
class FSMContext:
    """Context wrapper bound to a storage key for a single conversation."""

    storage: BaseFSMStorage
    key: StorageKey

    async def get_state(self) -> str | None:
        return await self.storage.get_state(self.key)

    async def set_state(self, state: str | None) -> None:
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
class FSMMiddleware:
    """
    Middleware that attaches `event.context['fsm']` when user/chat ids are available.
    """

    storage: BaseFSMStorage = field(default_factory=MemoryFSMStorage)

    async def __call__(self, event: Event, handler: Any) -> Any:
        user_id = self._resolve_user_id(event)
        chat_id = self._resolve_chat_id(event)
        if user_id is not None and chat_id is not None:
            event.context["fsm"] = FSMContext(
                storage=self.storage,
                key=StorageKey(user_id=user_id, chat_id=chat_id),
            )
        return await handler(event)

    @staticmethod
    def _resolve_user_id(event: Event) -> int | None:
        if event.user is not None:
            return event.user.id
        if event.message is not None:
            return event.message.author.id
        user_id = event.data.get("user_id")
        return int(user_id) if user_id is not None else None

    @staticmethod
    def _resolve_chat_id(event: Event) -> int | None:
        if event.channel is not None:
            return event.channel.id
        if event.message is not None:
            return event.message.channel.id
        channel_id = event.data.get("channel_id")
        if channel_id is not None:
            return int(channel_id)
        guild_id = event.data.get("guild_id")
        return int(guild_id) if guild_id is not None else None
