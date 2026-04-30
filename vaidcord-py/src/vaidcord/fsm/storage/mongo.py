from __future__ import annotations

from typing import Any, Protocol

from .base import FSMScope, StateValue, StorageKey


class AsyncMongoCollection(Protocol):
    async def find_one(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None: ...
    async def update_one(self, *args: Any, **kwargs: Any) -> Any: ...
    async def delete_one(self, *args: Any, **kwargs: Any) -> Any: ...


class MongoFSMStorage:
    """Async MongoDB FSM storage (pymongo asynchronous collection)."""

    def __init__(self, collection: AsyncMongoCollection | None = None) -> None:
        if collection is None:
            raise ImportError(
                "MongoFSMStorage requires pymongo asynchronous AsyncCollection. "
                "Install with: pip install pymongo"
            )
        self._collection = collection

    @staticmethod
    def _doc_id(key: StorageKey) -> str:
        return (
            f"{key.scope}:{key.guild_id}:{key.channel_id}:"
            f"{key.topic_id}:{key.user_id}:{key.custom_id}"
        )

    async def get_state(self, key: StorageKey) -> str | None:
        doc = await self._collection.find_one({"_id": self._doc_id(key)}, {"state": 1})
        return None if not doc else doc.get("state")

    async def set_state(self, key: StorageKey, state: StateValue | None) -> None:
        await self._collection.update_one(
            {"_id": self._doc_id(key)},
            {"$set": {"state": None if state is None else str(state)}},
            upsert=True,
        )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        doc = await self._collection.find_one({"_id": self._doc_id(key)}, {"data": 1})
        return {} if not doc else dict(doc.get("data") or {})

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        await self._collection.update_one(
            {"_id": self._doc_id(key)},
            {"$set": {"data": dict(data)}},
            upsert=True,
        )

    async def update_data(self, key: StorageKey, **kwargs: Any) -> dict[str, Any]:
        current = await self.get_data(key)
        current.update(kwargs)
        await self.set_data(key, current)
        return current

    async def clear(self, key: StorageKey) -> None:
        await self._collection.delete_one({"_id": self._doc_id(key)})

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
