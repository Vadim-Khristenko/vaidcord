from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vaidcord.types import Event
from vaidcord.typing import EventHandlerResult, NextHandler

from .storage.base import BaseFSMStorage, FSMScope, StateValue, StorageKey
from .storage.memory import MemoryFSMStorage


@dataclass
class FSMContext:
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
    storage: BaseFSMStorage = field(default_factory=MemoryFSMStorage)
    primary_scope: FSMScope = FSMScope.MEMBER
    scopes: tuple[FSMScope, ...] = (
        FSMScope.MEMBER,
        FSMScope.USER,
        FSMScope.CHANNEL,
        FSMScope.TOPIC,
        FSMScope.GUILD,
    )

    async def __call__(self, event: Event, handler: NextHandler) -> EventHandlerResult:
        manager = FSMManager(self.storage)
        event.context["fsm_manager"] = manager

        ids = self._resolve_ids(event)
        fsm_map = self._build_fsm_map(manager, ids)
        if fsm_map:
            event.context["fsm_map"] = fsm_map
            event.context["fsm_states"] = {
                scope: await fsm.get_state() for scope, fsm in fsm_map.items()
            }
            primary = fsm_map.get(self.primary_scope)
            primary_scope = self.primary_scope if primary is not None else next(iter(fsm_map))
            event.context["fsm"] = primary or fsm_map[primary_scope]
            event.context["fsm_primary_scope"] = primary_scope
            event.context["fsm_state"] = event.context["fsm_states"].get(primary_scope)

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
