"""
VaidCord - High-performance Discord framework inspired by Aiogram 3.x architecture.

This package provides a modern, type-safe, and performant way to build Discord bots
with full support for Python 3.12+.

Features:
- Modern async/await API
- Type-safe event handling
- Comprehensive formatting utilities
- HTTP client with proxy support
- Advanced mocking for testing
- Custom API endpoints
- Full OAuth2 support with user authentication
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "VaidCord Team"

# Lazy imports to avoid circular dependency issues
__lazy_imports__ = {
    "Bot": ".bot",
    "BotState": ".bot",
    "Router": ".router",
    "Event": ".types",
    "Message": ".types",
    "User": ".types",
    "Guild": ".types",
    "Channel": ".types",
    "Formatter": ".formatting",
    "HTTPClient": ".http",
    "HTTPConfig": ".http",
    "DiscordError": ".http",
    "MockBot": ".mock",
    "MockGateway": ".mock",
    "MockHTTPClient": ".mock",
    "create_mock_message": ".mock",
    "create_mock_event": ".mock",
    # OAuth2
    "OAuth2Client": ".oauth2",
    "UserAuthClient": ".oauth2",
    "OAuth2Config": ".oauth2",
    "OAuth2Token": ".oauth2",
    "OAuth2Scope": ".oauth2",
    "OAuth2Error": ".oauth2",
    "IntegrationType": ".oauth2",
    "PromptType": ".oauth2",
    # Errors
    "VaidCordError": ".errors",
    "DiscordAPIError": ".errors",
    "GatewayError": ".errors",
    "VoiceGatewayError": ".errors",
    "RateLimitError": ".errors",
    "AuthenticationError": ".errors",
    "ForbiddenError": ".errors",
    "NotFoundError": ".errors",
    "ValidationError": ".errors",
    "MissingPermissions": ".errors",
    "HierarchyError": ".errors",
    "GatewayOpcode": ".errors",
    "GatewayCloseCode": ".errors",
    "VoiceGatewayOpcode": ".errors",
    "VoiceGatewayCloseCode": ".errors",
    "DiscordErrorCode": ".errors",
    "create_discord_error": ".errors",
    "create_gateway_error": ".errors",
    "create_voice_gateway_error": ".errors",
    # Permissions
    "Permissions": ".permissions",
    "PermissionOverwrite": ".permissions",
    "PermissionCalculator": ".permissions",
    "calculate_permissions": ".permissions",
    "check_permission": ".permissions",
}


def __getattr__(name: str):
    if name in __lazy_imports__:
        import importlib

        module_path = __lazy_imports__[name]
        module = importlib.import_module(module_path, package="vaidcord")
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Core
    "Bot",
    "Router",
    "BotState",
    # Types
    "Event",
    "Message",
    "User",
    "Guild",
    "Channel",
    # Formatting
    "Formatter",
    # HTTP
    "HTTPClient",
    "HTTPConfig",
    "DiscordError",
    # Mocking
    "MockBot",
    "MockGateway",
    "MockHTTPClient",
    "create_mock_message",
    "create_mock_event",
    # OAuth2
    "OAuth2Client",
    "UserAuthClient",
    "OAuth2Config",
    "OAuth2Token",
    "OAuth2Scope",
    "OAuth2Error",
    "IntegrationType",
    "PromptType",
    # Errors
    "VaidCordError",
    "DiscordAPIError",
    "GatewayError",
    "VoiceGatewayError",
    "RateLimitError",
    "AuthenticationError",
    "ForbiddenError",
    "NotFoundError",
    "ValidationError",
    "MissingPermissions",
    "HierarchyError",
    "GatewayOpcode",
    "GatewayCloseCode",
    "VoiceGatewayOpcode",
    "VoiceGatewayCloseCode",
    "DiscordErrorCode",
    "create_discord_error",
    "create_gateway_error",
    "create_voice_gateway_error",
    # Permissions
    "Permissions",
    "PermissionOverwrite",
    "PermissionCalculator",
    "calculate_permissions",
    "check_permission",
    # Version
    "__version__",
]
