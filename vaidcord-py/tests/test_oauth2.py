"""
Tests for OAuth2 module.

Covers:
- Authorization URL generation
- Token management
- State parameter generation
- Redirect URL parsing
- OAuth2 flows (mocked)
"""

from __future__ import annotations

import pytest

from vaidcord.oauth2 import (
    IntegrationType,
    OAuth2Client,
    OAuth2Config,
    OAuth2Error,
    OAuth2Scope,
    OAuth2Token,
    PromptType,
    UserAuthClient,
)


class TestOAuth2Config:
    """Test OAuth2 configuration."""

    def test_config_creation(self):
        """Test basic config creation."""
        config = OAuth2Config(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="https://example.com/callback",
        )

        assert config.client_id == "test_client_id"
        assert config.client_secret == "test_client_secret"
        assert config.redirect_uri == "https://example.com/callback"
        assert config.api_version == "10"
        assert config.base_url == "https://discord.com/api"

    def test_config_urls(self):
        """Test URL generation from config."""
        config = OAuth2Config(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="https://example.com/callback",
        )

        assert "oauth2/token" in config.token_url
        assert "oauth2/token/revoke" in config.revoke_url
        assert "oauth2/applications/@me" in config.app_info_url
        assert "oauth2/@me" in config.auth_info_url

    def test_custom_base_url(self):
        """Test custom base URL for self-hosted mirrors."""
        config = OAuth2Config(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="https://example.com/callback",
            base_url="https://custom-discord.example.com/api",
        )

        assert config.base_url == "https://custom-discord.example.com/api"
        assert config.token_url.startswith("https://custom-discord.example.com/api")


class TestOAuth2Token:
    """Test OAuth2 token management."""

    def test_token_creation(self):
        """Test basic token creation."""
        token = OAuth2Token(
            access_token="test_access_token",
            token_type="Bearer",
            expires_in=604800,
            refresh_token="test_refresh_token",
            scope=["identify", "guilds"],
        )

        assert token.access_token == "test_access_token"
        assert token.token_type == "Bearer"
        assert token.expires_in == 604800
        assert token.refresh_token == "test_refresh_token"
        assert "identify" in token.scope
        assert "guilds" in token.scope

    def test_token_expiration(self):
        """Test token expiration detection."""
        # Create token that expires in 1 hour
        token = OAuth2Token(
            access_token="test_access_token",
            token_type="Bearer",
            expires_in=3600,
        )

        assert not token.is_expired
        assert token.expires_in_seconds > 3500

    def test_token_from_dict(self):
        """Test creating token from dictionary."""
        data = {
            "access_token": "test_token",
            "token_type": "Bearer",
            "expires_in": 604800,
            "refresh_token": "test_refresh",
            "scope": "identify guilds",
        }

        token = OAuth2Token.from_dict(data)

        assert token.access_token == "test_token"
        assert token.scope == ["identify", "guilds"]

    def test_token_to_dict(self):
        """Test converting token to dictionary."""
        token = OAuth2Token(
            access_token="test_token",
            token_type="Bearer",
            expires_in=604800,
        )

        data = token.to_dict()

        assert data["access_token"] == "test_token"
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 604800


class TestOAuth2Client:
    """Test OAuth2 client functionality."""

    @pytest.fixture
    def oauth_config(self):
        """Create OAuth2 config for testing."""
        return OAuth2Config(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="https://example.com/callback",
        )

    @pytest.fixture
    def oauth_client(self, oauth_config):
        """Create OAuth2 client for testing."""
        return OAuth2Client(oauth_config)

    def test_state_generation(self, oauth_client):
        """Test secure state parameter generation."""
        state1 = oauth_client.generate_state()
        state2 = oauth_client.generate_state()

        # States should be unique
        assert state1 != state2

        # States should have reasonable length
        assert len(state1) >= 32

        # States should be URL-safe
        assert state1.replace("-", "").replace("_", "").isalnum()

    def test_build_authorization_url_basic(self, oauth_client):
        """Test building basic authorization URL."""
        url = oauth_client.build_authorization_url(
            response_type="code",
            scope=[OAuth2Scope.IDENTIFY, OAuth2Scope.GUILDS],
        )

        assert "discord.com/oauth2/authorize" in url
        assert "response_type=code" in url
        assert "client_id=test_client_id" in url
        assert "redirect_uri=https%3A%2F%2Fexample.com%2Fcallback" in url
        assert "scope=identify+guilds" in url or "scope=identify%20guilds" in url

    def test_build_authorization_url_with_state(self, oauth_client):
        """Test building authorization URL with custom state."""
        custom_state = "my_custom_state_123"
        url = oauth_client.build_authorization_url(
            response_type="code",
            state=custom_state,
        )

        assert f"state={custom_state}" in url

    def test_build_authorization_url_bot(self, oauth_client):
        """Test building bot authorization URL."""
        url = oauth_client.build_authorization_url(
            response_type="code",
            scope=[OAuth2Scope.BOT],
            permissions=8,  # Administrator permission
            guild_id="123456789",
        )

        assert "permissions=8" in url
        assert "guild_id=123456789" in url

    def test_build_authorization_url_implicit_grant(self, oauth_client):
        """Test building implicit grant authorization URL."""
        url = oauth_client.build_authorization_url(
            response_type="token",
            scope=[OAuth2Scope.IDENTIFY],
        )

        assert "response_type=token" in url

    def test_parse_redirect_url_query(self, oauth_client):
        """Test parsing redirect URL with query parameters."""
        url = "https://example.com/callback?code=abc123&state=xyz789"
        params = oauth_client.parse_redirect_url(url)

        assert params.get("code") == "abc123"
        assert params.get("state") == "xyz789"

    def test_parse_redirect_url_fragment(self, oauth_client):
        """Test parsing redirect URL with fragment (implicit grant)."""
        url = "https://example.com/callback#access_token=token123&token_type=Bearer&expires_in=604800"
        params = oauth_client.parse_redirect_url(url)

        assert params.get("access_token") == "token123"
        assert params.get("token_type") == "Bearer"
        assert params.get("expires_in") == "604800"

    def test_basic_auth_header(self, oauth_client):
        """Test Basic authentication header generation."""
        auth_header = oauth_client._get_basic_auth()

        assert auth_header.startswith("Basic ")
        # Should contain base64-encoded client_id:client_secret
        import base64

        encoded = auth_header.split(" ")[1]
        decoded = base64.b64decode(encoded).decode()
        assert decoded == "test_client_id:test_client_secret"


class TestUserAuthClient:
    """Test user authentication client."""

    @pytest.fixture
    def user_auth_config(self):
        """Create OAuth2 config for user auth testing."""
        return OAuth2Config(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="https://example.com/callback",
            base_url="https://mock-discord.example.com/api",
        )

    def test_user_auth_client_creation(self, user_auth_config):
        """Test creating UserAuthClient."""
        client = UserAuthClient(
            config=user_auth_config,
            username="test_user",
            password="test_password",
        )

        assert client.username == "test_user"
        assert client.password == "test_password"

    def test_user_auth_inherits_oauth2(self, user_auth_config):
        """Test that UserAuthClient inherits OAuth2Client functionality."""
        client = UserAuthClient(config=user_auth_config)

        # Should have all OAuth2Client methods
        assert hasattr(client, "build_authorization_url")
        assert hasattr(client, "exchange_code")
        assert hasattr(client, "refresh_access_token")
        assert hasattr(client, "generate_state")


class TestOAuth2Error:
    """Test OAuth2 error handling."""

    def test_error_creation(self):
        """Test creating OAuth2 error."""
        error = OAuth2Error(
            status=400,
            code=50035,
            message="Invalid Form Body",
        )

        assert error.status == 400
        assert error.code == 50035
        assert error.message == "Invalid Form Body"
        assert "400" in str(error)
        assert "50035" in str(error)

    def test_error_to_dict(self):
        """Test converting error to dictionary."""
        error = OAuth2Error(
            status=401,
            code=40001,
            message="Unauthorized",
        )

        data = error.to_dict()

        assert data["status"] == 401
        assert data["code"] == 40001
        assert data["message"] == "Unauthorized"


class TestIntegrationTypes:
    """Test integration type enums."""

    def test_integration_type_values(self):
        """Test integration type enum values."""
        assert IntegrationType.GUILD_INSTALL.value == 0
        assert IntegrationType.USER_INSTALL.value == 1

    def test_prompt_type_values(self):
        """Test prompt type enum values."""
        assert PromptType.CONSENT.value == "consent"
        assert PromptType.NONE.value == "none"


class TestOAuth2Scopes:
    """Test OAuth2 scope enums."""

    def test_common_scopes(self):
        """Test common OAuth2 scopes."""
        assert OAuth2Scope.IDENTIFY.value == "identify"
        assert OAuth2Scope.GUILDS.value == "guilds"
        assert OAuth2Scope.BOT.value == "bot"
        assert OAuth2Scope.EMAIL.value == "email"
        assert OAuth2Scope.WEBHOOK_INCOMING.value == "webhook.incoming"

    def test_scope_iteration(self):
        """Test iterating over all scopes."""
        scopes = list(OAuth2Scope)
        assert len(scopes) > 0
        assert OAuth2Scope.IDENTIFY in scopes
        assert OAuth2Scope.BOT in scopes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
