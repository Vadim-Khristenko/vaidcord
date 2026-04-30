"""OAuth2 usage examples for VaidCord (English version)."""

from __future__ import annotations

from vaidcord.oauth2 import OAuth2Client, OAuth2Config, OAuth2Scope


def build_authorize_url() -> str:
    config = OAuth2Config(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        redirect_uri="https://example.com/callback",
    )
    client = OAuth2Client(config)
    return client.get_authorization_url(scopes=[OAuth2Scope.IDENTIFY, OAuth2Scope.GUILDS])


if __name__ == "__main__":
    print(build_authorize_url())
