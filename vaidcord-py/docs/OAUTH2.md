# OAuth2 in VaidCord

This document describes OAuth2 helpers provided by the Python SDK.

## Supported flows

- Authorization Code
- Implicit
- Client Credentials
- Bot authorization
- Incoming webhook authorization

## Quick start

```python
from vaidcord.oauth2 import OAuth2Client, OAuth2Config, OAuth2Scope

config = OAuth2Config(
    client_id="123",
    client_secret="secret",
    redirect_uri="https://example.com/callback",
)
client = OAuth2Client(config)

url = client.get_authorization_url(scopes=[OAuth2Scope.IDENTIFY])
print(url)
```

For runnable examples see `examples/oauth2_examples.py`.
