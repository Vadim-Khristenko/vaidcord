"""Discord-accurate snowflake generation for the mock server.

Snowflakes encode a millisecond timestamp (relative to the Discord epoch),
a worker id, a process id, and a per-process increment::

    63                                          22    17    12          0
    +-------------------------------------------+-----+-----+-----------+
    | milliseconds since Discord epoch          | wid | pid | increment |
    +-------------------------------------------+-----+-----+-----------+

This lets tests assert real timestamp semantics (``snowflake_time``) and
guarantees strictly increasing ids even when many are minted in the same
millisecond.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

DISCORD_EPOCH_MS = 1_420_070_400_000
"""First second of 2015 in unix milliseconds — Discord's snowflake epoch."""


class SnowflakeGenerator:
    """Mint monotonically increasing, timestamp-encoding snowflakes."""

    def __init__(self, *, worker_id: int = 1, process_id: int = 1) -> None:
        self._worker_id = worker_id & 0x1F
        self._process_id = process_id & 0x1F
        self._increment = 0
        self._last_id = 0
        self._lock = threading.Lock()

    def generate(self) -> int:
        """Return the next snowflake as an integer."""
        with self._lock:
            timestamp_ms = int(time.time() * 1000) - DISCORD_EPOCH_MS
            self._increment = (self._increment + 1) & 0xFFF
            snowflake = (
                (timestamp_ms << 22)
                | (self._worker_id << 17)
                | (self._process_id << 12)
                | self._increment
            )
            # Guard against clock skew / same-ms wraparound: ids must only grow.
            if snowflake <= self._last_id:
                snowflake = self._last_id + 1
            self._last_id = snowflake
            return snowflake

    def generate_str(self) -> str:
        """Return the next snowflake as the string Discord APIs use."""
        return str(self.generate())


def snowflake_time(snowflake: int | str) -> datetime:
    """Decode the creation time embedded in a snowflake."""
    value = int(snowflake)
    timestamp_ms = (value >> 22) + DISCORD_EPOCH_MS
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
