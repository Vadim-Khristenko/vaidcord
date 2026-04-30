from __future__ import annotations

from typing import Any

from .base import StorageKey


class MongoFSMStorage:
    """Optional MongoDB storage stub."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise ImportError(
            "MongoFSMStorage requires optional pymongo/motor integration."
        )

    async def get_state(self, key: StorageKey) -> str | None: ...
