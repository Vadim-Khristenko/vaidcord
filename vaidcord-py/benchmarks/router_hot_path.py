from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vaidcord.filters import F
from vaidcord.router import Router
from vaidcord.types import Channel, ChannelType, Event, EventType, Message, User


def make_event(content: str = "!bench payload") -> Event:
    user = User(id=100, username="bench")
    channel = Channel(id=200, type=ChannelType.TEXT)
    message = Message(
        id=300,
        channel=channel,
        author=user,
        content=content,
        timestamp=datetime.now(),
    )
    return Event(
        type=EventType.MESSAGE_CREATE,
        data={"user_id": str(user.id), "channel_id": str(channel.id), "guild_id": "500"},
        message=message,
        user=user,
        channel=channel,
    )


def build_router(filters: int, middlewares: int) -> Router:
    router = Router(name="hot-path-benchmark")

    for index in range(middlewares):

        @router.middleware(priority=index)
        async def middleware(event: Event, handler: Any) -> Any:
            event.context["middleware_hits"] = event.context.get("middleware_hits", 0) + 1
            return await handler(event)

    predicates = tuple(F.message.content.startswith("!bench") for _ in range(filters))

    @router.on_message(*predicates)
    async def handler(message: Message) -> str:
        return message.content

    return router


async def run(events: int, filters: int, middlewares: int) -> dict[str, float | int]:
    router = build_router(filters=filters, middlewares=middlewares)
    event = make_event()

    await router.propagate_event(event)

    started = time.perf_counter()
    for _ in range(events):
        event.context.clear()
        await router.propagate_event(event)
    elapsed = time.perf_counter() - started

    return {
        "events": events,
        "filters": filters,
        "middlewares": middlewares,
        "elapsed_seconds": round(elapsed, 6),
        "events_per_second": round(events / elapsed, 2) if elapsed else 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=10_000)
    parser.add_argument("--filters", type=int, default=10)
    parser.add_argument("--middlewares", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(run(args.events, args.filters, args.middlewares))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
