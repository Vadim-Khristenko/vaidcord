"""Minimal runnable hello-world + echo bot example."""

from __future__ import annotations

import os

from vaidcord import Bot, Formatter

bot = Bot(token=os.environ["DISCORD_BOT_TOKEN"])


@bot.on_command_start()
async def start(event):
    await bot.reply(
        channel_id=event.message.channel_id,
        message_id=event.message.id,
        content=Formatter.bold("Hello from VaidCord!"),
    )


@bot.on_message()
async def echo(event):
    if not event.message.content.startswith("/"):
        await bot.send_message(event.message.channel_id, f"echo: {event.message.content}")


if __name__ == "__main__":
    bot.run()
