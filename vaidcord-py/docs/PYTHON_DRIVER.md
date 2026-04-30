# Python driver guide

## Dispatcher defaults

`Dispatcher()` automatically registers FSM middleware.
If `storage` is not provided, it uses `MemoryFSMStorage`.

```python
from vaidcord import Dispatcher

dp = Dispatcher()  # in-memory FSM by default
```

You can pass custom storage:

```python
from vaidcord import Dispatcher
from vaidcord.fsm.storage.sqlite import SQLiteFSMStorage

dp = Dispatcher(storage=SQLiteFSMStorage("fsm.db"))
```

## Handler DI

Dependencies can be registered by name and injected into handlers.

```python
router.provide("service_name", "billing")

@router.message()
async def handler(event, service_name: str):
    ...
```
