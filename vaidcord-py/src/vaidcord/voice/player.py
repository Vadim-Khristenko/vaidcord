"""Drift-corrected audio playback for voice connections."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from . import opus
from .models import VoiceSpeakingFlag
from .sources import AudioSource

if TYPE_CHECKING:
    from .connection import VoiceConnection

logger = logging.getLogger(__name__)

__all__ = ["AudioPlayer"]

AfterCallback = Callable[[Exception | None], Awaitable[None] | None]


class AudioPlayer:
    """Plays an :class:`AudioSource` over a voice connection.

    Pacing uses an absolute deadline schedule (``next += 20ms``) instead of
    sleeping a fixed interval after each frame, so encode/encrypt/send time
    does not accumulate as drift. If the loop falls more than 100 ms behind
    (e.g. after a laptop suspend) the schedule resynchronises instead of
    bursting frames.
    """

    def __init__(
        self,
        source: AudioSource,
        connection: VoiceConnection,
        *,
        after: AfterCallback | None = None,
        speaking_flags: int = int(VoiceSpeakingFlag.MICROPHONE),
        frame_duration_ms: int = opus.FRAME_LENGTH_MS,
        bitrate_kbps: int = 128,
    ) -> None:
        self.source = source
        self.connection = connection
        self.after = after
        self.speaking_flags = speaking_flags
        self.frame_duration = frame_duration_ms / 1000.0
        self.timestamp_step = opus.SAMPLE_RATE * frame_duration_ms // 1000
        self._bitrate_kbps = bitrate_kbps
        self._encoder: opus.Encoder | None = None
        self._task: asyncio.Task[None] | None = None
        self._resumed = asyncio.Event()
        self._resumed.set()
        self._stopped = False
        self._done = asyncio.Event()
        self.sent_frames = 0
        self.error: Exception | None = None

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("AudioPlayer is already started")
        self._task = asyncio.create_task(self._run(), name="vaidcord-audio-player")

    @property
    def is_playing(self) -> bool:
        return self._task is not None and not self._done.is_set() and self._resumed.is_set()

    @property
    def is_paused(self) -> bool:
        return not self._done.is_set() and not self._resumed.is_set()

    def pause(self) -> None:
        self._resumed.clear()

    def resume(self) -> None:
        self._resumed.set()

    def stop(self) -> None:
        self._stopped = True
        self._resumed.set()

    async def wait(self) -> None:
        """Wait until playback finishes; re-raises a playback error if any."""
        await self._done.wait()
        if self.error is not None:
            raise self.error

    def _encode(self, frame: bytes) -> bytes:
        if self.source.is_opus():
            return frame
        if self._encoder is None:
            self._encoder = opus.Encoder(bitrate_kbps=self._bitrate_kbps)
        return self._encoder.encode(frame, self.timestamp_step)

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        error: Exception | None = None
        started_speaking = False
        try:
            await self.connection.set_speaking(self.speaking_flags)
            started_speaking = True
            next_deadline = loop.time()
            while not self._stopped:
                if not self._resumed.is_set():
                    await self.connection.send_silence_frames(frames=5, frame_duration_ms=0)
                    await self.connection.set_speaking(0)
                    await self._resumed.wait()
                    if self._stopped:
                        break
                    await self.connection.set_speaking(self.speaking_flags)
                    next_deadline = loop.time()
                frame = await self.source.read()
                if not frame:
                    break
                packet = self._encode(frame)
                await self.connection.send_audio_frame(
                    packet, timestamp_step=self.timestamp_step, encrypt=True
                )
                self.sent_frames += 1
                next_deadline += self.frame_duration
                delay = next_deadline - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    if delay < -0.1:
                        next_deadline = loop.time()
                    # Keep the event loop responsive even when frames are
                    # produced faster than real time (tests, prebuffered data).
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = exc
            logger.exception("Voice playback failed")
        finally:
            self.error = error
            try:
                if started_speaking:
                    await self.connection.send_silence_frames(frames=5, frame_duration_ms=0)
                    await self.connection.set_speaking(0)
            except Exception:  # pragma: no cover - connection may already be gone
                logger.debug("Could not send trailing silence", exc_info=True)
            try:
                await self.source.cleanup()
            except Exception:  # pragma: no cover
                logger.debug("Audio source cleanup failed", exc_info=True)
            if self._encoder is not None:
                self._encoder.close()
                self._encoder = None
            self._done.set()
            if self.after is not None:
                try:
                    result = self.after(error)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:  # pragma: no cover
                    logger.exception("AudioPlayer after-callback raised")
