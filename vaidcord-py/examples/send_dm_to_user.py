"""Send a DM to a user by ID.

Usage:
  DISCORD_BOT_TOKEN=... uv run python examples/send_dm_to_user.py 123456789012345678 "Hello!"
"""

from __future__ import annotations

import asyncio
import os
import sys

from vaidcord.bot import Bot


async def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python examples/send_dm_to_user.py <user_id> <message>")
        raise SystemExit(1)

    user_id = int(sys.argv[1])
    content = sys.argv[2]

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set DISCORD_BOT_TOKEN environment variable before running this example")

    bot = Bot(token=token)
    try:
        message = await bot.send_dm(user_id=user_id, content=content)
        print(f"DM sent: message_id={message.id} channel_id={message.channel.id}")
    finally:
        await bot.api_client.close()


if __name__ == "__main__":
    asyncio.run(main())
