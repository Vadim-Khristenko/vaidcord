"""Package metadata helpers."""

from __future__ import annotations

import platform
from importlib import metadata

__author__ = "VaidCord Team"
LIBRARY_NAME = "vaidcord"
PROJECT_URL = "https://github.com/Vadim-Khristenko/vaidcord"


def _package_version() -> str:
    try:
        return metadata.version(LIBRARY_NAME)
    except metadata.PackageNotFoundError:
        return "0.1.0b4"


__version__ = _package_version()


def build_user_agent() -> str:
    """Build a Discord-friendly user agent with runtime metadata."""
    python_version = platform.python_version()
    return f"DiscordBot ({PROJECT_URL}, {__version__}) {LIBRARY_NAME}/{__version__} Python/{python_version}"
