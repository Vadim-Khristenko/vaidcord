from __future__ import annotations

import json
from typing import Any

from .base import FSMScope, StateValue, StorageKey


class PostgresFSMStorage:
    """Async PostgreSQL FSM storage (requires optional `asyncpg` pool/connection)."""

    def __init__(self, conn: Any | None = None, *, table: str = "vaidcord_fsm") -> None:
        if conn is None:
            raise ImportError(
                "PostgresFSMStorage requires asyncpg connection/pool. "
                "Install with: pip install asyncpg"
            )
        self._conn = conn
        self._table = table

    @staticmethod
    def _key_text(key: StorageKey) -> str:
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

    async def get_state(self, key: StorageKey) -> str | None:
        row = await self._conn.fetchrow(
            f"SELECT state FROM {self._table} WHERE key = $1",
            self._key_text(key),
        )
        return None if row is None else row["state"]

    async def set_state(self, key: StorageKey, state: StateValue | None) -> None:
        current_data = await self.get_data(key)
        await self._conn.execute(
            f"""
            INSERT INTO {self._table}(key, state, data)
            VALUES($1, $2, $3)
            ON CONFLICT(key)
            DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data
            """,
            self._key_text(key),
            None if state is None else str(state),
            json.dumps(current_data),
        )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        row = await self._conn.fetchrow(
            f"SELECT data FROM {self._table} WHERE key = $1",
            self._key_text(key),
        )
        if row is None or row["data"] is None:
            return {}
        data = row["data"]
        if isinstance(data, str):
            return json.loads(data)
        return dict(data)

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        current_state = await self.get_state(key)
        await self._conn.execute(
            f"""
            INSERT INTO {self._table}(key, state, data)
            VALUES($1, $2, $3)
            ON CONFLICT(key)
            DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data
            """,
            self._key_text(key),
            current_state,
            json.dumps(data),
        )

    async def update_data(self, key: StorageKey, **kwargs: Any) -> dict[str, Any]:
        current = await self.get_data(key)
        current.update(kwargs)
        await self.set_data(key, current)
        return current

    async def clear(self, key: StorageKey) -> None:
        await self._conn.execute(
            f"DELETE FROM {self._table} WHERE key = $1",
            self._key_text(key),
        )

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
