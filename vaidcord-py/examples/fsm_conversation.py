"""FSM conversation example showing a small multi-step profile flow."""

from __future__ import annotations

import asyncio
import os

from vaidcord import Bot, Dispatcher, MemoryFSMStorage, Router
from vaidcord.filters import CommandFilter
from vaidcord.types import Event

PROFILE_ASK_NAME = "profile:ask_name"
PROFILE_ASK_LANGUAGE = "profile:ask_language"


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryFSMStorage())
    profile_router = Router(name="profile")

    @profile_router.on_message(CommandFilter(("profile",)))
    async def start_profile(event: Event, bot: Bot) -> None:
        fsm = event.context["fsm"]
        await fsm.set_state(PROFILE_ASK_NAME)
        await fsm.set_data({"user_id": event.user.id if event.user else None})
        await bot.reply(
            event.message.channel_id,
            event.message.id,
            "What name should I remember for you?",
        )

    @profile_router.on_message_state(PROFILE_ASK_NAME)
    async def capture_name(event: Event, bot: Bot) -> None:
        fsm = event.context["fsm"]
        await fsm.update_data(name=event.message.content.strip())
        await fsm.set_state(PROFILE_ASK_LANGUAGE)
        await bot.send_message(
            event.message.channel_id,
            "What language do you use most?",
        )

    @profile_router.on_message_state(PROFILE_ASK_LANGUAGE)
    async def capture_language(event: Event, bot: Bot) -> None:
        fsm = event.context["fsm"]
        data = await fsm.get_data()
        name = data.get("name", "anonymous")
        language = event.message.content.strip()
        await bot.send_message(
            event.message.channel_id,
            f"Saved profile: {name} prefers {language}.",
        )
        await fsm.clear()

    dispatcher.include_router(profile_router)
    return dispatcher


async def main() -> None:
    bot = Bot(token=os.environ["DISCORD_BOT_TOKEN"])
    dispatcher = build_dispatcher()

    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
