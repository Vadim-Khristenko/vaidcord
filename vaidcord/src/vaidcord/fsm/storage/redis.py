from __future__ import annotations

import json
from typing import Any

from .base import FSMScope, StateValue, StorageKey


class RedisFSMStorage:
    """Async Redis FSM storage (requires optional `redis` package)."""

    def __init__(self, client: Any | None = None, *, prefix: str = "vaidcord:fsm") -> None:
        if client is None:
            try:
                from redis.asyncio import Redis  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise ImportError(
                    "RedisFSMStorage requires optional dependency `redis`. "
                    "Install with: pip install redis"
                ) from exc
            client = Redis()
        self._redis = client
        self._prefix = prefix

    def _key(self, key: StorageKey) -> str:
        encoded = json.dumps(
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
        return f"{self._prefix}:{encoded}"

    async def get_state(self, key: StorageKey) -> str | None:
        data = await self._redis.hget(self._key(key), "state")
        if data is None:
            return None
        return data.decode() if isinstance(data, bytes) else str(data)

    async def set_state(self, key: StorageKey, state: StateValue | None) -> None:
        redis_key = self._key(key)
        if state is None:
            await self._redis.hdel(redis_key, "state")
            return
        await self._redis.hset(redis_key, mapping={"state": str(state)})

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        data = await self._redis.hget(self._key(key), "data")
        if data is None:
            return {}
        raw = data.decode() if isinstance(data, bytes) else str(data)
        return json.loads(raw)

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        await self._redis.hset(self._key(key), mapping={"data": json.dumps(data)})

    async def update_data(self, key: StorageKey, **kwargs: Any) -> dict[str, Any]:
        current = await self.get_data(key)
        current.update(kwargs)
        await self.set_data(key, current)
        return current

    async def clear(self, key: StorageKey) -> None:
        await self._redis.delete(self._key(key))

    async def set_many_states(self, assignments: dict[StorageKey, StateValue | None]) -> None:
        for key, state in assignments.items():
            await self.set_state(key, state)

    async def get_many_states(self, keys: list[StorageKey]) -> dict[StorageKey, str | None]:
        return {key: await self.get_state(key) for key in keys}

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
        await self.set_state(
            StorageKey(
                scope=scope,
                guild_id=guild_id,
                channel_id=channel_id,
                topic_id=topic_id,
                user_id=user_id,
                custom_id=custom_id,
            ),
            state,
        )

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
