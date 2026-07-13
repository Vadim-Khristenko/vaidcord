"""Play music into a voice channel and record every speaker to .wav files.

Demonstrates the full voice media pipeline:

* ``connection.play()`` with :class:`FFmpegPCMAudio` (any file/URL) and
  :class:`PCMVolumeTransformer` for live volume control;
* ``connection.listen()`` with :class:`WaveSink` for per-user recording;
* speaking callbacks and graceful disconnect.

Requirements: ``libopus`` + ``ffmpeg`` installed system-wide and
``pip install 'vaidcord[voice]'``.

Run:

    DISCORD_BOT_TOKEN=... \
    VAIDCORD_VOICE_GUILD_ID=... \
    VAIDCORD_VOICE_CHANNEL_ID=... \
    python examples/voice_play_and_record.py path/to/song.mp3
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from vaidcord import Bot, GatewayIntent, configure_logging
from vaidcord.voice import (
    FFmpegPCMAudio,
    PCMVolumeTransformer,
    WaveSink,
    check_voice_dependencies,
)

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Set DISCORD_BOT_TOKEN before running this example")

GUILD_ID = int(os.getenv("VAIDCORD_VOICE_GUILD_ID", "0"))
CHANNEL_ID = int(os.getenv("VAIDCORD_VOICE_CHANNEL_ID", "0"))
AUDIO_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "examples/assets/Anamanaguchi_Miku-Ft_Hatsune_Miku.mp3"
)

logger = logging.getLogger("vaidcord.examples.voice_play_and_record")

bot = Bot(
    token=TOKEN,
    intents=int(GatewayIntent.GUILDS | GatewayIntent.GUILD_VOICE_STATES),
)


async def play_and_record() -> None:
    status = check_voice_dependencies()
    logger.info(
        "voice deps: ffmpeg=%s libopus=%s pynacl=%s cryptography=%s",
        status.ffmpeg,
        status.libopus,
        status.pynacl,
        status.cryptography,
    )
    status.raise_for_playback()

    if not await bot.wait_until_ready(wait_timeout=30):
        raise TimeoutError("Bot did not become READY in 30 seconds")

    connection = await bot.join_voice_channel(GUILD_ID, CHANNEL_ID)
    try:
        connection.on_speaking(
            lambda user_id, ssrc, flags: logger.info(
                "user %s is %s (ssrc=%s)",
                user_id,
                "speaking" if flags else "silent",
                ssrc,
            )
        )

        # Record everything said in the channel while the song plays.
        connection.listen(WaveSink("./recordings"))

        source = PCMVolumeTransformer(FFmpegPCMAudio(AUDIO_PATH), volume=0.8)
        player = connection.play(source)
        logger.info("playing %s ...", AUDIO_PATH)

        await player.wait()
        logger.info("playback done: %d frames sent", player.sent_frames)

        # Keep listening for ten more seconds, then leave.
        await asyncio.sleep(10)
        await connection.stop_listening()
        logger.info("recordings saved to ./recordings/")
    finally:
        await connection.disconnect()
        await bot.stop()


async def main() -> None:
    worker = asyncio.create_task(play_and_record())
    try:
        await bot.start()
    finally:
        if not worker.done():
            worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
