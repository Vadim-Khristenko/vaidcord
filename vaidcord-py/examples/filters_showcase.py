"""Showcase of class-based filters, MagicFilter, MagicData, and BotFilter."""

from __future__ import annotations

import asyncio
import os

from vaidcord import Bot, Dispatcher, Router, configure_logging
from vaidcord.filters import BotFilter, ChatTypeFilter, CommandFilter, F, MagicData
from vaidcord.types import ChannelType, Message, TypingStart

router = Router(name="filters-showcase")
router.add_filter(MagicData(F.maintenance_mode.is_(False)))


@router.on_message_create(CommandFilter(("start",)))
async def start(message: Message) -> None:
    await message.answer("Filter showcase is active")


@router.on_message_create(ChatTypeFilter([ChannelType.DM, "group_dm"]))
async def dm_hint(message: Message) -> None:
    await message.answer("You are in DM/group_dm")


@router.on_message_create(BotFilter(bot_ids={1, 2, 3}) | F.bot.bot_username_in({"main_bot"}))
async def multi_bot_gate(message: Message, bot: Bot) -> None:
    await message.answer(f"Handled by bot identity gate: {getattr(bot, 'id', None)}")


@router.on_message_create(F.message.content.regex(r"^/set\s+(?P<name>\w+)$"))
async def regex_payload(message: Message, regex_groups: dict[str, str]) -> None:
    await message.answer(f"Parsed name: {regex_groups.get('name')}")


@router.on_typing_start()
async def typing_started(typing: TypingStart) -> None:
    print(f"user {typing.user_id} is typing in {typing.channel_id}")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.provide("maintenance_mode", False)
    dp.include_router(router)
    return dp


async def main() -> None:
    configure_logging()
    bot = Bot(token=os.environ["DISCORD_BOT_TOKEN"])
    dp = build_dispatcher()
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
