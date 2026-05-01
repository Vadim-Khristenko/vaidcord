"""FSM conversation example showing a small multi-step profile flow."""

from __future__ import annotations

import asyncio
import os

from vaidcord import (
    Bot,
    Dispatcher,
    MemoryFSMStorage,
    Router,
    State,
    StatesGroup,
    configure_logging,
)
from vaidcord.filters import CommandFilter
from vaidcord.fsm import FSMContext
from vaidcord.types import Message


class Profile(StatesGroup):
    ask_name = State()
    ask_language = State()


profile_router = Router(name="profile")


@profile_router.on_message_create(CommandFilter(("profile",)))
async def start_profile(message: Message, fsm: FSMContext) -> None:
    await fsm.set_state(Profile.ask_name)
    await fsm.set_data({"user_id": message.author_id})
    await message.reply(
        "What name should I remember for you?",
        mention_author=False,
    )


@profile_router.on_message_state(Profile.ask_name)
async def capture_name(message: Message, fsm: FSMContext) -> None:
    await fsm.update_data(name=message.content.strip())
    await fsm.set_state(Profile.ask_language)
    await message.answer("What language do you use most?")


@profile_router.on_message_state(Profile.ask_language)
async def capture_language(message: Message, fsm: FSMContext) -> None:
    data = await fsm.get_data()
    name = data.get("name", "anonymous")
    language = message.content.strip()
    await message.answer(f"Saved profile: {name} prefers {language}.")
    await fsm.clear()


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryFSMStorage())
    dispatcher.include_router(profile_router)
    return dispatcher


async def main() -> None:
    configure_logging()
    bot = Bot(token=os.environ["DISCORD_BOT_TOKEN"])
    dispatcher = build_dispatcher()

    await dispatcher.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
