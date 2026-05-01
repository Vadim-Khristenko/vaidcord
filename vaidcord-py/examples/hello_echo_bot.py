"""Minimal runnable bot on the Dispatcher + Router architecture."""

from __future__ import annotations

import asyncio
import os

from vaidcord import Bot, Dispatcher, Formatter, Router, configure_logging
from vaidcord.bot import GatewayIntent
from vaidcord.filters import CommandFilter, F
from vaidcord.types import Event

router = Router(name="hello")


@router.on_ready()
async def ready(bot: Bot) -> None:
    user = bot.user or await bot.get_current_user()
    print(f"Logged in as {user.username} ({user.id})")


@router.on_message_create(CommandFilter(("start",)))
async def start(event: Event, bot: Bot) -> None:
    await bot.reply(
        channel_id=event.message.channel_id,
        message_id=event.message.id,
        content=Formatter.bold("Hello from VaidCord!"),
        mention_author=False,
    )


@router.on_message_create(
    F.message.content.exists()
    & F.message.content.not_in({"/start"})
    & ~F.message.content.startswith("/")
)
async def echo(event: Event, bot: Bot) -> None:
    await bot.send_message(
        event.message.channel_id,
        f"echo: {event.message.content}",
    )


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def main() -> None:
    configure_logging()
    bot = Bot(
        token=os.environ["DISCORD_BOT_TOKEN"],
        intents=int(GatewayIntent.default() | GatewayIntent.MESSAGE_CONTENT),
    )
    dispatcher = build_dispatcher()

    await dispatcher.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
