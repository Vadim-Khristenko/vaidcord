# Application API resources

VaidCord exposes Discord application resources as lightweight models so you can work with structured data instead of raw payload dictionaries.

## Layer map (after modular refactor)

- `vaidcord.bot.Bot`: high-level orchestration facade (`start`, `stop`, `send_message`, application helpers).
- `vaidcord.gateway_runtime.GatewayRuntime`: gateway session lifecycle, identify flow, heartbeat, and dispatch loop.
- `vaidcord.api_client.APIClient`: REST layer used by `Bot`, backed by `HTTPClient`.
- `vaidcord.dispatcher.Dispatcher`: router/FSM lifecycle and startup modes, typed against a narrow bot protocol instead of a concrete `Bot`.

## Models

- `Application` represents the current Discord application or bot app record.
- `ApplicationRoleConnectionMetadata` represents a single role-connection metadata record.
- `ApplicationRoleConnectionMetadataType` mirrors the Discord enum for metadata comparisons.

`Application.from_dict(...)` keeps the original payload in `raw` so nothing gets lost if Discord adds fields you do not model yet.

## Current application

Use the current-application helpers when you want to read or patch the app that owns the token:

- `await bot.get_current_application()`
- `await bot.edit_current_application(...)`

The edit call forwards the payload directly to Discord and returns an `Application` model with the updated data.

## Role connection metadata

Role-connection metadata is the structured data Discord uses for role connection screens and verification URLs.

- `await bot.get_application_role_connection_metadata(application_id)` fetches the configured metadata records.
- `await bot.update_application_role_connection_metadata(application_id, records)` replaces the records.

Important details:

- Discord allows at most 5 metadata records.
- `ApplicationRoleConnectionMetadata.to_dict()` only serializes localization fields when they are present.
- `ApplicationRoleConnectionMetadata.from_dict()` restores the enum type automatically.

Example:

```python
from vaidcord import (
    ApplicationRoleConnectionMetadata,
    ApplicationRoleConnectionMetadataType,
)

records = [
    ApplicationRoleConnectionMetadata(
        type=ApplicationRoleConnectionMetadataType.BOOLEAN_EQUAL,
        key="is_beta_tester",
        name="Beta tester",
        description="Granted when the user is part of the beta program",
    ),
]

await bot.update_application_role_connection_metadata(application_id, records)
```

## What to send through `edit_current_application`

Common fields include:

- `name`
- `description`
- `icon`
- `bot_public`
- `bot_require_code_grant`
- `role_connections_verification_url`
- `interactions_endpoint_url`
- `flags`

If you are building a dashboard or admin panel, this API is a clean way to keep the application record in sync with your UI.

## Example files

- [docs/OAUTH2.md](OAUTH2.md) pairs well with application management because many admin flows start with OAuth2.
