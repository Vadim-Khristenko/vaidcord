from __future__ import annotations

import json
import logging
from typing import Any

from .base import FSMScope, StateValue, StorageKey

logger = logging.getLogger(__name__)


class MemoryFSMStorage:
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
            logger.debug("FSM memory state cleared for key=%s", key)
            return
        self._states[key] = normalized
        logger.debug("FSM memory state set for key=%s", key)

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

    async def set_many_states(self, assignments: dict[StorageKey, StateValue | None]) -> None:
        for key, state in assignments.items():
            await self.set_state(key, state)

    async def get_many_states(self, keys: list[StorageKey]) -> dict[StorageKey, str | None]:
        return {key: self._states.get(key) for key in keys}

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
        key = StorageKey(
            scope=scope,
            guild_id=guild_id,
            channel_id=channel_id,
            topic_id=topic_id,
            user_id=user_id,
            custom_id=custom_id,
        )
        await self.set_state(key, state)

    async def transition_data(
        self,
        from_key: StorageKey,
        to_key: StorageKey,
        *,
        clear_source: bool = False,
        merge: bool = True,
    ) -> dict[str, Any]:
        source = await self.get_data(from_key)
        if merge:
            target = await self.get_data(to_key)
            target.update(source)
            await self.set_data(to_key, target)
            result = target
        else:
            await self.set_data(to_key, source)
            result = source
        if clear_source:
            await self.clear(from_key)
        return result

    async def export_snapshot(self) -> dict[str, Any]:
        def encode_key(key: StorageKey) -> str:
            return json.dumps(
                {
                    "scope": str(key.scope),
                    "guild_id": key.guild_id,
                    "channel_id": key.channel_id,
                    "topic_id": key.topic_id,
                    "user_id": key.user_id,
                    "custom_id": key.custom_id,
                },
                sort_keys=True,
            )

        snapshot = {
            "states": {encode_key(k): v for k, v in self._states.items()},
            "data": {encode_key(k): v for k, v in self._data.items()},
        }
        logger.info("FSM memory snapshot exported: %s keys", len(self._states))
        return snapshot

    async def import_snapshot(self, snapshot: dict[str, Any]) -> None:
        def decode_key(raw: str) -> StorageKey:
            payload = json.loads(raw)
            return StorageKey(
                scope=FSMScope(payload["scope"]),
                guild_id=payload.get("guild_id"),
                channel_id=payload.get("channel_id"),
                topic_id=payload.get("topic_id"),
                user_id=payload.get("user_id"),
                custom_id=payload.get("custom_id"),
            )

        self._states = {
            decode_key(raw_key): value
            for raw_key, value in snapshot.get("states", {}).items()
        }
        self._data = {
            decode_key(raw_key): dict(value)
            for raw_key, value in snapshot.get("data", {}).items()
        }
        logger.warning("FSM memory snapshot imported: %s keys", len(self._states))
