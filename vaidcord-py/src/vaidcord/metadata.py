"""Package metadata helpers."""

from __future__ import annotations

import platform

__version__ = "0.1.0"
__author__ = "VaidCord Team"
LIBRARY_NAME = "vaidcord"
PROJECT_URL = "https://github.com/vaidcord/vaidcord"


def build_user_agent() -> str:
    """Build a Discord-friendly user agent with runtime metadata."""
    python_version = platform.python_version()
    return f"DiscordBot ({PROJECT_URL}, {__version__}) {LIBRARY_NAME}/{__version__} Python/{python_version}"
