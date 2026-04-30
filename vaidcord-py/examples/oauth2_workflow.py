"""OAuth2 helper example showing install links and token helpers."""

from __future__ import annotations

from vaidcord.oauth2 import (
    IntegrationType,
    OAuth2Client,
    OAuth2Config,
    OAuth2Scope,
    OAuth2Token,
    PromptType,
)


def build_install_url() -> str:
    config = OAuth2Config(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        redirect_uri="https://example.com/callback",
    )
    client = OAuth2Client(config)
    state = client.generate_state()
    return client.build_authorization_url(
        scope=[OAuth2Scope.IDENTIFY, OAuth2Scope.GUILDS, OAuth2Scope.BOT],
        state=state,
        prompt=PromptType.CONSENT,
        integration_type=IntegrationType.GUILD_INSTALL,
        guild_id="123456789012345678",
        disable_guild_select=True,
    )


def parse_callback_url(url: str) -> dict[str, str]:
    config = OAuth2Config(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        redirect_uri="https://example.com/callback",
    )
    client = OAuth2Client(config)
    return client.parse_redirect_url(url)


def preview_token_lifetime() -> tuple[bool, int]:
    token = OAuth2Token(access_token="demo", token_type="Bearer", expires_in=3600)
    return token.is_expired, token.expires_in_seconds


if __name__ == "__main__":
    print("Install URL:", build_install_url())
    print(
        "Parsed callback:",
        parse_callback_url("https://example.com/callback?code=demo&state=abc"),
    )
    print("Token lifetime:", preview_token_lifetime())
