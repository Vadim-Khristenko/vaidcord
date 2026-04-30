from __future__ import annotations

from typing import Any

from .base import StorageKey


class RedisFSMStorage:
    """Optional Redis storage stub. Install redis client and implement backend wiring."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise ImportError(
            "RedisFSMStorage requires optional redis integration. "
            "Install extra deps and provide implementation."
        )

    async def get_state(self, key: StorageKey) -> str | None: ...
