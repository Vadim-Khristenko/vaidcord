"""
OAuth2 Module for VaidCord.

Implements Discord's OAuth2 authentication flows:
- Authorization Code Grant
- Implicit Grant
- Client Credentials Grant
- Bot Authorization
- Webhook Authorization

Supports:
- User authentication (for self-hosted mirrors and mock servers)
- Bot authentication
- Token refresh and revocation
- Custom OAuth2 endpoints
"""

from __future__ import annotations

import asyncio
import base64
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp


class OAuth2Scope(str, Enum):
    """OAuth2 scopes supported by Discord."""

    ACTIVITIES_READ = "activities.read"
    ACTIVITIES_WRITE = "activities.write"
    APPLICATIONS_BUILDS_READ = "applications.builds.read"
    APPLICATIONS_BUILDS_UPLOAD = "applications.builds.upload"
    APPLICATIONS_COMMANDS = "applications.commands"
    APPLICATIONS_COMMANDS_UPDATE = "applications.commands.update"
    APPLICATIONS_COMMANDS_PERMISSIONS_UPDATE = (
        "applications.commands.permissions.update"
    )
    APPLICATIONS_ENTITLEMENTS = "applications.entitlements"
    APPLICATIONS_STORE_UPDATE = "applications.store.update"
    BOT = "bot"
    CONNECTIONS = "connections"
    DM_CHANNELS_READ = "dm_channels.read"
    EMAIL = "email"
    GDM_JOIN = "gdm.join"
    GUILDS = "guilds"
    GUILDS_JOIN = "guilds.join"
    GUILDS_MEMBERS_READ = "guilds.members.read"
    IDENTIFY = "identify"
    MESSAGES_READ = "messages.read"
    RELATIONSHIPS_READ = "relationships.read"
    ROLE_CONNECTIONS_WRITE = "role_connections.write"
    RPC = "rpc"
    RPC_ACTIVITIES_WRITE = "rpc.activities.write"
    RPC_NOTIFICATIONS_READ = "rpc.notifications.read"
    RPC_VOICE_READ = "rpc.voice.read"
    RPC_VOICE_WRITE = "rpc.voice.write"
    VOICE = "voice"
    WEBHOOK_INCOMING = "webhook.incoming"


class OAuth2GrantType(str, Enum):
    """OAuth2 grant types."""

    AUTHORIZATION_CODE = "authorization_code"
    REFRESH_TOKEN = "refresh_token"
    CLIENT_CREDENTIALS = "client_credentials"


class IntegrationType(int, Enum):
    """Integration type for OAuth2 authorization."""

    GUILD_INSTALL = 0
    USER_INSTALL = 1


class PromptType(str, Enum):
    """Prompt types for OAuth2 authorization."""

    CONSENT = "consent"
    NONE = "none"


@dataclass
class OAuth2Token:
    """Represents an OAuth2 access token."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None = None
    scope: list[str] = field(default_factory=list)
    webhook: dict[str, Any] | None = None
    guild: dict[str, Any] | None = None
    user: dict[str, Any] | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.expires_in and not self.expires_at:
            self.expires_at = datetime.now() + timedelta(seconds=self.expires_in)

    @property
    def is_expired(self) -> bool:
        """Check if the token is expired."""
        if self.expires_at is None:
            return False
        return datetime.now() >= self.expires_at

    @property
    def expires_in_seconds(self) -> int:
        """Get seconds until expiration."""
        if self.expires_at is None:
            return 0
        delta = self.expires_at - datetime.now()
        return max(0, int(delta.total_seconds()))

    def to_dict(self) -> dict[str, Any]:
        """Convert token to dictionary."""
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
            "webhook": self.webhook,
            "guild": self.guild,
            "user": self.user,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OAuth2Token:
        """Create OAuth2Token from dictionary."""
        return cls(
            access_token=data["access_token"],
            token_type=data["token_type"],
            expires_in=data["expires_in"],
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope", "").split(),
            webhook=data.get("webhook"),
            guild=data.get("guild"),
            user=data.get("user"),
        )


@dataclass
class OAuth2Config:
    """Configuration for OAuth2 client."""

    client_id: str
    client_secret: str
    redirect_uri: str
    api_version: str = "10"
    base_url: str = "https://discord.com/api"
    authorize_url: str = "https://discord.com/oauth2/authorize"
    proxy: str | None = None
    proxy_auth: aiohttp.BasicAuth | None = None
    timeout: float = 30.0
    user_agent: str | None = None

    def __post_init__(self) -> None:
        if self.user_agent is None:
            self.user_agent = "DiscordBot (https://github.com/vaidcord/vaidcord, 0.1.0)"

    @property
    def token_url(self) -> str:
        """Get token endpoint URL."""
        return f"{self.base_url}/v{self.api_version}/oauth2/token"

    @property
    def revoke_url(self) -> str:
        """Get token revocation endpoint URL."""
        return f"{self.base_url}/v{self.api_version}/oauth2/token/revoke"

    @property
    def app_info_url(self) -> str:
        """Get application info endpoint URL."""
        return f"{self.base_url}/v{self.api_version}/oauth2/applications/@me"

    @property
    def auth_info_url(self) -> str:
        """Get authorization info endpoint URL."""
        return f"{self.base_url}/v{self.api_version}/oauth2/@me"


@dataclass
class AuthorizationURLParams:
    """Parameters for building authorization URL."""

    response_type: Literal["code", "token"]
    client_id: str
    redirect_uri: str
    scope: list[OAuth2Scope] = field(default_factory=list)
    state: str | None = None
    prompt: PromptType | None = None
    integration_type: IntegrationType | None = None
    permissions: int | None = None
    guild_id: str | None = None
    disable_guild_select: bool = False

    def to_query_string(self) -> str:
        """Convert parameters to query string."""
        params: dict[str, str] = {
            "response_type": self.response_type,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }

        if self.scope:
            params["scope"] = " ".join(s.value for s in self.scope)

        if self.state:
            params["state"] = self.state

        if self.prompt:
            params["prompt"] = self.prompt.value

        if self.integration_type is not None:
            params["integration_type"] = str(self.integration_type.value)

        if self.permissions is not None:
            params["permissions"] = str(self.permissions)

        if self.guild_id:
            params["guild_id"] = self.guild_id

        if self.disable_guild_select:
            params["disable_guild_select"] = "true"

        return urlencode(params)


class OAuth2Client:
    """
    OAuth2 client for Discord authentication.

    Supports all OAuth2 flows:
    - Authorization Code Grant (standard OAuth2)
    - Implicit Grant (browser-based)
    - Client Credentials Grant (testing)
    - Bot Authorization
    - Webhook Authorization

    Features:
    - Automatic token refresh
    - State parameter for CSRF protection
    - Support for custom OAuth2 endpoints (self-hosted mirrors)
    - User authentication support (for mock servers)
    """

    def __init__(self, config: OAuth2Config) -> None:
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._current_token: OAuth2Token | None = None
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {
                "User-Agent": self.config.user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
            }
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            )
        return self._session

    async def close(self) -> None:
        """Close the OAuth2 client session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def generate_state(self, length: int = 32) -> str:
        """
        Generate a secure random state parameter for CSRF protection.

        Args:
            length: Length of the state string

        Returns:
            Secure random state string
        """
        return secrets.token_urlsafe(length)

    def build_authorization_url(
        self,
        response_type: Literal["code", "token"] = "code",
        scope: list[OAuth2Scope] | None = None,
        state: str | None = None,
        prompt: PromptType | None = None,
        integration_type: IntegrationType | None = None,
        permissions: int | None = None,
        guild_id: str | None = None,
        disable_guild_select: bool = False,
    ) -> str:
        """
        Build OAuth2 authorization URL.

        Args:
            response_type: 'code' for authorization code grant, 'token' for implicit grant
            scope: List of OAuth2 scopes to request
            state: State parameter for CSRF protection (auto-generated if None)
            prompt: Whether to prompt user for consent
            integration_type: Installation context (guild or user)
            permissions: Bot permissions (for bot authorization)
            guild_id: Pre-select guild for bot authorization
            disable_guild_select: Prevent user from changing guild selection

        Returns:
            Complete authorization URL
        """
        if state is None:
            state = self.generate_state()

        params = AuthorizationURLParams(
            response_type=response_type,
            client_id=self.config.client_id,
            redirect_uri=self.config.redirect_uri,
            scope=scope or [],
            state=state,
            prompt=prompt,
            integration_type=integration_type,
            permissions=permissions,
            guild_id=guild_id,
            disable_guild_select=disable_guild_select,
        )

        query_string = params.to_query_string()
        return f"{self.config.authorize_url}?{query_string}"

    def _get_basic_auth(self) -> str:
        """Get Basic authentication header value."""
        credentials = f"{self.config.client_id}:{self.config.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    async def exchange_code(
        self, code: str, redirect_uri: str | None = None
    ) -> OAuth2Token:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from redirect
            redirect_uri: Redirect URI (must match authorization request)

        Returns:
            OAuth2Token with access and refresh tokens
        """
        session = await self._get_session()
        redirect_uri = redirect_uri or self.config.redirect_uri

        data = {
            "grant_type": OAuth2GrantType.AUTHORIZATION_CODE.value,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        headers = {"Authorization": self._get_basic_auth()}

        async with session.post(
            self.config.token_url,
            data=data,
            headers=headers,
            proxy=self.config.proxy,
        ) as response:
            if response.status != 200:
                error_data = await response.json()
                raise OAuth2Error(
                    status=response.status,
                    code=error_data.get("code", 0),
                    message=error_data.get("message", "Unknown error"),
                )

            token_data = await response.json()
            token = OAuth2Token.from_dict(token_data)
            self._current_token = token
            return token

    async def refresh_access_token(self, refresh_token: str) -> OAuth2Token:
        """
        Refresh an access token using a refresh token.

        Args:
            refresh_token: Refresh token from previous authorization

        Returns:
            New OAuth2Token with fresh access token
        """
        session = await self._get_session()

        data = {
            "grant_type": OAuth2GrantType.REFRESH_TOKEN.value,
            "refresh_token": refresh_token,
        }

        headers = {"Authorization": self._get_basic_auth()}

        async with session.post(
            self.config.token_url,
            data=data,
            headers=headers,
            proxy=self.config.proxy,
        ) as response:
            if response.status != 200:
                error_data = await response.json()
                raise OAuth2Error(
                    status=response.status,
                    code=error_data.get("code", 0),
                    message=error_data.get("message", "Unknown error"),
                )

            token_data = await response.json()
            token = OAuth2Token.from_dict(token_data)
            self._current_token = token
            return token

    async def get_client_credentials_token(
        self, scope: list[OAuth2Scope] | None = None
    ) -> OAuth2Token:
        """
        Get access token using client credentials grant.

        This is useful for testing and bot-only operations.

        Args:
            scope: List of scopes to request

        Returns:
            OAuth2Token with access token (no refresh token)
        """
        session = await self._get_session()

        data = {
            "grant_type": OAuth2GrantType.CLIENT_CREDENTIALS.value,
        }

        if scope:
            data["scope"] = " ".join(s.value for s in scope)

        headers = {"Authorization": self._get_basic_auth()}

        async with session.post(
            self.config.token_url,
            data=data,
            headers=headers,
            proxy=self.config.proxy,
        ) as response:
            if response.status != 200:
                error_data = await response.json()
                raise OAuth2Error(
                    status=response.status,
                    code=error_data.get("code", 0),
                    message=error_data.get("message", "Unknown error"),
                )

            token_data = await response.json()
            token = OAuth2Token.from_dict(token_data)
            self._current_token = token
            return token

    async def revoke_token(
        self,
        token: str,
        token_type_hint: Literal["access_token", "refresh_token"] | None = None,
    ) -> None:
        """
        Revoke an access or refresh token.

        Note: Revoking a token will revoke all associated tokens.

        Args:
            token: Token to revoke
            token_type_hint: Type of token being revoked
        """
        session = await self._get_session()

        data = {"token": token}
        if token_type_hint:
            data["token_type_hint"] = token_type_hint

        headers = {"Authorization": self._get_basic_auth()}

        async with session.post(
            self.config.revoke_url,
            data=data,
            headers=headers,
            proxy=self.config.proxy,
        ) as response:
            if response.status != 200:
                error_data = await response.json()
                raise OAuth2Error(
                    status=response.status,
                    code=error_data.get("code", 0),
                    message=error_data.get("message", "Unknown error"),
                )

    async def get_current_authorization(self, access_token: str) -> dict[str, Any]:
        """
        Get information about the current authorization.

        Args:
            access_token: Bearer token for authentication

        Returns:
            Authorization information including application, scopes, and user
        """
        session = await self._get_session()

        headers = {"Authorization": f"Bearer {access_token}"}

        async with session.get(
            self.config.auth_info_url,
            headers=headers,
            proxy=self.config.proxy,
        ) as response:
            if response.status != 200:
                error_data = await response.json()
                raise OAuth2Error(
                    status=response.status,
                    code=error_data.get("code", 0),
                    message=error_data.get("message", "Unknown error"),
                )

            return await response.json()

    async def get_bot_application_info(self, access_token: str) -> dict[str, Any]:
        """
        Get bot application information.

        Args:
            access_token: Bearer token for authentication

        Returns:
            Application information
        """
        session = await self._get_session()

        headers = {"Authorization": f"Bearer {access_token}"}

        async with session.get(
            self.config.app_info_url,
            headers=headers,
            proxy=self.config.proxy,
        ) as response:
            if response.status != 200:
                error_data = await response.json()
                raise OAuth2Error(
                    status=response.status,
                    code=error_data.get("code", 0),
                    message=error_data.get("message", "Unknown error"),
                )

            return await response.json()

    async def ensure_valid_token(self) -> OAuth2Token | None:
        """
        Ensure the current token is valid, refreshing if necessary.

        Returns:
            Valid OAuth2Token or None if no token available
        """
        async with self._lock:
            if self._current_token is None:
                return None

            if self._current_token.is_expired and self._current_token.refresh_token:
                try:
                    return await self.refresh_access_token(
                        self._current_token.refresh_token
                    )
                except OAuth2Error:
                    self._current_token = None
                    return None

            return self._current_token

    @property
    def current_token(self) -> OAuth2Token | None:
        """Get the current token."""
        return self._current_token

    def parse_redirect_url(self, url: str) -> dict[str, str]:
        """
        Parse OAuth2 redirect URL to extract parameters.

        Handles both query parameters (authorization code) and
        fragment parameters (implicit grant).

        Args:
            url: Redirect URL from OAuth2 flow

        Returns:
            Dictionary of extracted parameters
        """
        parsed = urlparse(url)

        # Check for fragment (implicit grant)
        if parsed.fragment:
            params = {}
            for param in parsed.fragment.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = value
            return params

        # Query parameters (authorization code grant)
        return {k: v[0] for k, v in parse_qs(parsed.query).items()}

    def __repr__(self) -> str:
        return f"<OAuth2Client client_id={self.config.client_id}>"


class OAuth2Error(Exception):
    """Exception raised for OAuth2 errors."""

    def __init__(
        self,
        status: int,
        code: int,
        message: str,
    ) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(f"[{status}] {code}: {message}")

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary."""
        return {
            "status": self.status,
            "code": self.code,
            "message": self.message,
        }


class UserAuthClient(OAuth2Client):
    """
    Extended OAuth2 client for user authentication.

    This class provides additional functionality for authenticating
    as a Discord user (for self-hosted mirrors and mock servers).

    WARNING: Using this to automate user accounts violates Discord's
    Terms of Service on the official platform. Only use with:
    - Self-hosted Discord server mirrors
    - Mock/testing servers
    - Explicit user consent via proper OAuth2 flow
    """

    def __init__(
        self,
        config: OAuth2Config,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        super().__init__(config)
        self.username = username
        self.password = password

    async def login_with_credentials(
        self, username: str, password: str, mfa_code: str | None = None
    ) -> OAuth2Token:
        """
        Login with username and password (for self-hosted/mock servers only).

        WARNING: This bypasses normal OAuth2 flow and should ONLY be used
        with self-hosted Discord mirrors or mock servers. Using this on
        the official Discord API violates ToS.

        Args:
            username: User's email or username
            password: User's password
            mfa_code: 2FA code if enabled

        Returns:
            OAuth2Token with user's access token
        """
        session = await self._get_session()

        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
        }

        if mfa_code:
            data["mfa_code"] = mfa_code

        headers = {
            "Authorization": self._get_basic_auth(),
        }

        async with session.post(
            self.config.token_url,
            data=data,
            headers=headers,
            proxy=self.config.proxy,
        ) as response:
            if response.status != 200:
                error_data = await response.json()
                raise OAuth2Error(
                    status=response.status,
                    code=error_data.get("code", 0),
                    message=error_data.get("message", "Unknown error"),
                )

            token_data = await response.json()
            token = OAuth2Token.from_dict(token_data)
            self._current_token = token
            return token

    async def get_user_connections(self, access_token: str) -> list[dict[str, Any]]:
        """
        Get user's connected third-party accounts.

        Requires 'connections' scope.

        Args:
            access_token: User's access token

        Returns:
            List of connected accounts
        """
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {access_token}"}

        url = f"{self.config.base_url}/v{self.config.api_version}/users/@me/connections"

        async with session.get(
            url,
            headers=headers,
            proxy=self.config.proxy,
        ) as response:
            if response.status != 200:
                error_data = await response.json()
                raise OAuth2Error(
                    status=response.status,
                    code=error_data.get("code", 0),
                    message=error_data.get("message", "Unknown error"),
                )

            return await response.json()

    async def get_user_guilds(
        self,
        access_token: str,
        limit: int = 100,
        before: str | None = None,
        after: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get user's guilds.

        Requires 'guilds' scope.

        Args:
            access_token: User's access token
            limit: Maximum number of guilds to return
            before: Get guilds before this ID
            after: Get guilds after this ID

        Returns:
            List of guild objects
        """
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {access_token}"}

        params = {"limit": str(limit)}
        if before:
            params["before"] = before
        if after:
            params["after"] = after

        url = f"{self.config.base_url}/v{self.config.api_version}/users/@me/guilds"

        async with session.get(
            url,
            headers=headers,
            params=params,
            proxy=self.config.proxy,
        ) as response:
            if response.status != 200:
                error_data = await response.json()
                raise OAuth2Error(
                    status=response.status,
                    code=error_data.get("code", 0),
                    message=error_data.get("message", "Unknown error"),
                )

            return await response.json()

    async def get_current_user(self, access_token: str) -> dict[str, Any]:
        """
        Get current user's information.

        Requires 'identify' scope (and 'email' for email address).

        Args:
            access_token: User's access token

        Returns:
            User object
        """
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {access_token}"}

        url = f"{self.config.base_url}/v{self.config.api_version}/users/@me"

        async with session.get(
            url,
            headers=headers,
            proxy=self.config.proxy,
        ) as response:
            if response.status != 200:
                error_data = await response.json()
                raise OAuth2Error(
                    status=response.status,
                    code=error_data.get("code", 0),
                    message=error_data.get("message", "Unknown error"),
                )

            return await response.json()
