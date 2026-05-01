"""Create Discord polls and handle poll vote gateway events."""

from __future__ import annotations

import asyncio
import logging
import os

from vaidcord import Bot, Dispatcher, Router, configure_logging
from vaidcord.bot import GatewayIntent
from vaidcord.filters import CommandFilter
from vaidcord.types import Message, PollVote

logger = logging.getLogger("vaidcord.examples.polls")
router = Router(name="polls")


@router.on_message_create(CommandFilter(("poll",)))
async def create_poll(message: Message, bot: Bot) -> None:
    poll_message = await bot.send_poll(
        channel_id=message.channel_id,
        content="Vote below.",
        question="What should we improve next?",
        answers=["Typed events", "Mock UI", "Docs"],
        duration_hours=24,
        allow_multiselect=False,
    )
    await message.reply(
        f"Poll created: {poll_message['id']}",
        mention_author=False,
    )


@router.on_message_poll_vote_add()
async def on_poll_vote(vote: PollVote, bot: Bot) -> None:
    voters = await bot.get_poll_answer_voters(
        vote.channel_id,
        vote.message_id,
        vote.answer_id,
        limit=25,
    )
    logger.info(
        "Poll vote: user=%s message=%s answer=%s voters_seen=%s",
        vote.user_id,
        vote.message_id,
        vote.answer_id,
        len(voters),
    )


@router.on_message_create(CommandFilter(("endpoll",)))
async def end_poll(message: Message, bot: Bot) -> None:
    _, _, raw_message_id = message.content.partition(" ")
    if not raw_message_id.strip().isdigit():
        await message.reply("Usage: /endpoll <message_id>", mention_author=False)
        return
    ended = await bot.end_poll(message.channel_id, int(raw_message_id))
    await message.reply(f"Ended poll message {ended.id}.", mention_author=False)


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def main() -> None:
    configure_logging()
    intents = (
        GatewayIntent.default()
        | GatewayIntent.MESSAGE_CONTENT
        | GatewayIntent.GUILD_MESSAGE_POLLS
        | GatewayIntent.DIRECT_MESSAGE_POLLS
    )
    bot = Bot(token=os.environ["DISCORD_BOT_TOKEN"], intents=int(intents))
    dispatcher = build_dispatcher()
    await dispatcher.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
