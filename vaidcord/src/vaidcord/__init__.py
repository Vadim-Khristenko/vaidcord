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
"""

from __future__ import annotations

__version__ = "0.2.0"
__author__ = "VaidCord Team"

# Lazy imports to avoid circular dependency issues
__lazy_imports__ = {
    "Bot": ".bot",
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
    "__version__",
]
