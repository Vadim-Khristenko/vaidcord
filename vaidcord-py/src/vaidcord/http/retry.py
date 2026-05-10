"""Retry policy used by the HTTP transport.

The :class:`RetryPolicy` is intentionally tiny: it answers "should this
attempt retry?" and "how long should we wait before the next attempt?".
That keeps tuning policies (linear vs exponential backoff, jitter, max
retries) out of the transport's hot path.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RetryPolicy:
    """Exponential-backoff retry policy."""

    max_retries: int = 3
    base_delay: float = 1.0

    def should_retry(self, *, attempt: int, status: int | None = None) -> bool:
        """Return True if another attempt is allowed.

        ``attempt`` is the 1-based attempt number that just failed.
        """
        if attempt >= self.max_retries:
            return False
        if status is not None and status < 500:
            return False
        return True

    def delay_for(self, attempt: int) -> float:
        """Return the delay in seconds before retrying after ``attempt`` failed."""
        return self.base_delay * (2 ** max(0, attempt - 1))


__all__ = ["RetryPolicy"]
