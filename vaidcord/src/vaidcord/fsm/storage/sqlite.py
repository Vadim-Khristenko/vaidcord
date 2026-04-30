from __future__ import annotations

import json
import sqlite3
from typing import Any

from .base import StateValue, StorageKey


class SQLiteFSMStorage:
    """SQLite-backed FSM storage with stdlib sqlite3 (no extra deps)."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fsm_state (
                key TEXT PRIMARY KEY,
                state TEXT,
                data TEXT
            )
            """
        )
        self._conn.commit()

    @staticmethod
    def _key_text(key: StorageKey) -> str:
        payload: dict[str, Any] = {
            "scope": str(key.scope),
            "guild_id": key.guild_id,
            "channel_id": key.channel_id,
            "topic_id": key.topic_id,
            "user_id": key.user_id,
            "custom_id": key.custom_id,
        }
        return json.dumps(payload, sort_keys=True)

    def _get_row(self, key: StorageKey) -> tuple[Any, ...] | None:
        return self._conn.execute(
            "SELECT state,data FROM fsm_state WHERE key=?",
            (self._key_text(key),),
        ).fetchone()

    async def get_state(self, key: StorageKey) -> str | None:
        row = self._get_row(key)
        return row[0] if row else None

    async def set_state(self, key: StorageKey, state: StateValue | None) -> None:
        current_data = await self.get_data(key)
        self._conn.execute(
            """
            INSERT INTO fsm_state(key,state,data)
            VALUES(?,?,?)
            ON CONFLICT(key)
            DO UPDATE SET state=excluded.state, data=excluded.data
            """,
            (self._key_text(key), str(state) if state is not None else None, json.dumps(current_data)),
        )
        self._conn.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        row = self._get_row(key)
        if not row or row[1] is None:
            return {}
        return json.loads(row[1])

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        current_state = await self.get_state(key)
        self._conn.execute(
            """
            INSERT INTO fsm_state(key,state,data)
            VALUES(?,?,?)
            ON CONFLICT(key)
            DO UPDATE SET state=excluded.state, data=excluded.data
            """,
            (self._key_text(key), current_state, json.dumps(data)),
        )
        self._conn.commit()

    async def update_data(self, key: StorageKey, **kwargs: Any) -> dict[str, Any]:
        data = await self.get_data(key)
        data.update(kwargs)
        await self.set_data(key, data)
        return data

    async def clear(self, key: StorageKey) -> None:
        self._conn.execute("DELETE FROM fsm_state WHERE key=?", (self._key_text(key),))
        self._conn.commit()
