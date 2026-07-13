package vaidcord

import "io"

// Opus/audio constants for the Discord voice pipeline (48 kHz stereo,
// 20 ms frames).
const (
	OpusSampleRate      = 48000
	OpusChannels        = 2
	OpusFrameLengthMS   = 20
	OpusSamplesPerFrame = OpusSampleRate / 1000 * OpusFrameLengthMS // 960
	// OpusTimestampStep is the RTP timestamp increment per 20 ms frame.
	OpusTimestampStep = OpusSamplesPerFrame
)

// OpusSilenceFrame is the canonical Opus silence packet appended after a
// stream so decoders flush cleanly.
var OpusSilenceFrame = []byte{0xF8, 0xFF, 0xFE}

// AudioSource yields pre-encoded Opus packets, one 20 ms frame per call.
// ReadOpus returns io.EOF when the stream ends. There is no pure-Go Opus
// encoder, so the SDK ships opus passthrough: feed it packets produced by
// ffmpeg/libopus (see FFmpegOpusSource) or captured from another connection.
type AudioSource interface {
	// ReadOpus returns the next Opus packet, or io.EOF at end of stream.
	ReadOpus() ([]byte, error)
	// Close releases any held resources; called once playback finishes.
	Close() error
}

// OpusPacketSource replays a fixed sequence of Opus packets.
type OpusPacketSource struct {
	packets [][]byte
	index   int
}

func NewOpusPacketSource(packets ...[]byte) *OpusPacketSource {
	return &OpusPacketSource{packets: packets}
}

func (s *OpusPacketSource) ReadOpus() ([]byte, error) {
	if s.index >= len(s.packets) {
		return nil, io.EOF
	}
	packet := s.packets[s.index]
	s.index++
	return packet, nil
}

func (s *OpusPacketSource) Close() error { return nil }

// OpusChannelSource adapts a channel of Opus packets; close the channel to
// end the stream.
type OpusChannelSource struct {
	Frames <-chan []byte
}

func NewOpusChannelSource(frames <-chan []byte) *OpusChannelSource {
	return &OpusChannelSource{Frames: frames}
}

func (s *OpusChannelSource) ReadOpus() ([]byte, error) {
	frame, ok := <-s.Frames
	if !ok {
		return nil, io.EOF
	}
	return frame, nil
}

func (s *OpusChannelSource) Close() error { return nil }

// SilenceSource produces Opus silence packets for a fixed duration —
// useful for padding and tests.
type SilenceSource struct {
	framesLeft int
}

func NewSilenceSource(durationMS int) *SilenceSource {
	frames := durationMS / OpusFrameLengthMS
	if frames < 0 {
		frames = 0
	}
	return &SilenceSource{framesLeft: frames}
}

func (s *SilenceSource) ReadOpus() ([]byte, error) {
	if s.framesLeft <= 0 {
		return nil, io.EOF
	}
	s.framesLeft--
	return OpusSilenceFrame, nil
}

func (s *SilenceSource) Close() error { return nil }
