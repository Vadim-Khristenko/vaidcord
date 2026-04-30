from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vaidcord.types import EventType


@dataclass
class MockEvent:
    event_type: EventType
    data: dict[str, Any]
    delay: float = 0.0


@dataclass
class MockHTTPResponse:
    status: int = 200
    data: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    error_code: int | None = None
    error_message: str | None = None
    delay: float = 0.0
