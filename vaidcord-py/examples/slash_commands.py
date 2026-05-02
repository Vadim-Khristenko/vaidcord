from __future__ import annotations

import os

from vaidcord import Bot, BotConfig, GatewayIntent


bot = Bot(
    config=BotConfig(
        token=os.getenv("DISCORD_BOT_TOKEN") or "",
        intents=GatewayIntent.default(),
        command_dev_guild_id=1499484508611936439 # 123456789012345678,  # fast dev sync
    )
)


@bot.slash_command(
    name="echo",
    description="Echo text back",
    options=[
        {"name": "text", "description": "Message text", "type": 3, "required": True},
        {"name": "times", "description": "Repeat count", "type": 4, "required": False},
    ],
)
async def echo(ctx) -> None:
    text = ctx.require_str("text")
    times = ctx.option_int("times", 1) or 1
    # interaction response is intentionally explicit
    await bot.create_interaction_response(
        int(ctx["id"]),
        ctx["token"],
        type=4,
        data={"content": "\n".join(text for _ in range(max(1, min(times, 5))))},
    )


if __name__ == "__main__":
    bot.run()
