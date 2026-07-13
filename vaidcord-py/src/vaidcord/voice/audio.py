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
    libopus: bool = False

    @property
    def opus_ready(self) -> bool:
        """Opus encoding is available via the bundled ctypes binding or opuslib."""
        return self.libopus or self.opuslib

    @property
    def missing_playback(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.ffmpeg:
            missing.append("ffmpeg")
        if not self.opus_ready:
            missing.append("libopus")
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
            "Install the libopus system library (e.g. `apt install libopus0`) and ffmpeg in PATH; "
            "`pip install 'vaidcord[voice]'` covers the Python-side extras."
        )


def check_voice_dependencies() -> AudioBackendStatus:
    from . import opus as opus_binding

    return AudioBackendStatus(
        ffmpeg=shutil.which("ffmpeg") is not None,
        opuslib=importlib.util.find_spec("opuslib") is not None,
        pynacl=importlib.util.find_spec("nacl") is not None,
        cryptography=importlib.util.find_spec("cryptography") is not None,
        libopus=opus_binding.is_loaded(),
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


def _make_opus_encoder(
    sample_rate: int, channels: int, application: str, bitrate_kbps: int
):
    """Build an ``encode(pcm, frame_samples) -> bytes`` callable.

    Prefers the bundled ctypes binding to libopus; falls back to the
    third-party ``opuslib`` wrapper when the shared library cannot be
    located by ctypes but opuslib manages to load it its own way.
    """
    from . import opus as opus_binding

    if opus_binding.is_loaded():
        application_map = {
            "voip": opus_binding.APPLICATION_VOIP,
            "audio": opus_binding.APPLICATION_AUDIO,
            "restricted_lowdelay": opus_binding.APPLICATION_LOWDELAY,
        }
        encoder = opus_binding.Encoder(
            application=application_map.get(application, opus_binding.APPLICATION_AUDIO),
            bitrate_kbps=bitrate_kbps,
            sample_rate=sample_rate,
            channels=channels,
        )
        return encoder.encode
    try:
        import opuslib  # type: ignore[import-not-found]
    except ImportError as error:  # pragma: no cover - dependency gate
        raise MissingVoiceDependency(
            "Opus encoding requires the libopus system library "
            "(e.g. `apt install libopus0`) or the `opuslib` package."
        ) from error
    encoder = opuslib.Encoder(sample_rate, channels, application)
    return encoder.encode


async def iter_opus_frames(
    path: str,
    *,
    frame_duration_ms: int = 20,
    sample_rate: int = 48_000,
    channels: int = 2,
    application: str = "audio",
    bitrate_kbps: int = 128,
) -> AsyncIterator[bytes]:
    encode = _make_opus_encoder(sample_rate, channels, application, bitrate_kbps)
    ensure_voice_playback_dependencies()
    frame_samples = sample_rate * frame_duration_ms // 1000
    async for pcm in iter_pcm_s16le_frames(
        path,
        frame_duration_ms=frame_duration_ms,
        sample_rate=sample_rate,
        channels=channels,
    ):
        packet = encode(pcm, frame_samples)
        if packet:
            yield packet
