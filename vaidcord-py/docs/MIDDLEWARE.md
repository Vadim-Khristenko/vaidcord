# Middleware in VaidCord (Outer + Inner)

VaidCord now supports two middleware layers inspired by aiogram:

- **Outer middleware** — runs before filter checks and handler selection.
- **Inner middleware** — runs around the selected handler (after filters pass).

## Why two layers?

Use **outer** for global gates and data preparation:
- maintenance mode
- anti-spam/ban checks
- request tracing bootstrap
- FSM context hydration

Use **inner** for handler-scoped cross-cutting logic:
- timing
- logging selected handlers
- post-processing output

## API

```python
router.add_outer_middleware(mw, priority=100)
router.outer_middleware(priority=100)

router.add_middleware(mw, priority=0)
router.middleware(priority=0)

# unified API
router.register_middleware(mw, layer="outer", priority=100)
router.middleware_layer(layer="inner", priority=0)
```

## Execution model

1. Outer middleware chain
2. Router/global filters
3. Handler filters
4. Inner middleware chain
5. Handler

If outer middleware does **not** call `await next_handler(event)`, update is dropped.

## FSM as system middleware

`Dispatcher` wires `FSMMiddleware` as **outer middleware** by default.
This guarantees FSM context exists before filters and handler matching.

## Example

```python
@router.outer_middleware(priority=100)
async def gate(event, next_handler):
    if event.context.get("maintenance_mode"):
        return None
    return await next_handler(event)

@router.middleware()
async def trace(event, next_handler):
    print("before handler")
    result = await next_handler(event)
    print("after handler")
    return result
```


## Stop propagation explicitly

Use `Router.stop_propagation()` inside middleware/handler when you want to hard-drop the event.


## Class-based middleware (recommended)

```python
from vaidcord import BaseMiddleware

class AuditMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        data["audit"] = {"event_type": event.type.value}
        return await handler(event, data)

router.add_outer_middleware(AuditMiddleware())
```

You can register **multiple middleware objects**; they execute by priority (higher first).
