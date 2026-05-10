"""Benchmark for the model layer parsing hot path (issue #26).

Compares throughput of ``Bot._parse_message`` / ``Bot._parse_event`` between
the legacy "copy raw_data" mode and the new "share raw_data" / "drop
raw_data" modes introduced for issue #26.

Run with::

    uv run python benchmarks/model_parse.py --iterations 50000

The script prints a small JSON report with throughput numbers and the
relative speed-up of the new modes against the legacy copy mode.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vaidcord.bot import Bot, BotConfig  # noqa: E402
from vaidcord.types import EventType  # noqa: E402

# Representative MESSAGE_CREATE payload modeled after a real Discord event.
SAMPLE_MESSAGE = {
    "id": "1331984829234876521",
    "channel_id": "987654321098765432",
    "guild_id": "112233445566778899",
    "content": "Benchmark payload — keep this realistic enough to exercise the parser.",
    "timestamp": "2026-05-10T12:00:00.000+00:00",
    "edited_timestamp": None,
    "tts": False,
    "mention_everyone": False,
    "mentions": [
        {"id": "999", "username": "alice", "discriminator": "0", "global_name": "Alice", "bot": False},
        {"id": "888", "username": "bob", "discriminator": "0", "global_name": "Bob", "bot": False},
    ],
    "mention_roles": ["123", "456"],
    "mention_channels": [],
    "attachments": [],
    "embeds": [],
    "reactions": [],
    "pinned": False,
    "type": 0,
    "author": {
        "id": "777",
        "username": "carol",
        "discriminator": "0",
        "global_name": "Carol",
        "bot": False,
    },
    "components": [],
    "flags": 0,
}


def _make_bot(*, keep_raw_data: bool, share_raw_data: bool) -> Bot:
    config = BotConfig(
        token="benchmark",
        keep_raw_data=keep_raw_data,
        share_raw_data=share_raw_data,
    )
    return Bot(config=config)


async def _bench(*, iterations: int, keep_raw_data: bool, share_raw_data: bool) -> dict[str, float | int]:
    bot = _make_bot(keep_raw_data=keep_raw_data, share_raw_data=share_raw_data)

    # Warm-up so JIT/dataclass init costs don't pollute the timing.
    for _ in range(min(iterations // 10, 1000) or 1):
        await bot._parse_event(EventType.MESSAGE_CREATE, dict(SAMPLE_MESSAGE))
        bot._parse_user(SAMPLE_MESSAGE["author"])
        bot._parse_message(SAMPLE_MESSAGE)

    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    for _ in range(iterations):
        # Each iteration mimics a fresh json.loads dict.
        payload = dict(SAMPLE_MESSAGE)
        await bot._parse_event(EventType.MESSAGE_CREATE, payload)
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    gc.collect()

    return {
        "mode": _mode_name(keep_raw_data=keep_raw_data, share_raw_data=share_raw_data),
        "iterations": iterations,
        "elapsed_seconds": round(elapsed, 6),
        "events_per_second": round(iterations / elapsed, 2) if elapsed else 0,
        "peak_traced_bytes": peak,
    }


def _mode_name(*, keep_raw_data: bool, share_raw_data: bool) -> str:
    if not keep_raw_data:
        return "no-raw"
    return "share-raw" if share_raw_data else "copy-raw"


async def main(iterations: int) -> None:
    results = []
    # Run legacy copy mode first so its allocations don't influence later
    # tracemalloc snapshots.
    for keep_raw, share_raw in (
        (True, False),   # legacy
        (True, True),    # new default
        (False, False),  # opt-out entirely
    ):
        results.append(await _bench(
            iterations=iterations,
            keep_raw_data=keep_raw,
            share_raw_data=share_raw,
        ))

    base = next(r for r in results if r["mode"] == "copy-raw")
    for r in results:
        r["speedup_vs_copy_raw"] = (
            round(r["events_per_second"] / base["events_per_second"], 3)
            if base["events_per_second"]
            else 0
        )
        r["alloc_ratio_vs_copy_raw"] = (
            round(r["peak_traced_bytes"] / base["peak_traced_bytes"], 3)
            if base["peak_traced_bytes"]
            else 0
        )

    print(json.dumps(results, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=20_000)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args().iterations))
