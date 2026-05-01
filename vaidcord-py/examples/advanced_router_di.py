"""Advanced router, DI, middleware, and gateway-event shortcut example."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from time import perf_counter

from vaidcord import Bot, Dispatcher, Router, configure_logging
from vaidcord.bot import GatewayIntent
from vaidcord.filters import CommandFilter, F
from vaidcord.types import Event

NextHandler = Callable[[Event], Awaitable[object]]
logger = logging.getLogger("vaidcord.examples.advanced")


class SupportService:
    def __init__(self, queue_name: str) -> None:
        self.queue_name = queue_name

    async def status_text(self) -> str:
        return f"{self.queue_name} queue is online"


feature_router = Router(name="feature")
public_router = Router(name="public")
admin_router = Router(name="admin")

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
    logger.info("Feature router is ready")


@feature_router.on_shutdown()
async def on_shutdown() -> None:
    logger.info("Feature router is shutting down")


@public_router.on_ready()
async def ready(bot: Bot) -> None:
    logger.info("Ready handler sees bot_id=%s", bot.id)


@public_router.on_message_create(CommandFilter(("start",)))
async def start(event: Event, bot: Bot, service: SupportService) -> None:
    await bot.reply(
        event.message.channel_id,
        event.message.id,
        f"Welcome. {await service.status_text()}. Try /help.",
        mention_author=False,
    )


@public_router.on_message_create(CommandFilter(("help",)))
async def help_command(event: Event, bot: Bot) -> None:
    await bot.send_message(
        event.message.channel_id,
        "Try /start, /echo hello, /poll, or /stats.",
    )


@public_router.on_message_create(F.message.content.startswith("/echo"))
async def echo(event: Event, bot: Bot) -> None:
    _, _, payload = event.message.content.partition(" ")
    await bot.send_message(event.message.channel_id, payload or "Usage: /echo your text")


@public_router.on_private_message()
async def dm_only(event: Event, bot: Bot) -> None:
    await bot.send_message(event.message.channel_id, "This handler only sees direct messages.")


@public_router.on_message_create(CommandFilter(("poll",)))
async def send_poll(event: Event, bot: Bot) -> None:
    await bot.send_poll(
        event.message.channel_id,
        question="Which feature should be expanded next?",
        answers=["FSM", "Filters", "Gateway events"],
        duration_hours=24,
    )


@public_router.on_message_poll_vote_add()
async def poll_vote(event: Event) -> None:
    logger.info("Poll vote event received", extra={"event": event})


@public_router.on_guild_member_add()
async def member_join(event: Event, bot: Bot) -> None:
    if event.user is not None:
        logger.info("New member joined: %s", event.user.id, extra={"event": event})


@admin_router.on_message_create(CommandFilter(("stats",)))
async def stats(
    event: Event,
    bot: Bot,
    admin_label: str,
    service: SupportService,
) -> None:
    await bot.reply(
        event.message.channel_id,
        event.message.id,
        f"{admin_label} {await service.status_text()}; trace context is attached.",
        mention_author=False,
    )


feature_router.include_routers(public_router, admin_router)


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.provide("service", SupportService("support"))
    dispatcher.include_router(feature_router)
    return dispatcher


async def main() -> None:
    configure_logging()
    intents = (
        GatewayIntent.default()
        | GatewayIntent.MESSAGE_CONTENT
        | GatewayIntent.GUILD_MESSAGE_POLLS
    )
    if os.environ.get("VAIDCORD_ENABLE_GUILD_MEMBERS_INTENT") == "1":
        intents |= GatewayIntent.GUILD_MEMBERS

    bot = Bot(
        token=os.environ["DISCORD_BOT_TOKEN"],
        intents=int(intents),
    )
    dispatcher = build_dispatcher()

    await dispatcher.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
