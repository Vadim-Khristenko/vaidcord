"""Tests for FSM storage package structure and backends."""

import pytest

from vaidcord.fsm import (
    FSMScope,
    MemoryFSMStorage,
    MongoFSMStorage,
    PostgresFSMStorage,
    RedisFSMStorage,
    SQLiteFSMStorage,
    StorageKey,
)


@pytest.mark.asyncio
async def test_sqlite_storage_roundtrip() -> None:
    storage = SQLiteFSMStorage()
    key = StorageKey.member(guild_id=1, user_id=2)

    await storage.set_state(key, "step:1")
    await storage.set_data(key, {"name": "alice"})

    assert await storage.get_state(key) == "step:1"
    assert await storage.get_data(key) == {"name": "alice"}

    await storage.update_data(key, age=20)
    assert await storage.get_data(key) == {"name": "alice", "age": 20}

    await storage.clear(key)
    assert await storage.get_state(key) is None
    assert await storage.get_data(key) == {}


@pytest.mark.asyncio
async def test_memory_storage_policy_setters() -> None:
    storage = MemoryFSMStorage()
    await storage.set_many_states(
        {
            StorageKey.topic(9): "topic",
            StorageKey.channel(8): "channel",
            StorageKey.user(7): "user",
        }
    )
    await storage.set_state_for(FSMScope.GUILD, "guild", guild_id=6)

    assert await storage.get_state(StorageKey.topic(9)) == "topic"
    assert await storage.get_state(StorageKey.channel(8)) == "channel"
    assert await storage.get_state(StorageKey.user(7)) == "user"
    assert await storage.get_state(StorageKey.guild(6)) == "guild"


def test_optional_storages_raise_informative_errors() -> None:
    with pytest.raises(ImportError):
        RedisFSMStorage()
    with pytest.raises(ImportError):
        MongoFSMStorage()
    with pytest.raises(ImportError):
        PostgresFSMStorage()
