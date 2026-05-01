"""Showcase of class-based filters, MagicFilter, MagicData, and BotFilter."""

from __future__ import annotations

import asyncio
import os

from vaidcord import Bot, Dispatcher, Router
from vaidcord.filters import BotFilter, ChatTypeFilter, CommandFilter, F, MagicData
from vaidcord.types import ChannelType, Event


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(maintenance_mode=False)
    router = Router(name="filters-showcase")

    router.add_filter(MagicData(F.maintenance_mode.is_(False)))

    @router.on_message(CommandFilter(("start",)))
    async def start(event: Event, bot: Bot) -> None:
        await bot.send_message(event.message.channel_id, "Filter showcase is active")

    @router.on_message(ChatTypeFilter([ChannelType.DM, "group_dm"]))
    async def dm_hint(event: Event, bot: Bot) -> None:
        await bot.send_message(event.message.channel_id, "You are in DM/group_dm")

    @router.on_message(BotFilter(bot_ids={1, 2, 3}) | F.bot.bot_username_in({"main_bot"}))
    async def multi_bot_gate(event: Event, bot: Bot) -> None:
        await bot.send_message(event.message.channel_id, f"Handled by bot identity gate: {getattr(bot, 'id', None)}")

    @router.on_message(F.message.content.regex(r"^/set\s+(?P<name>\w+)$"))
    async def regex_payload(event: Event, bot: Bot, regex_groups: dict[str, str]) -> None:
        await bot.send_message(event.message.channel_id, f"Parsed name: {regex_groups.get('name')}")

    dp.include_router(router)
    return dp


async def main() -> None:
    bot = Bot(token=os.environ["DISCORD_BOT_TOKEN"])
    dp = build_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
