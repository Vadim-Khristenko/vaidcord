from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from vaidcord import Bot, GatewayIntent, VoiceSpeakingFlag, configure_logging
from vaidcord.voice import check_voice_dependencies, iter_opus_frames

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Set DISCORD_BOT_TOKEN before running this example")

GUILD_ID = int(os.getenv("VAIDCORD_VOICE_GUILD_ID", "123456789012345678"))
VOICE_CHANNEL_ID = int(os.getenv("VAIDCORD_VOICE_CHANNEL_ID", "123456789012345679"))
ASSET_PATH = Path(__file__).parent / "assets" / "Anamanaguchi_Miku-Ft_Hatsune_Miku.mp3"

bot = Bot(
    token=TOKEN,
    intents=int(GatewayIntent.GUILDS | GatewayIntent.GUILD_VOICE_STATES),
    command_sync_mode="replace",
    command_sync_guild_ids=(GUILD_ID,),
)
logger = logging.getLogger("vaidcord.examples.voice_showcase")


@bot.slash_command(name="ping", description="Health check for interactions")
async def ping(ctx) -> None:
    logger.info("Received /ping")
    await bot.create_interaction_response(
        int(ctx["id"]),
        ctx["token"],
        type=4,
        data={"content": "pong"},
    )


async def demo_stream_encoded_frames(connection) -> None:
    logger.info("Demo: stream encoded Opus frames")

    async def frames():
        sent = 0
        async for frame in iter_opus_frames(str(ASSET_PATH)):
            yield frame
            sent += 1
            if sent >= 100:
                break

    sent = await connection.stream_audio(
        frames(),
        frame_duration_ms=20,
        timestamp_step=960,
        speaking=True,
    )
    logger.info("Demo: stream encoded Opus frames sent=%s", sent)


async def demo_manual_speaking(connection) -> None:
    logger.info("Demo: manual speaking bitmask + synthetic frames")
    await connection.start_speaking(int(VoiceSpeakingFlag.MICROPHONE | VoiceSpeakingFlag.PRIORITY))
    try:
        # 3 tiny synthetic frames
        for _ in range(3):
            await connection.send_audio_frame(b"\xF8\xFF\xFE")
            await asyncio.sleep(0.02)
        await connection.send_silence_frames()
    finally:
        await connection.stop_speaking()


async def demo_play_file(connection) -> None:
    logger.info("Demo: play_file")
    sent = await connection.play_file(
        str(ASSET_PATH),
        chunk_size=3840,
        frame_duration_ms=20,
        timestamp_step=960,
    )
    logger.info("Demo: play_file sent=%s", sent)


async def run_showcase() -> None:
    if not ASSET_PATH.exists():
        raise FileNotFoundError(f"Audio file is missing: {ASSET_PATH}")
    status = check_voice_dependencies()
    logger.info(
        "Voice dependencies: ffmpeg=%s opuslib=%s pynacl=%s cryptography=%s",
        status.ffmpeg,
        status.opuslib,
        status.pynacl,
        status.cryptography,
    )
    status.raise_for_playback()

    logger.info("Waiting READY before voice join")
    ready = await bot.wait_until_ready(wait_timeout=30)
    if not ready:
        raise TimeoutError("Bot did not become READY in 30 seconds")

    logger.info("Joining voice guild=%s channel=%s", GUILD_ID, VOICE_CHANNEL_ID)
    connection = await bot.join_voice_channel(guild_id=GUILD_ID, channel_id=VOICE_CHANNEL_ID)
    try:
        logger.info("Voice connected, starting showcase flow")
        await demo_play_file(connection)
        await demo_stream_encoded_frames(connection)
        await demo_manual_speaking(connection)
    except Exception as error:  # noqa: BLE001
        logger.exception("Voice showcase playback failed: %s", error)
        raise
    finally:
        logger.info("Closing voice connection")
        await connection.close()
        logger.info("Stopping bot")
        await bot.stop()


async def main() -> None:
    showcase_task = asyncio.create_task(run_showcase())
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await bot.stop()
    finally:
        if not showcase_task.done():
            showcase_task.cancel()
            try:
                await showcase_task
            except asyncio.CancelledError:
                pass
        else:
            try:
                await showcase_task
            except Exception as error:  # noqa: BLE001
                if "close_code=4017" in str(error):
                    logger.error(
                        "Voice server requires DAVE/E2EE handshake support (close 4017). "
                        "Configure a production DaveCryptoBackend for DAVE-required channels."
                    )
                logger.exception("Showcase task failed: %s", error)


if __name__ == "__main__":
    configure_logging()
    logger.info(
        "Start voice showcase. Install voice extras (vaidcord[voice]) and configure VAIDCORD_VOICE_GUILD_ID/VAIDCORD_VOICE_CHANNEL_ID."
    )
    asyncio.run(main())
