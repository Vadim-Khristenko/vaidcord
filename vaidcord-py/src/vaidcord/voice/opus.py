"""Self-contained ctypes binding to libopus.

VaidCord ships its own thin binding so voice playback and receive do not
depend on third-party wrapper packages. Only the small subset of the Opus
API needed for Discord voice (48 kHz stereo, 20 ms frames) is exposed.

The shared library is resolved lazily via :func:`ctypes.util.find_library`;
call :func:`load_opus` with an explicit path to override.
"""

from __future__ import annotations

import array
import ctypes
import ctypes.util
import threading

__all__ = [
    "APPLICATION_AUDIO",
    "APPLICATION_LOWDELAY",
    "APPLICATION_VOIP",
    "CHANNELS",
    "FRAME_LENGTH_MS",
    "FRAME_SIZE",
    "SAMPLE_RATE",
    "SAMPLES_PER_FRAME",
    "SILENCE_FRAME",
    "Decoder",
    "Encoder",
    "OpusError",
    "OpusNotLoaded",
    "is_loaded",
    "load_opus",
]

SAMPLE_RATE = 48_000
CHANNELS = 2
FRAME_LENGTH_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_LENGTH_MS // 1000  # 960
SAMPLE_WIDTH = 2  # 16-bit signed PCM
FRAME_SIZE = SAMPLES_PER_FRAME * CHANNELS * SAMPLE_WIDTH  # 3840 bytes / 20ms

#: Opus frame that decodes to silence; used to flush the jitter buffer.
SILENCE_FRAME = b"\xf8\xff\xfe"

APPLICATION_VOIP = 2048
APPLICATION_AUDIO = 2049
APPLICATION_LOWDELAY = 2051

# Encoder/decoder CTL request codes (see opus_defines.h).
_CTL_SET_BITRATE = 4002
_CTL_SET_BANDWIDTH = 4008
_CTL_SET_INBAND_FEC = 4012
_CTL_SET_PACKET_LOSS_PERC = 4014
_CTL_SET_SIGNAL = 4024
_CTL_RESET_STATE = 4028
_CTL_SET_GAIN = 4034

BANDWIDTH_FULL = 1105
SIGNAL_VOICE = 3001
SIGNAL_MUSIC = 3002

_OK = 0

# Maximum samples per channel for a 120 ms packet at 48 kHz.
_MAX_FRAME_SAMPLES = SAMPLE_RATE * 120 // 1000


class OpusError(RuntimeError):
    """Raised when a libopus call fails."""

    def __init__(self, code: int, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or f"libopus returned error code {code}")


class OpusNotLoaded(OpusError):
    """Raised when the libopus shared library cannot be located."""

    def __init__(self, message: str) -> None:
        RuntimeError.__init__(self, message)
        self.code = -1


_lib: ctypes.CDLL | None = None
_lib_lock = threading.Lock()


def _configure(lib: ctypes.CDLL) -> ctypes.CDLL:
    lib.opus_strerror.argtypes = (ctypes.c_int,)
    lib.opus_strerror.restype = ctypes.c_char_p

    lib.opus_encoder_create.argtypes = (
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
    )
    lib.opus_encoder_create.restype = ctypes.c_void_p
    lib.opus_encode.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int16),
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int32,
    )
    lib.opus_encode.restype = ctypes.c_int32
    lib.opus_encoder_ctl.restype = ctypes.c_int32
    lib.opus_encoder_destroy.argtypes = (ctypes.c_void_p,)
    lib.opus_encoder_destroy.restype = None

    lib.opus_decoder_create.argtypes = (
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
    )
    lib.opus_decoder_create.restype = ctypes.c_void_p
    lib.opus_decode.argtypes = (
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int16),
        ctypes.c_int,
        ctypes.c_int,
    )
    lib.opus_decode.restype = ctypes.c_int
    lib.opus_decoder_ctl.restype = ctypes.c_int32
    lib.opus_decoder_destroy.argtypes = (ctypes.c_void_p,)
    lib.opus_decoder_destroy.restype = None

    lib.opus_packet_get_nb_frames.argtypes = (ctypes.c_char_p, ctypes.c_int32)
    lib.opus_packet_get_nb_frames.restype = ctypes.c_int
    lib.opus_packet_get_nb_channels.argtypes = (ctypes.c_char_p,)
    lib.opus_packet_get_nb_channels.restype = ctypes.c_int
    lib.opus_packet_get_samples_per_frame.argtypes = (ctypes.c_char_p, ctypes.c_int32)
    lib.opus_packet_get_samples_per_frame.restype = ctypes.c_int
    return lib


def load_opus(path: str | None = None) -> ctypes.CDLL:
    """Load libopus, optionally from an explicit ``path``."""
    global _lib
    with _lib_lock:
        if path is None:
            if _lib is not None:
                return _lib
            path = ctypes.util.find_library("opus")
            if path is None:
                raise OpusNotLoaded(
                    "Could not locate the libopus shared library. Install it via your "
                    "package manager (e.g. `apt install libopus0`) or call "
                    "vaidcord.voice.opus.load_opus('/path/to/libopus.so')."
                )
        _lib = _configure(ctypes.CDLL(path))
        return _lib


def is_loaded() -> bool:
    if _lib is not None:
        return True
    try:
        load_opus()
    except OpusNotLoaded:
        return False
    return True


def _strerror(lib: ctypes.CDLL, code: int) -> str:
    raw = lib.opus_strerror(code)
    return raw.decode("utf-8") if raw else f"error {code}"


def _check(lib: ctypes.CDLL, code: int) -> int:
    if code < _OK:
        raise OpusError(code, _strerror(lib, code))
    return code


class Encoder:
    """48 kHz stereo Opus encoder tuned for Discord voice."""

    def __init__(
        self,
        *,
        application: int = APPLICATION_AUDIO,
        bitrate_kbps: int = 128,
        fec: bool = True,
        expected_packet_loss: float = 0.15,
        signal: int = SIGNAL_MUSIC,
        sample_rate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
    ) -> None:
        self._lib = load_opus()
        self.sample_rate = sample_rate
        self.channels = channels
        error = ctypes.c_int()
        self._state: ctypes.c_void_p | None = ctypes.c_void_p(
            self._lib.opus_encoder_create(sample_rate, channels, application, ctypes.byref(error))
        )
        _check(self._lib, error.value)
        if not self._state:
            raise OpusError(-1, "opus_encoder_create returned NULL")
        self._ctl(_CTL_SET_BITRATE, min(512, max(16, bitrate_kbps)) * 1024)
        self._ctl(_CTL_SET_BANDWIDTH, BANDWIDTH_FULL)
        self._ctl(_CTL_SET_INBAND_FEC, 1 if fec else 0)
        self._ctl(_CTL_SET_PACKET_LOSS_PERC, int(min(1.0, max(0.0, expected_packet_loss)) * 100))
        self._ctl(_CTL_SET_SIGNAL, signal)

    def _ctl(self, request: int, value: int) -> None:
        _check(self._lib, self._lib.opus_encoder_ctl(self._state, ctypes.c_int(request), ctypes.c_int32(value)))

    def set_bitrate(self, kbps: int) -> None:
        self._ctl(_CTL_SET_BITRATE, min(512, max(16, kbps)) * 1024)

    def set_expected_packet_loss(self, fraction: float) -> None:
        self._ctl(_CTL_SET_PACKET_LOSS_PERC, int(min(1.0, max(0.0, fraction)) * 100))

    def encode(self, pcm: bytes, frame_samples: int = SAMPLES_PER_FRAME) -> bytes:
        """Encode one frame of signed 16-bit little-endian PCM."""
        if self._state is None:
            raise OpusError(-1, "encoder is closed")
        expected = frame_samples * self.channels * SAMPLE_WIDTH
        if len(pcm) < expected:
            pcm = pcm + b"\x00" * (expected - len(pcm))
        max_bytes = 1276 * 3
        out = ctypes.create_string_buffer(max_bytes)
        pcm_ptr = ctypes.cast(ctypes.c_char_p(pcm), ctypes.POINTER(ctypes.c_int16))
        written = _check(
            self._lib,
            self._lib.opus_encode(self._state, pcm_ptr, frame_samples, out, max_bytes),
        )
        return out.raw[:written]

    def reset(self) -> None:
        self._ctl(_CTL_RESET_STATE, 0)

    def close(self) -> None:
        if self._state is not None:
            self._lib.opus_encoder_destroy(self._state)
            self._state = None

    def __del__(self) -> None:  # pragma: no cover - GC timing dependent
        try:
            self.close()
        except Exception:
            pass


class Decoder:
    """48 kHz stereo Opus decoder with packet-loss concealment."""

    def __init__(self, *, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS) -> None:
        self._lib = load_opus()
        self.sample_rate = sample_rate
        self.channels = channels
        error = ctypes.c_int()
        self._state: ctypes.c_void_p | None = ctypes.c_void_p(
            self._lib.opus_decoder_create(sample_rate, channels, ctypes.byref(error))
        )
        _check(self._lib, error.value)
        if not self._state:
            raise OpusError(-1, "opus_decoder_create returned NULL")

    def packet_frame_samples(self, packet: bytes) -> int:
        """Samples per channel encoded in ``packet`` (per frame * frame count)."""
        frames = _check(self._lib, self._lib.opus_packet_get_nb_frames(packet, len(packet)))
        per_frame = _check(
            self._lib, self._lib.opus_packet_get_samples_per_frame(packet, self.sample_rate)
        )
        return frames * per_frame

    def decode(self, packet: bytes | None, *, fec: bool = False) -> bytes:
        """Decode an Opus packet to PCM; pass ``None`` for loss concealment."""
        if self._state is None:
            raise OpusError(-1, "decoder is closed")
        if packet is None:
            frame_samples = SAMPLES_PER_FRAME
            data: bytes | None = None
            length = 0
        else:
            frame_samples = min(self.packet_frame_samples(packet), _MAX_FRAME_SAMPLES)
            data = packet
            length = len(packet)
        buffer = (ctypes.c_int16 * (frame_samples * self.channels))()
        decoded = _check(
            self._lib,
            self._lib.opus_decode(self._state, data, length, buffer, frame_samples, 1 if fec else 0),
        )
        samples = array.array("h", buffer[: decoded * self.channels])
        return samples.tobytes()

    def close(self) -> None:
        if self._state is not None:
            self._lib.opus_decoder_destroy(self._state)
            self._state = None

    def __del__(self) -> None:  # pragma: no cover - GC timing dependent
        try:
            self.close()
        except Exception:
            pass
