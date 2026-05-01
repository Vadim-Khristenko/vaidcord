"""Bot example with explicit Gateway intents and permission notes."""

from __future__ import annotations

import asyncio
import logging
import os

from vaidcord import Bot, Dispatcher, Router, configure_logging
from vaidcord.bot import GatewayIntent
from vaidcord.filters import CommandFilter
from vaidcord.permissions import Permissions
from vaidcord.types import Event, Message

logger = logging.getLogger("vaidcord.examples.permissions")
router = Router(name="intents-permissions")

TEXT_PERMISSIONS = (
    Permissions.VIEW_CHANNEL
    | Permissions.SEND_MESSAGES
    | Permissions.READ_MESSAGE_HISTORY
    | Permissions.EMBED_LINKS
)


@router.on_ready()
async def ready(bot: Bot) -> None:
    user = bot.user or await bot.get_current_user()
    logger.info(
        "Logged in as %s (%s). Suggested invite permission integer: %s",
        user.username,
        user.id,
        int(TEXT_PERMISSIONS),
    )


@router.on_message_create(CommandFilter(("permissions",)))
async def permissions_hint(message: Message) -> None:
    await message.answer(
        "Required in this channel: View Channel, Send Messages, Read Message History, "
        "Embed Links. Guild text commands also require MESSAGE_CONTENT intent.",
    )


@router.on_guild_member_add()
async def member_joined(event: Event) -> None:
    logger.info("Guild member event received: %s", event.data.get("user", {}).get("id"))


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


def build_intents() -> int:
    intents = GatewayIntent.default() | GatewayIntent.MESSAGE_CONTENT
    if os.environ.get("VAIDCORD_ENABLE_GUILD_MEMBERS_INTENT") == "1":
        intents |= GatewayIntent.GUILD_MEMBERS
    return int(intents)


async def main() -> None:
    configure_logging()
    bot = Bot(token=os.environ["DISCORD_BOT_TOKEN"], intents=build_intents())
    dispatcher = build_dispatcher()
    await dispatcher.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
