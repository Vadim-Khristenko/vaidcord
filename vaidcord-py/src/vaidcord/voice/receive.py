"""Inbound voice pipeline: decrypt, decode, and demultiplex per speaker.

Attach an :class:`AudioSink` to a connected :class:`VoiceConnection` via
``connection.listen(sink)``. The receiver reads the UDP socket, drops RTCP
traffic, decrypts each RTP packet with the negotiated transport mode,
undoes DAVE E2EE when active, decodes Opus to PCM (unless the sink asks
for raw Opus), and hands frames to the sink tagged with the speaking
user's id resolved from SSRC mappings.
"""

from __future__ import annotations

import asyncio
import logging
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import opus
from .crypto import VoiceDecryptionError
from .rtp import is_rtcp_packet

if TYPE_CHECKING:
    from .connection import VoiceConnection

logger = logging.getLogger(__name__)

__all__ = [
    "AudioSink",
    "BufferSink",
    "CallbackSink",
    "VoiceFrame",
    "VoiceReceiver",
    "WaveSink",
]


@dataclass(frozen=True, slots=True)
class VoiceFrame:
    """One decoded (or raw Opus) audio frame from a remote speaker."""

    ssrc: int
    user_id: int | None
    sequence: int
    timestamp: int
    opus: bytes
    pcm: bytes | None


class AudioSink:
    """Consumes inbound audio frames."""

    def wants_opus(self) -> bool:
        """Return ``True`` to receive raw Opus packets and skip decoding."""
        return False

    def write(self, frame: VoiceFrame) -> None:
        raise NotImplementedError

    def on_speaking_start(self, user_id: int, ssrc: int) -> None:
        """Called when a user's SSRC is first mapped (started transmitting)."""

    def on_speaking_stop(self, user_id: int) -> None:
        """Called when a user disconnects from the channel."""

    def cleanup(self) -> None:
        """Flush and release resources once listening stops."""


class BufferSink(AudioSink):
    """Accumulates PCM per user in memory (handy for tests and clips)."""

    def __init__(self) -> None:
        self.buffers: dict[int | None, bytearray] = {}

    def write(self, frame: VoiceFrame) -> None:
        if frame.pcm is None:
            return
        self.buffers.setdefault(frame.user_id, bytearray()).extend(frame.pcm)

    def pcm(self, user_id: int | None) -> bytes:
        return bytes(self.buffers.get(user_id, b""))


class CallbackSink(AudioSink):
    """Routes every frame to a callable ``(frame) -> None``."""

    def __init__(self, callback: Callable[[VoiceFrame], Any], *, opus_frames: bool = False) -> None:
        self._callback = callback
        self._opus = opus_frames

    def wants_opus(self) -> bool:
        return self._opus

    def write(self, frame: VoiceFrame) -> None:
        self._callback(frame)


class WaveSink(AudioSink):
    """Writes one 48 kHz stereo ``.wav`` file per speaking user."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._files: dict[int | None, wave.Wave_write] = {}

    def _file_for(self, user_id: int | None) -> wave.Wave_write:
        writer = self._files.get(user_id)
        if writer is None:
            name = f"user-{user_id}.wav" if user_id is not None else "unknown.wav"
            writer = wave.open(str(self.directory / name), "wb")
            writer.setnchannels(opus.CHANNELS)
            writer.setsampwidth(2)
            writer.setframerate(opus.SAMPLE_RATE)
            self._files[user_id] = writer
        return writer

    def write(self, frame: VoiceFrame) -> None:
        if frame.pcm is None:
            return
        self._file_for(frame.user_id).writeframes(frame.pcm)

    def cleanup(self) -> None:
        for writer in self._files.values():
            try:
                writer.close()
            except Exception:  # pragma: no cover
                logger.debug("Failed closing wave file", exc_info=True)
        self._files.clear()


class VoiceReceiver:
    """Background task that feeds an :class:`AudioSink` from the UDP socket."""

    def __init__(self, connection: VoiceConnection, sink: AudioSink) -> None:
        self.connection = connection
        self.sink = sink
        self._task: asyncio.Task[None] | None = None
        self._decoders: dict[int, opus.Decoder] = {}
        self.received_frames = 0
        self.dropped_packets = 0

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("VoiceReceiver is already running")
        self._task = asyncio.create_task(self._run(), name="vaidcord-voice-receiver")

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        for decoder in self._decoders.values():
            decoder.close()
        self._decoders.clear()
        try:
            self.sink.cleanup()
        except Exception:  # pragma: no cover
            logger.exception("Audio sink cleanup failed")

    async def _run(self) -> None:
        udp = self.connection.udp
        if udp is None:
            raise RuntimeError("Voice UDP transport is not connected")
        async for datagram in udp.packets():
            try:
                self._handle_datagram(datagram.data)
            except VoiceDecryptionError:
                self.dropped_packets += 1
                logger.debug("Dropped undecryptable voice packet")
            except Exception:
                self.dropped_packets += 1
                logger.exception("Error handling inbound voice packet")

    def _handle_datagram(self, data: bytes) -> None:
        if len(data) < 12 or is_rtcp_packet(data):
            return
        box = self.connection.voice_box
        if box is None:
            return
        packet, payload = box.open_packet(data)
        if not payload:
            return
        payload = self.connection.dave.decrypt_frame(ssrc=packet.ssrc, frame=payload)
        user_id = self.connection.ssrc_to_user(packet.ssrc)
        pcm: bytes | None = None
        if not self.sink.wants_opus():
            if payload == opus.SILENCE_FRAME:
                return
            decoder = self._decoders.get(packet.ssrc)
            if decoder is None:
                decoder = self._decoders[packet.ssrc] = opus.Decoder()
            pcm = decoder.decode(payload)
        frame = VoiceFrame(
            ssrc=packet.ssrc,
            user_id=user_id,
            sequence=packet.sequence,
            timestamp=packet.timestamp,
            opus=payload,
            pcm=pcm,
        )
        self.received_frames += 1
        self.sink.write(frame)
