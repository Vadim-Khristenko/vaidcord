from __future__ import annotations

from typing import Any

from .base import StorageKey


class PostgresFSMStorage:
    """Optional PostgreSQL storage stub."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise ImportError(
            "PostgresFSMStorage requires optional asyncpg/psycopg integration."
        )

    async def get_state(self, key: StorageKey) -> str | None: ...
