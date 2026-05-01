"""Minimal runnable hello-world + echo bot example."""

from __future__ import annotations

import os

from vaidcord import Bot, Formatter
from vaidcord.filters import CommandFilter, F

bot = Bot(token=os.environ["DISCORD_BOT_TOKEN"])


@bot.on_message(CommandFilter(("start",)))
async def start(event):
    await bot.reply(
        channel_id=event.message.channel_id,
        message_id=event.message.id,
        content=Formatter.bold("Hello from VaidCord!"),
    )


@bot.on_message(F.message.content.exists() & F.message.content.not_in({"/start"}) & ~F.message.content.startswith("/"))
async def echo(event):
    await bot.send_message(event.message.channel_id, f"echo: {event.message.content}")

if __name__ == "__main__":
    bot.run()
