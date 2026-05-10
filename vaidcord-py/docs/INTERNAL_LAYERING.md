# Internal layering

Issue #32 traced VaidCord's three monolithic core classes — `Bot`,
`Router`, `HTTPClient` — and proposed splitting their responsibilities
into smaller, individually-testable collaborators. This document
captures the layering that landed; it should make it obvious where new
code lives and why the public facades stay small.

The public surface (`Bot`, `Router`, `HTTPClient`, `APIClient`) is
unchanged. Everything below sits behind it.

```
                                                public  private
                                                ──────  ───────
vaidcord.Bot ──────────► Router (filters / middleware / dispatch)
              │
              │  delegates parsing to:
              ▼
              vaidcord._internal.EventParser
                   - _raw (raw_data sharing modes)
                   - parse_event / parse_message / parse_user / ...
                   - parse_channel / parse_guild / parse_ready / parse_message_pin

              delegates message endpoints to:
              ▼
              vaidcord._internal.services.MessageService
                   - send_message / reply / send_components_v2
                   - send_dm / send_message_to_user / send_poll
                   - trigger_typing / list_messages / fetch_message
                   - edit_message / delete_message / crosspost_message
                   - add_reaction / delete_*_reaction / list_reactions
                   - clear_reaction(s) / bulk_delete_messages
                   - list_pins / get_channel_pins / pin_*_message / unpin_*
                   - get_poll_answer_voters / end_poll

vaidcord.HTTPClient (from vaidcord.http) is a thin orchestrator that
composes:

  vaidcord.http.transport.TransportSession   (aiohttp ClientSession)
  vaidcord.http.rate_limit.RateLimitManager  (per-route + global locks)
  vaidcord.http.retry.RetryPolicy            (exponential backoff)
  vaidcord.http.logging.RequestLogger        (+sanitize_*, extract_rate_limit_fields)
  vaidcord.http.config.{HTTPConfig, HTTPRequestContext, HTTPResponseData, RateLimitInfo}
  vaidcord.http.errors.{DiscordError, DiscordErrorCode}
```

## Why the split

Before:

* `bot.py` was ~1700 lines, mixing facade / gateway state / event
  parsing / cache mutation / resource wrappers / lifecycle.
* `http.py` was ~620 lines mixing aiohttp ownership / retry / rate
  limits / sanitization / logging.

After:

* `bot.py` is 1200 lines. Parsing and message endpoints are gone.
* `http/` is a six-module subpackage where each file owns one concern.

The smaller surface makes:

* Performance work easier — each collaborator can be benchmarked alone
  (see `benchmarks/model_parse.py` for an EventParser-style benchmark).
* New Discord resource families easier to add — they get their own
  service module under `_internal/services/` and the Bot facade only
  grows by one delegating method per endpoint.
* New transports easier to plug in — swap `TransportSession` for an
  in-process implementation and the rest of the HTTP stack keeps
  working unchanged. The mock tests already do this through
  `session_provider` / `session_closer` callbacks.

## Backwards compatibility

Every previously-public symbol still resolves at the same dotted path:

| Symbol                       | Old location           | New location                                      |
|------------------------------|------------------------|---------------------------------------------------|
| `HTTPClient`                 | `vaidcord.http`        | `vaidcord.http.client` (re-exported)              |
| `HTTPConfig`                 | `vaidcord.http`        | `vaidcord.http.config` (re-exported)              |
| `HTTPResponseData`           | `vaidcord.http`        | `vaidcord.http.config` (re-exported)              |
| `RateLimitInfo`              | `vaidcord.http`        | `vaidcord.http.config` (re-exported)              |
| `RateLimitManager`           | `vaidcord.http`        | `vaidcord.http.rate_limit` (re-exported)          |
| `DiscordError`               | `vaidcord.http`        | `vaidcord.http.errors` (re-exported)              |
| `DiscordErrorCode`           | `vaidcord.http`        | `vaidcord.http.errors` (re-exported)              |
| `Bot._parse_event` etc.      | `vaidcord.bot`         | `vaidcord._internal.EventParser` (Bot delegates)  |
| `Bot.send_message` etc.      | `vaidcord.bot`         | `vaidcord._internal.MessageService` (Bot delegates) |

Subclasses that overrode the private parser methods (`_parse_event`,
`_parse_message`, …) keep working; the shims preserve method dispatch.

## What's still inside Bot

* Lifecycle (`start`, `stop`, `wait_until_ready`, `_state`).
* Gateway runtime wiring (`runtime`, `_handle_dispatch`,
  `_connect_gateway`, `_send_payload`, `_identify`, `_heartbeat`).
* Cache (`_users`, `_channels`, `_guilds`).
* Application command management (`slash_command`, `user_command`,
  `message_command`, `sync_application_commands`, …).
* Voice manager (`voice`).
* The thin REST helpers that aren't message-specific
  (`get_current_application`, `delete_webhook`).

These remain on Bot until #32 lands additional service modules:
`ChannelService`, `GuildService`, `UserService`, `ApplicationService`.
The pattern to follow is the one set by `MessageService`:

1. Create `_internal/services/<name>.py` with the resource methods.
2. Have it take a `<Name>Host` Protocol describing the slice of Bot it
   needs (api_client, parser, caches, occasional `request`).
3. In `Bot.__init__`, instantiate the service and stash it.
4. Replace each Bot method body with a one-line delegation.
5. Run tests; if a test monkey-patches a Bot method, route the service
   back through the host so the override still takes effect.

## File reference

```
src/vaidcord/
  bot.py                             # Bot facade (1200 LOC, was ~1700)
  router.py                          # Router (split pending)
  http/
    __init__.py                      # back-compat re-exports
    client.py                        # HTTPClient orchestrator
    transport.py                     # TransportSession (aiohttp ownership)
    rate_limit.py                    # RateLimitManager
    retry.py                         # RetryPolicy
    logging.py                       # RequestLogger + sanitize helpers
    config.py                        # HTTPConfig, HTTPResponseData, ...
    errors.py                        # legacy DiscordError + DiscordErrorCode
  _internal/                         # private collaborators (do not import)
    __init__.py
    event_parser.py                  # EventParser
    services/
      __init__.py
      messages.py                    # MessageService
```
