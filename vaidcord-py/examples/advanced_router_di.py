"""Advanced router, DI, and middleware example for VaidCord.

This script shows how to organize a bot into nested routers, share dependencies
through the router tree, and keep cross-cutting logic in middleware.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from time import perf_counter

from vaidcord import Bot, Dispatcher, Router
from vaidcord.filters import CommandFilter, F
from vaidcord.types import Event

NextHandler = Callable[[Event], Awaitable[object]]


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()

    feature_router = Router(name="feature")
    public_router = Router(name="public")
    admin_router = Router(name="admin")

    feature_router.provide("service_name", "support")
    admin_router.provide("admin_label", "[ADMIN]")

    @feature_router.outer_middleware(priority=100)
    async def trace_runtime(event: Event, handler: NextHandler) -> object:
        started_at = perf_counter()
        event.context["trace_started_at"] = started_at
        result = await handler(event)
        event.context["trace_elapsed_ms"] = round(
            (perf_counter() - started_at) * 1000,
            2,
        )
        return result

    @feature_router.on_startup()
    async def on_startup() -> None:
        print("Feature router is ready")

    @feature_router.on_shutdown()
    async def on_shutdown() -> None:
        print("Feature router is shutting down")

    @public_router.on_message(CommandFilter(("start",)))
    async def start(event: Event, bot: Bot, service_name: str) -> None:
        await bot.reply(
            event.message.channel_id,
            event.message.id,
            f"Welcome to {service_name}. Try /help for more.",
        )

    @public_router.on_message(CommandFilter(("help",)))
    async def help_command(event: Event, bot: Bot) -> None:
        await bot.send_message(
            event.message.channel_id,
            "Try /start, /echo hello, or /stats in the admin router.",
        )

    @public_router.on_message(F.message.content.startswith("/echo"))
    async def echo(event: Event, bot: Bot) -> None:
        _, _, payload = event.message.content.partition(" ")
        await bot.send_message(event.message.channel_id, payload or "Usage: /echo your text")

    @public_router.on_private_message()
    async def dm_only(event: Event, bot: Bot) -> None:
        await bot.send_message(event.message.channel_id, "This handler only sees direct messages.")

    @admin_router.on_message(CommandFilter(("stats",)))
    async def stats(event: Event, bot: Bot, admin_label: str, service_name: str) -> None:
        await bot.reply(
            event.message.channel_id,
            event.message.id,
            f"{admin_label} {service_name} is running; trace context is attached in event.context.",
        )

    feature_router.include_routers(public_router, admin_router)
    dispatcher.include_router(feature_router)
    return dispatcher


async def main() -> None:
    bot = Bot(token=os.environ["DISCORD_BOT_TOKEN"])
    dispatcher = build_dispatcher()

    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
