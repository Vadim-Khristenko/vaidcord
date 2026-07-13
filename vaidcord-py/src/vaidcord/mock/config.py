from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MockSettings:
    """Runtime tuning for mock subsystem behavior."""

    auto_ready_event: bool = True
    default_http_status: int = 200
    default_rate_limit: int = 5
    network_delay: float = 0.0


@dataclass
class MockServerConfig:
    """Behavioral configuration for :class:`vaidcord.mock.MockDiscordServer`.

    Everything here is also adjustable at runtime through the control plane
    (``/api/mock/chaos``, ``/api/mock/ratelimit``, ``/api/mock/permissions``),
    so tests can flip simulation features mid-scenario without restarting.
    """

    # --- gateway -----------------------------------------------------------
    heartbeat_interval_ms: int = 41_250
    """Heartbeat interval advertised in the gateway HELLO payload."""

    event_buffer_size: int = 256
    """Per-session ring buffer of dispatched events kept for RESUME replay."""

    # --- request validation ------------------------------------------------
    strict_validation: bool = True
    """Return Discord-shaped 400 errors (50006, 50035, 50109) for bad input."""

    # --- permissions -------------------------------------------------------
    enforce_permissions: bool = False
    """When enabled, channels marked as denied return 403 Missing Access."""

    # --- rate limiting -----------------------------------------------------
    rate_limit_enabled: bool = False
    """Opt-in per-route + global rate-limit simulation with real headers."""

    rate_limit_per_route: int = 5
    """Requests allowed per route bucket within ``rate_limit_window``."""

    rate_limit_window: float = 5.0
    """Length of a per-route bucket window in seconds."""

    global_rate_limit: int = 50
    """Requests allowed across all ``/api/v10`` routes per global window."""

    global_rate_limit_window: float = 1.0
    """Length of the global window in seconds."""

    # --- chaos injection ---------------------------------------------------
    chaos_latency_ms: float = 0.0
    """Fixed latency added to every ``/api/v10`` request."""

    chaos_jitter_ms: float = 0.0
    """Additional random latency in ``[0, jitter]`` milliseconds."""

    chaos_error_rate: float = 0.0
    """Probability in ``[0, 1]`` that a ``/api/v10`` request fails."""

    chaos_error_status: int = 500
    """HTTP status used for injected chaos errors."""

    chaos_error_code: int = 0
    """Discord error ``code`` field used for injected chaos errors."""
