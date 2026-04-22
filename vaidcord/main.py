"""
Example bot using VaidCord framework.

This demonstrates the basic usage of VaidCord's router system and formatting utilities.
"""

from __future__ import annotations

import asyncio
import os

from vaidcord import Bot, Event, Formatter, Router

# Create the main bot instance
bot = Bot(token=os.getenv("DISCORD_TOKEN", "YOUR_TOKEN_HERE"))

# Create a separate router for commands
commands_router = Router(name="commands")


@commands_router.on_message()
async def handle_ping(event: Event) -> None:
    """Handle ping command."""
    if event.message and event.message.content.lower() == "!ping":
        response = Formatter.bold("Pong!") + " 🏓"
        print(response)
        # In real usage: await event.message.channel.send(response)


@commands_router.on_message()
async def handle_help(event: Event) -> None:
    """Handle help command."""
    if event.message and event.message.content.lower() == "!help":
        help_text = Formatter.combine_styles(
            "VaidCord Bot Help",
            Formatter.bold,  # type: ignore[arg-type]
        )
        help_text += "\n\n"
        help_text += Formatter.bold("Commands:") + "\n"
        help_text += Formatter.inline_code("!ping") + " - Check bot latency\n"
        help_text += Formatter.inline_code("!help") + " - Show this help message\n"
        help_text += "\n"
        help_text += Formatter.code_block(
            "# Example code block\nprint('Hello from VaidCord!')",
            "python",
        )
        print(help_text)


@bot.on_event("READY")
async def on_ready(event: Event) -> None:
    """Handle bot ready event."""
    print(f"{Formatter.bold('Bot is ready!')} Logged in as {bot.user}")


# Include the commands router in the bot
bot.include_router(commands_router)


async def main() -> None:
    """Main entry point."""
    print(f"Starting {Formatter.bold('VaidCord')} bot...")
    print(f"Formatting example: {Formatter.bold('Bold')} {Formatter.italic('Italic')}")

    # In production, you would run the bot with:
    # bot.run()

    # For demo purposes, we'll just show the structure
    from vaidcord.types import EventType

    print("\nBot handlers registered:")
    print(f"  - {len(bot.get_handlers(EventType.MESSAGE_CREATE))} message handlers")
    print(f"  - {len(commands_router.get_handlers(EventType.MESSAGE_CREATE))} command handlers")

    print("\nTo run the bot, set DISCORD_TOKEN environment variable and call bot.run()")


if __name__ == "__main__":
    asyncio.run(main())
