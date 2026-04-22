"""
VaidCord - High-performance Discord framework inspired by Aiogram 3.x architecture.

This package provides a modern, type-safe, and performant way to build Discord bots
with full support for Python 3.12+.
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "VaidCord Team"

from .bot import Bot
from .router import Router
from .types import Event, Message, User, Guild, Channel
from .dispatcher import Dispatcher
from .formatting import Formatter

__all__ = [
    "Bot",
    "Router",
    "Dispatcher",
    "Event",
    "Message",
    "User",
    "Guild",
    "Channel",
    "Formatter",
    "__version__",
]
