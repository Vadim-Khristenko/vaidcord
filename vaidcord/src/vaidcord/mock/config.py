from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MockSettings:
    """Runtime tuning for mock subsystem behavior."""

    auto_ready_event: bool = True
    default_http_status: int = 200
    default_rate_limit: int = 5
    network_delay: float = 0.0
