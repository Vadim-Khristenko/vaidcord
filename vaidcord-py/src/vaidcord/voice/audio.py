from __future__ import annotations

import asyncio
import importlib.util
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass


class AudioBackendError(RuntimeError):
    """Base error for voice audio backend failures."""


class MissingVoiceDependency(AudioBackendError):
    """Raised when an optional dependency required for voice playback is missing."""


@dataclass(frozen=True, slots=True)
class AudioBackendStatus:
    ffmpeg: bool
    opuslib: bool
    pynacl: bool
    cryptography: bool

    @property
    def missing_playback(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.ffmpeg:
            missing.append("ffmpeg")
        if not self.opuslib:
            missing.append("opuslib")
        return tuple(missing)

    @property
    def missing_encryption(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.pynacl:
            missing.append("PyNaCl")
        if not self.cryptography:
            missing.append("cryptography")
        return tuple(missing)

    @property
    def playback_ready(self) -> bool:
        return not self.missing_playback

    @property
    def encryption_ready(self) -> bool:
        return not self.missing_encryption

    def raise_for_playback(self) -> None:
        if self.playback_ready:
            return
        missing = ", ".join(self.missing_playback)
        raise MissingVoiceDependency(
            f"Voice file playback requires missing dependency/dependencies: {missing}. "
            "Install optional voice deps with `pip install 'vaidcord[voice]'` and install ffmpeg in PATH."
        )


def check_voice_dependencies() -> AudioBackendStatus:
    return AudioBackendStatus(
        ffmpeg=shutil.which("ffmpeg") is not None,
        opuslib=importlib.util.find_spec("opuslib") is not None,
        pynacl=importlib.util.find_spec("nacl") is not None,
        cryptography=importlib.util.find_spec("cryptography") is not None,
    )


def ensure_voice_playback_dependencies() -> AudioBackendStatus:
    status = check_voice_dependencies()
    status.raise_for_playback()
    return status


async def iter_file_chunks(path: str, *, chunk_size: int = 3840) -> AsyncIterator[bytes]:
    with open(path, "rb") as stream:  # noqa: ASYNC230
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            yield chunk


async def iter_pcm_s16le_frames(
    path: str,
    *,
    frame_duration_ms: int = 20,
    sample_rate: int = 48_000,
    channels: int = 2,
) -> AsyncIterator[bytes]:
    status = check_voice_dependencies()
    if not status.ffmpeg:
        raise MissingVoiceDependency(
            "ffmpeg is required to decode .wav/.mp3/.ogg and other file formats for voice playback. "
            "Install ffmpeg and make sure it is available in PATH."
        )
    frame_samples = sample_rate * frame_duration_ms // 1000
    frame_bytes = frame_samples * channels * 2
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        path,
        "-f",
        "s16le",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    reached_eof = False
    try:
        if process.stdout is None:
            raise RuntimeError("ffmpeg stdout is not available")
        while True:
            chunk = await process.stdout.read(frame_bytes)
            if not chunk:
                reached_eof = True
                break
            if len(chunk) < frame_bytes:
                chunk = chunk + (b"\x00" * (frame_bytes - len(chunk)))
            yield chunk
    finally:
        if reached_eof and process.returncode is None:
            await process.wait()
        elif process.returncode is None:
            process.terminate()
            await process.wait()
            return
        if process.returncode not in (0, None):
            stderr = b""
            if process.stderr is not None:
                stderr = await process.stderr.read()
            message = stderr.decode("utf-8", errors="replace").strip()
            raise AudioBackendError(f"ffmpeg failed while decoding audio: {message or process.returncode}")


async def iter_opus_frames(
    path: str,
    *,
    frame_duration_ms: int = 20,
    sample_rate: int = 48_000,
    channels: int = 2,
    application: str = "audio",
) -> AsyncIterator[bytes]:
    try:
        import opuslib  # type: ignore[import-not-found]
    except ImportError as error:  # pragma: no cover - dependency gate
        raise MissingVoiceDependency(
            "Opus encoding requires `opuslib`. Install optional voice deps with `pip install 'vaidcord[voice]'`."
        ) from error

    ensure_voice_playback_dependencies()
    frame_samples = sample_rate * frame_duration_ms // 1000
    encoder = opuslib.Encoder(sample_rate, channels, application)
    async for pcm in iter_pcm_s16le_frames(
        path,
        frame_duration_ms=frame_duration_ms,
        sample_rate=sample_rate,
        channels=channels,
    ):
        packet = encoder.encode(pcm, frame_samples)
        if packet:
            yield packet
