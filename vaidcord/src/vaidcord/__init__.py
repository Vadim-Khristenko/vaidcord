"""
VaidCord - High-performance Discord framework inspired by Aiogram 3.x architecture.

This package provides a modern, type-safe, and performant way to build Discord bots
with full support for Python 3.12+.
"""

from __future__ import annotations

__version__ = "0.1.0"
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
    "Bot",
    "Router",
    "Event",
    "Message",
    "User",
    "Guild",
    "Channel",
    "Formatter",
    "__version__",
]
