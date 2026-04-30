# Python driver architecture

## Components

- `Bot`: transport + API surface.
- `Dispatcher`: root router and lifecycle runtime.
- `Router`: feature-level module.
- `Middleware`: cross-cutting behavior.
- `Filters`: handler matching + parameter extraction.
- `FSM`: scoped state management.

## Root router rule

`Dispatcher` is the root and should not be nested.

Valid:
- Dispatcher -> Router -> Router

Invalid:
- Dispatcher -> Dispatcher

## DI hierarchy

Dependency visibility is inherited downward.

- Provide on dispatcher → available everywhere.
- Provide on router → available in router subtree only.

## Handler argument resolution

Handler kwargs are populated from:
1. DI providers
2. Filter payload data

If a handler argument name matches a provided dependency/filter key, it is injected.

## FSM behavior

- `Dispatcher()` auto-registers FSM middleware.
- Default storage: `MemoryFSMStorage`.
- Custom storage can be passed via `Dispatcher(storage=...)`.

## Startup modes

- `start_polling(bot)`
- `start_websocket(bot)`
- `start_webhook(bot, drop_pending_updates=True)`

`start_webhook` performs webhook cleanup through `bot.delete_webhook(...)` before start.
