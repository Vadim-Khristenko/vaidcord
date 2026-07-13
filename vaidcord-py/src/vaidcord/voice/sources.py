"""Audio source abstractions for voice playback.

An :class:`AudioSource` yields exactly one 20 ms frame per ``read()`` call —
either signed 16-bit little-endian 48 kHz stereo PCM (3840 bytes) or a
pre-encoded Opus packet when :meth:`AudioSource.is_opus` returns ``True``.
An empty ``bytes`` signals end of stream.
"""

from __future__ import annotations

import array
import asyncio
import io
import shutil
from collections.abc import AsyncIterator

from . import opus
from .audio import AudioBackendError, MissingVoiceDependency

__all__ = [
    "AudioSource",
    "FFmpegOpusAudio",
    "FFmpegPCMAudio",
    "OpusFrameSource",
    "PCMAudio",
    "PCMVolumeTransformer",
    "SilenceSource",
]


class AudioSource:
    """Base class for playable audio."""

    async def read(self) -> bytes:
        """Return the next 20 ms frame, or ``b""`` when exhausted."""
        raise NotImplementedError

    def is_opus(self) -> bool:
        """Whether :meth:`read` yields Opus packets instead of PCM."""
        return False

    async def cleanup(self) -> None:
        """Release any held resources; called once playback finishes."""


class PCMAudio(AudioSource):
    """Reads raw s16le 48 kHz stereo PCM from a binary stream."""

    def __init__(self, stream: io.BufferedIOBase | io.RawIOBase) -> None:
        self.stream = stream

    async def read(self) -> bytes:
        chunk = self.stream.read(opus.FRAME_SIZE) or b""
        if 0 < len(chunk) < opus.FRAME_SIZE:
            chunk = chunk + b"\x00" * (opus.FRAME_SIZE - len(chunk))
        return chunk

    async def cleanup(self) -> None:
        try:
            self.stream.close()
        except Exception:
            pass


class SilenceSource(AudioSource):
    """Produces PCM silence for a fixed duration (useful for padding/tests)."""

    def __init__(self, duration_ms: int = 1000) -> None:
        self._frames_left = max(0, duration_ms) // opus.FRAME_LENGTH_MS

    async def read(self) -> bytes:
        if self._frames_left <= 0:
            return b""
        self._frames_left -= 1
        return b"\x00" * opus.FRAME_SIZE


class OpusFrameSource(AudioSource):
    """Adapts an async iterator of pre-encoded Opus packets."""

    def __init__(self, frames: AsyncIterator[bytes]) -> None:
        self._frames = frames

    def is_opus(self) -> bool:
        return True

    async def read(self) -> bytes:
        try:
            return await anext(self._frames)  # type: ignore[arg-type]
        except StopAsyncIteration:
            return b""

    async def cleanup(self) -> None:
        aclose = getattr(self._frames, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:
                pass


class _FFmpegSource(AudioSource):
    def __init__(
        self,
        source: str,
        *,
        pipe_stream: io.BufferedIOBase | None = None,
        before_options: str | None = None,
        options: str | None = None,
        executable: str = "ffmpeg",
    ) -> None:
        if shutil.which(executable) is None:
            raise MissingVoiceDependency(
                f"`{executable}` was not found in PATH; it is required for file/stream playback."
            )
        self._source = source
        self._pipe_stream = pipe_stream
        self._before_options = before_options.split() if before_options else []
        self._options = options.split() if options else []
        self._executable = executable
        self._process: asyncio.subprocess.Process | None = None
        self._feeder: asyncio.Task[None] | None = None

    def _output_args(self) -> list[str]:
        raise NotImplementedError

    async def _spawn(self) -> asyncio.subprocess.Process:
        if self._process is not None:
            return self._process
        args = [
            "-hide_banner",
            "-loglevel",
            "error",
            *self._before_options,
            "-i",
            self._source,
            *self._output_args(),
            *self._options,
            "pipe:1",
        ]
        self._process = await asyncio.create_subprocess_exec(
            self._executable,
            *args,
            stdin=asyncio.subprocess.PIPE if self._pipe_stream is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if self._pipe_stream is not None:
            self._feeder = asyncio.create_task(self._feed_stdin())
        return self._process

    async def _feed_stdin(self) -> None:
        assert self._process is not None and self._process.stdin is not None
        stdin = self._process.stdin
        stream = self._pipe_stream
        assert stream is not None
        try:
            while True:
                chunk = await asyncio.to_thread(stream.read, 65536)
                if not chunk:
                    break
                stdin.write(chunk)
                await stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with_suppress_close(stdin)

    async def _read_exact(self, size: int) -> bytes:
        process = await self._spawn()
        assert process.stdout is not None
        data = await process.stdout.read(size)
        while 0 < len(data) < size:
            more = await process.stdout.read(size - len(data))
            if not more:
                break
            data += more
        return data

    async def _raise_if_failed(self) -> None:
        process = self._process
        if process is None:
            return
        if process.returncode is None:
            # stdout hit EOF, so ffmpeg is exiting; reap it to get the code.
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                return
        if process.returncode == 0:
            return
        stderr = b""
        if process.stderr is not None:
            stderr = await process.stderr.read()
        message = stderr.decode("utf-8", errors="replace").strip()
        raise AudioBackendError(f"ffmpeg failed: {message or process.returncode}")

    async def cleanup(self) -> None:
        if self._feeder is not None:
            self._feeder.cancel()
            self._feeder = None
        process = self._process
        self._process = None
        if process is not None and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            else:
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.kill()
                    await process.wait()
        if self._pipe_stream is not None:
            try:
                self._pipe_stream.close()
            except Exception:
                pass


def with_suppress_close(stdin: asyncio.StreamWriter) -> None:
    try:
        stdin.close()
    except Exception:
        pass


class FFmpegPCMAudio(_FFmpegSource):
    """Decodes any ffmpeg-supported file/URL/stream to 20 ms PCM frames.

    Pass ``source="pipe:0"`` together with ``pipe_stream=<binary stream>`` to
    stream from memory or a socket instead of a path/URL.
    """

    def _output_args(self) -> list[str]:
        return ["-f", "s16le", "-ar", str(opus.SAMPLE_RATE), "-ac", str(opus.CHANNELS)]

    async def read(self) -> bytes:
        chunk = await self._read_exact(opus.FRAME_SIZE)
        if not chunk:
            await self._raise_if_failed()
            return b""
        if len(chunk) < opus.FRAME_SIZE:
            chunk = chunk + b"\x00" * (opus.FRAME_SIZE - len(chunk))
        return chunk


class FFmpegOpusAudio(_FFmpegSource):
    """Encodes via ffmpeg's libopus into an Ogg stream and demuxes packets.

    Skips re-encoding inside Python entirely: ffmpeg produces Opus, VaidCord
    just parses Ogg pages and forwards the packets.
    """

    def __init__(
        self,
        source: str,
        *,
        bitrate_kbps: int = 128,
        pipe_stream: io.BufferedIOBase | None = None,
        before_options: str | None = None,
        options: str | None = None,
        executable: str = "ffmpeg",
    ) -> None:
        super().__init__(
            source,
            pipe_stream=pipe_stream,
            before_options=before_options,
            options=options,
            executable=executable,
        )
        self._bitrate_kbps = bitrate_kbps
        self._packets: list[bytes] = []
        self._buffer = b""
        self._skipped_headers = 0
        self._eof = False

    def is_opus(self) -> bool:
        return True

    def _output_args(self) -> list[str]:
        return [
            "-map_metadata",
            "-1",
            "-c:a",
            "libopus",
            "-b:a",
            f"{self._bitrate_kbps}k",
            "-ar",
            str(opus.SAMPLE_RATE),
            "-ac",
            str(opus.CHANNELS),
            "-f",
            "ogg",
        ]

    async def read(self) -> bytes:
        while True:
            if self._packets:
                packet = self._packets.pop(0)
                # The first two packets of an Ogg Opus stream are the
                # OpusHead/OpusTags headers, not audio.
                if self._skipped_headers < 2:
                    self._skipped_headers += 1
                    continue
                return packet
            if self._eof:
                await self._raise_if_failed()
                return b""
            await self._fill()

    async def _fill(self) -> None:
        chunk = await self._read_exact(8192)
        if not chunk:
            self._eof = True
        self._buffer += chunk
        self._parse_pages()

    def _parse_pages(self) -> None:
        while True:
            start = self._buffer.find(b"OggS")
            if start < 0:
                if len(self._buffer) > 3:
                    self._buffer = self._buffer[-3:]
                return
            if start:
                self._buffer = self._buffer[start:]
            if len(self._buffer) < 27:
                return
            segment_count = self._buffer[26]
            header_len = 27 + segment_count
            if len(self._buffer) < header_len:
                return
            lacing = self._buffer[27:header_len]
            body_len = sum(lacing)
            if len(self._buffer) < header_len + body_len:
                return
            body = self._buffer[header_len : header_len + body_len]
            self._buffer = self._buffer[header_len + body_len :]
            offset = 0
            packet = b""
            for lace in lacing:
                packet += body[offset : offset + lace]
                offset += lace
                if lace < 255:
                    self._packets.append(packet)
                    packet = b""
            # A trailing 255 lace means the packet continues on the next
            # page; ffmpeg's 20 ms opus packets never span pages, so any
            # remainder is safe to prepend on the next parse.
            if packet:
                self._buffer = packet + self._buffer


class PCMVolumeTransformer(AudioSource):
    """Scales the volume of a PCM source (1.0 = passthrough)."""

    def __init__(self, source: AudioSource, volume: float = 1.0) -> None:
        if source.is_opus():
            raise ValueError("PCMVolumeTransformer requires a PCM source, not Opus")
        self.source = source
        self.volume = volume

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(4.0, float(value)))

    async def read(self) -> bytes:
        frame = await self.source.read()
        if not frame or self._volume == 1.0:
            return frame
        samples = array.array("h")
        samples.frombytes(frame)
        scale = self._volume
        for index, sample in enumerate(samples):
            scaled = int(sample * scale)
            samples[index] = max(-32768, min(32767, scaled))
        return samples.tobytes()

    async def cleanup(self) -> None:
        await self.source.cleanup()
