"""Tests for the full voice media pipeline: Opus, RTP, crypto, play, receive."""

from __future__ import annotations

import asyncio
import math
import struct
import wave
from typing import Any

import pytest

from vaidcord.voice import (
    BufferSink,
    CallbackSink,
    OpusFrameSource,
    PCMAudio,
    PCMVolumeTransformer,
    SilenceSource,
    VoiceCloseAction,
    VoiceDatagram,
    VoiceDecryptionError,
    VoiceFrame,
    VoiceGatewayConfig,
    VoiceReady,
    VoiceReceiver,
    VoiceServerUpdate,
    VoiceState,
    WaveSink,
    classify_voice_close_code,
    create_voice_box,
    is_rtcp_packet,
    opus,
    parse_rtp_packet,
    supported_encryption_modes,
)
from vaidcord.voice.connection import VoiceConnection
from vaidcord.voice.player import AudioPlayer
from vaidcord.voice.rtp import strip_header_extension

requires_libopus = pytest.mark.skipif(not opus.is_loaded(), reason="libopus not available")


def make_rtp_header(
    *, sequence: int = 1, timestamp: int = 960, ssrc: int = 7, extension: bool = False
) -> bytes:
    first = 0x80 | (0x10 if extension else 0)
    header = struct.pack(">BBHII", first, 0x78, sequence, timestamp, ssrc)
    if extension:
        header += struct.pack(">HH", 0xBEDE, 1)  # one 4-byte extension word
    return header


def sine_pcm_frame(frequency: float = 440.0, amplitude: int = 12000) -> bytes:
    samples = bytearray()
    for i in range(opus.SAMPLES_PER_FRAME):
        value = int(amplitude * math.sin(2 * math.pi * frequency * i / opus.SAMPLE_RATE))
        samples += struct.pack("<hh", value, value)
    return bytes(samples)


# --------------------------------------------------------------------- #
# Opus binding                                                          #
# --------------------------------------------------------------------- #


@requires_libopus
def test_opus_encode_decode_roundtrip() -> None:
    encoder = opus.Encoder()
    decoder = opus.Decoder()
    packet = encoder.encode(sine_pcm_frame())
    assert 0 < len(packet) < 1500
    pcm = decoder.decode(packet)
    assert len(pcm) == opus.FRAME_SIZE


@requires_libopus
def test_opus_decoder_packet_loss_concealment() -> None:
    decoder = opus.Decoder()
    assert len(decoder.decode(None)) == opus.FRAME_SIZE


@requires_libopus
def test_opus_silence_frame_decodes() -> None:
    decoder = opus.Decoder()
    pcm = decoder.decode(opus.SILENCE_FRAME)
    assert len(pcm) == opus.FRAME_SIZE
    assert max(abs(s) for s in memoryview(pcm).cast("h")) < 128


@requires_libopus
def test_opus_encoder_pads_short_pcm() -> None:
    encoder = opus.Encoder()
    packet = encoder.encode(b"\x00" * 100)
    assert packet


# --------------------------------------------------------------------- #
# RTP parsing                                                           #
# --------------------------------------------------------------------- #


def test_parse_rtp_packet_basic_fields() -> None:
    data = make_rtp_header(sequence=42, timestamp=1920, ssrc=99) + b"payload"
    packet = parse_rtp_packet(data)
    assert packet.version == 2
    assert packet.payload_type == 0x78
    assert packet.sequence == 42
    assert packet.timestamp == 1920
    assert packet.ssrc == 99
    assert packet.header == data[:12]
    assert packet.payload == b"payload"


def test_parse_rtp_packet_with_extension_preamble() -> None:
    data = make_rtp_header(extension=True) + b"rest"
    packet = parse_rtp_packet(data)
    assert packet.extension
    assert len(packet.header) == 16
    assert packet.payload == b"rest"
    # one extension word (4 bytes) is stripped from the decrypted payload
    assert strip_header_extension(packet, b"WORDopus") == b"opus"


def test_rtcp_detection() -> None:
    rtcp = bytes([0x80, 201]) + b"\x00" * 6
    assert is_rtcp_packet(rtcp)
    assert not is_rtcp_packet(make_rtp_header() + b"x")


def test_parse_rtp_packet_rejects_short_input() -> None:
    with pytest.raises(ValueError):
        parse_rtp_packet(b"\x80\x78")


# --------------------------------------------------------------------- #
# Transport encryption                                                  #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", supported_encryption_modes())
def test_voice_box_seal_open_roundtrip(mode: str) -> None:
    box = create_voice_box(mode, bytes(range(32)))
    header = make_rtp_header()
    sealed = box.seal(header, b"opus data", 1234)
    packet, payload = box.open_packet(header + sealed)
    assert payload == b"opus data"
    assert packet.ssrc == 7


@pytest.mark.parametrize(
    "mode", ["aead_aes256_gcm_rtpsize", "aead_xchacha20_poly1305_rtpsize"]
)
def test_voice_box_rejects_tampered_header(mode: str) -> None:
    box = create_voice_box(mode, bytes(range(32)))
    header = make_rtp_header()
    sealed = box.seal(header, b"opus data", 1)
    tampered = bytearray(header + sealed)
    tampered[8] ^= 0xFF  # flip a bit inside the authenticated SSRC field
    with pytest.raises(VoiceDecryptionError):
        box.open_packet(bytes(tampered))


def test_voice_box_strips_encrypted_extension_words() -> None:
    box = create_voice_box("aead_aes256_gcm_rtpsize", bytes(range(32)))
    header = make_rtp_header(extension=True)
    sealed = box.seal(header, b"EXT!" + b"opus data", 7)
    _, payload = box.open_packet(header + sealed)
    assert payload == b"opus data"


def test_create_voice_box_unknown_mode() -> None:
    with pytest.raises(RuntimeError, match="Unsupported voice encryption mode"):
        create_voice_box("xsalsa20_poly1305", bytes(32))


def test_supported_modes_cover_discord_required_set() -> None:
    modes = supported_encryption_modes()
    assert "aead_aes256_gcm_rtpsize" in modes
    assert "aead_xchacha20_poly1305_rtpsize" in modes


# --------------------------------------------------------------------- #
# Audio sources                                                         #
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pcm_audio_pads_and_terminates(tmp_path) -> None:
    path = tmp_path / "audio.pcm"
    path.write_bytes(b"\x01\x02" * 1000)  # 2000 bytes -> less than one frame
    source = PCMAudio(open(path, "rb"))  # noqa: ASYNC230
    frame = await source.read()
    assert len(frame) == opus.FRAME_SIZE
    assert frame.startswith(b"\x01\x02")
    assert await source.read() == b""
    await source.cleanup()


@pytest.mark.asyncio
async def test_silence_source_produces_fixed_duration() -> None:
    source = SilenceSource(duration_ms=60)
    frames = []
    while frame := await source.read():
        frames.append(frame)
    assert len(frames) == 3
    assert all(f == b"\x00" * opus.FRAME_SIZE for f in frames)


@pytest.mark.asyncio
async def test_opus_frame_source_wraps_async_iterator() -> None:
    async def frames():
        yield b"\x01"
        yield b"\x02"

    source = OpusFrameSource(frames())
    assert source.is_opus()
    assert await source.read() == b"\x01"
    assert await source.read() == b"\x02"
    assert await source.read() == b""


@pytest.mark.asyncio
async def test_volume_transformer_scales_samples() -> None:
    class OneFrame(PCMAudio):
        def __init__(self) -> None:
            self._sent = False

        async def read(self) -> bytes:
            if self._sent:
                return b""
            self._sent = True
            return struct.pack("<h", 10000) * (opus.FRAME_SIZE // 2)

        async def cleanup(self) -> None:
            return None

    transformer = PCMVolumeTransformer(OneFrame(), volume=0.5)
    frame = await transformer.read()
    assert struct.unpack_from("<h", frame, 0)[0] == 5000
    transformer.volume = 99  # clamped
    assert transformer.volume == 4.0


def test_volume_transformer_rejects_opus_sources() -> None:
    async def frames():
        yield b"\x01"

    with pytest.raises(ValueError):
        PCMVolumeTransformer(OpusFrameSource(frames()))


# --------------------------------------------------------------------- #
# Player                                                                #
# --------------------------------------------------------------------- #


class FakePlaybackConnection:
    def __init__(self) -> None:
        self.frames: list[bytes] = []
        self.speaking: list[int] = []

    async def set_speaking(self, speaking: int, *, delay: int = 0) -> None:
        self.speaking.append(speaking)

    async def send_audio_frame(self, payload: bytes, **kwargs: Any) -> None:
        self.frames.append(payload)

    async def send_silence_frames(self, **kwargs: Any) -> None:
        self.frames.append(b"silence")


@pytest.mark.asyncio
async def test_player_plays_opus_source_and_signals_speaking() -> None:
    async def frames():
        yield b"\x01"
        yield b"\x02"
        yield b"\x03"

    connection = FakePlaybackConnection()
    finished: list[Exception | None] = []

    player = AudioPlayer(
        OpusFrameSource(frames()),
        connection,  # type: ignore[arg-type]
        after=finished.append,
        frame_duration_ms=0,
    )
    player.start()
    await asyncio.wait_for(player.wait(), timeout=5)

    assert player.sent_frames == 3
    assert connection.frames[:3] == [b"\x01", b"\x02", b"\x03"]
    assert connection.speaking[0] == 1
    assert connection.speaking[-1] == 0
    assert finished == [None]


@pytest.mark.asyncio
async def test_player_stop_interrupts_playback() -> None:
    async def frames():
        for _ in range(10_000):
            yield b"\x01"

    connection = FakePlaybackConnection()
    player = AudioPlayer(OpusFrameSource(frames()), connection, frame_duration_ms=0)  # type: ignore[arg-type]
    player.start()
    await asyncio.sleep(0.01)
    player.stop()
    await asyncio.wait_for(player.wait(), timeout=5)
    assert 0 < player.sent_frames < 10_000


@pytest.mark.asyncio
async def test_player_pause_and_resume() -> None:
    async def frames():
        for _ in range(50):
            yield b"\x01"

    connection = FakePlaybackConnection()
    player = AudioPlayer(OpusFrameSource(frames()), connection, frame_duration_ms=0)  # type: ignore[arg-type]
    player.start()
    player.pause()
    await asyncio.sleep(0.02)
    assert player.is_paused
    count_while_paused = player.sent_frames
    await asyncio.sleep(0.02)
    assert player.sent_frames <= count_while_paused + 1
    player.resume()
    await asyncio.wait_for(player.wait(), timeout=5)
    assert player.sent_frames == 50


@pytest.mark.asyncio
async def test_player_wait_reraises_source_error() -> None:
    class BrokenSource(OpusFrameSource):
        def __init__(self) -> None:
            pass

        def is_opus(self) -> bool:
            return True

        async def read(self) -> bytes:
            raise RuntimeError("boom")

        async def cleanup(self) -> None:
            return None

    connection = FakePlaybackConnection()
    player = AudioPlayer(BrokenSource(), connection, frame_duration_ms=0)  # type: ignore[arg-type]
    player.start()
    with pytest.raises(RuntimeError, match="boom"):
        await asyncio.wait_for(player.wait(), timeout=5)


# --------------------------------------------------------------------- #
# Receive pipeline                                                      #
# --------------------------------------------------------------------- #


class FakeUDPSource:
    def __init__(self, datagrams: list[bytes]) -> None:
        self._datagrams = datagrams

    async def packets(self):
        for data in self._datagrams:
            yield VoiceDatagram(data=data, address=("127.0.0.1", 5000))


class PassthroughDave:
    def decrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        return frame


class FakeReceiveConnection:
    def __init__(self, datagrams: list[bytes], box, ssrc_map: dict[int, int]) -> None:
        self.udp = FakeUDPSource(datagrams)
        self.voice_box = box
        self.dave = PassthroughDave()
        self._map = ssrc_map

    def ssrc_to_user(self, ssrc: int) -> int | None:
        return self._map.get(ssrc)


def build_encrypted_packet(box, *, ssrc: int, sequence: int, opus_payload: bytes) -> bytes:
    header = make_rtp_header(sequence=sequence, timestamp=sequence * 960, ssrc=ssrc)
    return header + box.seal(header, opus_payload, sequence)


@requires_libopus
@pytest.mark.asyncio
async def test_receiver_decrypts_decodes_and_demuxes_by_user() -> None:
    box = create_voice_box("aead_aes256_gcm_rtpsize", bytes(range(32)))
    encoder = opus.Encoder()
    packet_a = encoder.encode(sine_pcm_frame(440))
    packet_b = encoder.encode(sine_pcm_frame(880))

    datagrams = [
        build_encrypted_packet(box, ssrc=100, sequence=1, opus_payload=packet_a),
        bytes([0x80, 201]) + b"\x00" * 10,  # RTCP is dropped
        build_encrypted_packet(box, ssrc=200, sequence=2, opus_payload=packet_b),
    ]
    connection = FakeReceiveConnection(datagrams, box, {100: 111, 200: 222})
    sink = BufferSink()
    receiver = VoiceReceiver(connection, sink)  # type: ignore[arg-type]
    receiver.start()
    await asyncio.wait_for(receiver._task, timeout=5)  # type: ignore[arg-type]

    assert receiver.received_frames == 2
    assert len(sink.pcm(111)) == opus.FRAME_SIZE
    assert len(sink.pcm(222)) == opus.FRAME_SIZE
    await receiver.stop()


@pytest.mark.asyncio
async def test_receiver_opus_sink_skips_decoding() -> None:
    box = create_voice_box("aead_xchacha20_poly1305_rtpsize", bytes(range(32)))
    datagrams = [build_encrypted_packet(box, ssrc=5, sequence=9, opus_payload=b"\xde\xad")]
    frames: list[VoiceFrame] = []
    connection = FakeReceiveConnection(datagrams, box, {5: 50})
    receiver = VoiceReceiver(connection, CallbackSink(frames.append, opus_frames=True))  # type: ignore[arg-type]
    receiver.start()
    await asyncio.wait_for(receiver._task, timeout=5)  # type: ignore[arg-type]

    assert len(frames) == 1
    assert frames[0].opus == b"\xde\xad"
    assert frames[0].pcm is None
    assert frames[0].user_id == 50
    assert frames[0].sequence == 9


@pytest.mark.asyncio
async def test_receiver_counts_undecryptable_packets() -> None:
    box = create_voice_box("aead_aes256_gcm_rtpsize", bytes(range(32)))
    bad = make_rtp_header() + b"\x00" * 24
    connection = FakeReceiveConnection([bad], box, {})
    receiver = VoiceReceiver(connection, CallbackSink(lambda f: None, opus_frames=True))  # type: ignore[arg-type]
    receiver.start()
    await asyncio.wait_for(receiver._task, timeout=5)  # type: ignore[arg-type]
    assert receiver.dropped_packets == 1
    assert receiver.received_frames == 0


@requires_libopus
@pytest.mark.asyncio
async def test_wave_sink_writes_playable_files(tmp_path) -> None:
    box = create_voice_box("aead_aes256_gcm_rtpsize", bytes(range(32)))
    encoder = opus.Encoder()
    datagrams = [
        build_encrypted_packet(box, ssrc=1, sequence=i, opus_payload=encoder.encode(sine_pcm_frame()))
        for i in range(1, 4)
    ]
    connection = FakeReceiveConnection(datagrams, box, {1: 42})
    receiver = VoiceReceiver(connection, WaveSink(tmp_path))  # type: ignore[arg-type]
    receiver.start()
    await asyncio.wait_for(receiver._task, timeout=5)  # type: ignore[arg-type]
    await receiver.stop()

    with wave.open(str(tmp_path / "user-42.wav"), "rb") as recording:
        assert recording.getframerate() == opus.SAMPLE_RATE
        assert recording.getnchannels() == opus.CHANNELS
        assert recording.getnframes() == 3 * opus.SAMPLES_PER_FRAME


# --------------------------------------------------------------------- #
# Close-code policy & connection event handling                         #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("code", "action"),
    [
        (None, VoiceCloseAction.RESUME),
        (1000, VoiceCloseAction.RESUME),
        (1006, VoiceCloseAction.RESUME),
        (4015, VoiceCloseAction.RESUME),
        (4006, VoiceCloseAction.REJOIN),
        (4009, VoiceCloseAction.REJOIN),
        (4004, VoiceCloseAction.FATAL),
        (4014, VoiceCloseAction.FATAL),
        (4017, VoiceCloseAction.FATAL),
    ],
)
def test_classify_voice_close_code(code: int | None, action: VoiceCloseAction) -> None:
    assert classify_voice_close_code(code) is action


class FakeRuntime:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def send_payload(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


class FakeBot:
    def __init__(self) -> None:
        self.runtime = FakeRuntime()


def make_connection() -> VoiceConnection:
    return VoiceConnection(
        bot=FakeBot(),  # type: ignore[arg-type]
        guild_id=10,
        user_id=30,
        state=VoiceState(guild_id=10, channel_id=20, user_id=30, session_id="session"),
        server=VoiceServerUpdate(guild_id=10, token="token", endpoint="voice.example"),
        config=VoiceGatewayConfig(),
    )


@pytest.mark.asyncio
async def test_connection_tracks_speaking_ssrc_map_and_callbacks() -> None:
    connection = make_connection()
    seen: list[tuple[int, int, int]] = []
    connection.on_speaking(lambda user, ssrc, flags: seen.append((user, ssrc, flags)))

    await connection._handle_ws_payload(
        {"op": 5, "d": {"ssrc": 555, "user_id": "42", "speaking": 1}}
    )
    assert connection.ssrc_to_user(555) == 42
    assert seen == [(42, 555, 1)]

    await connection._handle_ws_payload({"op": 13, "d": {"user_id": "42"}})
    assert connection.ssrc_to_user(555) is None


@pytest.mark.asyncio
async def test_connection_maps_audio_ssrc_from_video_payload() -> None:
    connection = make_connection()
    await connection._handle_ws_payload(
        {"op": 12, "d": {"user_id": "9", "audio_ssrc": 777, "video_ssrc": 778}}
    )
    assert connection.ssrc_to_user(777) == 9


@pytest.mark.asyncio
async def test_connection_resumed_event_sets_on_op9() -> None:
    connection = make_connection()
    assert not connection._resumed_event.is_set()
    await connection._handle_ws_payload({"op": 9, "d": {}})
    assert connection._resumed_event.is_set()


@pytest.mark.asyncio
async def test_session_description_builds_voice_box_lazily() -> None:
    connection = make_connection()
    await connection._handle_ws_payload(
        {
            "op": 4,
            "d": {"mode": "aead_aes256_gcm_rtpsize", "secret_key": list(range(32))},
        }
    )
    header = make_rtp_header()
    sealed = connection._encrypt_voice_payload(header, b"opus")
    assert connection.voice_box is not None
    _, payload = connection.voice_box.open_packet(header + sealed)
    assert payload == b"opus"


# --------------------------------------------------------------------- #
# FFmpeg sources (require the ffmpeg binary)                            #
# --------------------------------------------------------------------- #

import shutil  # noqa: E402

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not available"
)


@pytest.fixture()
def tone_wav(tmp_path):
    import subprocess

    path = tmp_path / "tone.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
            "-ac", "2", "-ar", "48000", str(path),
        ],
        check=True,
    )
    return str(path)


@requires_ffmpeg
@pytest.mark.asyncio
async def test_ffmpeg_pcm_audio_decodes_file(tone_wav) -> None:
    from vaidcord.voice import FFmpegPCMAudio

    source = FFmpegPCMAudio(tone_wav)
    frames = 0
    while frame := await source.read():
        assert len(frame) == opus.FRAME_SIZE
        frames += 1
    await source.cleanup()
    assert 24 <= frames <= 26  # 0.5s of audio in 20ms frames


@requires_ffmpeg
@requires_libopus
@pytest.mark.asyncio
async def test_ffmpeg_opus_audio_yields_decodable_packets(tone_wav) -> None:
    from vaidcord.voice import FFmpegOpusAudio

    source = FFmpegOpusAudio(tone_wav)
    assert source.is_opus()
    decoder = opus.Decoder()
    packets = 0
    pcm_total = 0
    while packet := await source.read():
        pcm_total += len(decoder.decode(packet))
        packets += 1
    await source.cleanup()
    assert packets >= 24
    assert pcm_total >= 24 * opus.FRAME_SIZE


@requires_ffmpeg
@pytest.mark.asyncio
async def test_ffmpeg_pcm_audio_from_pipe_stream(tone_wav) -> None:
    from vaidcord.voice import FFmpegPCMAudio

    with open(tone_wav, "rb") as stream:  # noqa: ASYNC230
        source = FFmpegPCMAudio("pipe:0", pipe_stream=stream)
        frames = 0
        while await source.read():
            frames += 1
        await source.cleanup()
    assert frames >= 24


# --------------------------------------------------------------------- #
# End-to-end loopback: play -> encrypt -> UDP -> decrypt -> decode      #
# --------------------------------------------------------------------- #


class FakeWS:
    closed = False

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


class CapturingUDP:
    def __init__(self) -> None:
        self.packets_sent: list[bytes] = []

    async def send(self, data: bytes) -> None:
        self.packets_sent.append(data)


@requires_libopus
@pytest.mark.asyncio
async def test_end_to_end_play_and_listen_loopback() -> None:
    """A bot plays PCM audio; a second bot receives, decrypts and decodes it."""
    sender = make_connection()
    sender.ready = VoiceReady(ssrc=321, ip="127.0.0.1", port=5000, modes=("aead_aes256_gcm_rtpsize",))
    sender._ws = FakeWS()  # type: ignore[assignment]
    udp = CapturingUDP()
    sender.udp = udp  # type: ignore[assignment]
    await sender._handle_ws_payload(
        {"op": 4, "d": {"mode": "aead_aes256_gcm_rtpsize", "secret_key": list(range(32))}}
    )

    async def pcm_frames():
        for _ in range(10):
            yield sine_pcm_frame()

    class PCMSource(PCMAudio):
        def __init__(self) -> None:
            self._iter = pcm_frames()

        async def read(self) -> bytes:
            try:
                return await anext(self._iter)
            except StopAsyncIteration:
                return b""

        async def cleanup(self) -> None:
            return None

    player = sender.play(PCMSource())
    await asyncio.wait_for(player.wait(), timeout=10)
    assert player.sent_frames == 10
    # 10 audio frames + trailing silence frames were all encrypted and sent.
    assert len(udp.packets_sent) >= 10

    # Now replay the captured packets into a receiving connection.
    box = create_voice_box("aead_aes256_gcm_rtpsize", bytes(range(32)))
    listener = FakeReceiveConnection(list(udp.packets_sent), box, {321: 42})
    sink = BufferSink()
    receiver = VoiceReceiver(listener, sink)  # type: ignore[arg-type]
    receiver.start()
    await asyncio.wait_for(receiver._task, timeout=10)  # type: ignore[arg-type]

    recorded = sink.pcm(42)
    assert len(recorded) == 10 * opus.FRAME_SIZE
    # The sine tone must survive the trip with real signal energy intact.
    peak = max(abs(s) for s in memoryview(recorded).cast("h"))
    assert peak > 5000


@pytest.mark.asyncio
async def test_manager_registers_and_forgets_connections() -> None:
    from vaidcord.voice import VoiceManager

    bot = FakeBot()
    manager = VoiceManager(bot)  # type: ignore[arg-type]
    connection = make_connection()
    manager._connections[10] = connection
    assert manager.get(10) is connection

    await manager.disconnect(10)
    assert manager.get(10) is None
    assert bot.runtime.payloads[-1]["d"]["channel_id"] is None
