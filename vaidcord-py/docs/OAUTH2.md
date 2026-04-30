# OAuth2 in VaidCord

The OAuth2 helpers in VaidCord cover the parts of Discord auth that are most annoying to hand-roll: authorization URLs, callback parsing, code exchange, refresh, revocation, and a few common identity lookups.

## What it is good for

- Bot installation links.
- Sign-in with Discord flows.
- Refreshable user sessions.
- Token inspection and revocation.
- Guild, connection, and application lookups.

## Configuration

`OAuth2Config` keeps the transport details in one place:

- `client_id`, `client_secret`, and `redirect_uri` are required.
- `api_version` and `base_url` let you target a different Discord API host if needed.
- `authorize_url` can be overridden for mirrored or mock environments.
- `proxy`, `proxy_auth`, and `timeout` are available for network control.
- `user_agent` defaults to a VaidCord-branded value if you do not set one.

## Build authorization URLs

`OAuth2Client.build_authorization_url(...)` supports the common Discord knobs:

- `scope`
- `state`
- `prompt`
- `integration_type`
- `permissions`
- `guild_id`
- `disable_guild_select`

Example:

```python
from vaidcord.oauth2 import (
    IntegrationType,
    OAuth2Client,
    OAuth2Config,
    OAuth2Scope,
    PromptType,
)

config = OAuth2Config(
    client_id="123",
    client_secret="secret",
    redirect_uri="https://example.com/callback",
)
client = OAuth2Client(config)
state = client.generate_state()

url = client.build_authorization_url(
    scope=[OAuth2Scope.IDENTIFY, OAuth2Scope.GUILDS, OAuth2Scope.BOT],
    state=state,
    prompt=PromptType.CONSENT,
    integration_type=IntegrationType.GUILD_INSTALL,
    guild_id="123456789012345678",
    disable_guild_select=True,
)
```

## Handle the redirect

`parse_redirect_url(...)` understands both styles that Discord can send back:

- Query parameters for authorization code flow.
- Fragment parameters for implicit flow.

That makes it easy to turn a callback URL into a dictionary of values before you exchange the code or inspect the response.

## Exchange, refresh, and revoke

- `exchange_code(code, redirect_uri=None)` exchanges an authorization code for an `OAuth2Token`.
- `refresh_access_token(refresh_token)` refreshes a token using the refresh grant.
- `get_client_credentials_token(scope=None)` gets an app-only token.
- `revoke_token(token, token_type_hint=None)` revokes access or refresh tokens.
- `ensure_valid_token()` returns the current token and refreshes it automatically when possible.

`OAuth2Token` tracks expiry for you through `is_expired` and `expires_in_seconds`.

## Inspect Discord identity data

Use the bearer token helpers when you want to inspect the current session:

- `get_current_authorization(access_token)` returns the auth payload.
- `get_current_user(access_token)` fetches the user identity.
- `get_user_connections(access_token)` lists linked connections.
- `get_user_guilds(access_token)` lists guilds the user can see.
- `get_bot_application_info(access_token)` fetches the app info endpoint.

## A practical flow

1. Create a client from `OAuth2Config`.
2. Build an authorization URL with a state value.
3. Send the user to Discord.
4. Parse the callback with `parse_redirect_url(...)`.
5. Exchange the code for a token.
6. Refresh or revoke the token when the session changes.

## Example files

- [examples/oauth2_examples.py](../examples/oauth2_examples.py) - the smallest authorization URL example.
- [examples/oauth2_workflow.py](../examples/oauth2_workflow.py) - a richer install-link and token-helper example.
