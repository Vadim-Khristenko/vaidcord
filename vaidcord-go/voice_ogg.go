package vaidcord

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"os/exec"
	"strconv"
)

// OggDemuxer is an incremental Ogg page parser that reassembles packets
// from lacing values — a direct port of the Python SDK's FFmpegOpusAudio
// parser, so both SDKs demux ffmpeg's ogg/opus output identically.
type OggDemuxer struct {
	buffer  []byte
	packets [][]byte
}

var oggCapturePattern = []byte("OggS")

// Write feeds raw Ogg bytes into the demuxer.
func (d *OggDemuxer) Write(data []byte) {
	d.buffer = append(d.buffer, data...)
	d.parsePages()
}

// NextPacket pops the next complete logical packet, if any.
func (d *OggDemuxer) NextPacket() ([]byte, bool) {
	if len(d.packets) == 0 {
		return nil, false
	}
	packet := d.packets[0]
	d.packets = d.packets[1:]
	return packet, true
}

func (d *OggDemuxer) parsePages() {
	for {
		start := bytes.Index(d.buffer, oggCapturePattern)
		if start < 0 {
			if len(d.buffer) > 3 {
				d.buffer = d.buffer[len(d.buffer)-3:]
			}
			return
		}
		if start > 0 {
			d.buffer = d.buffer[start:]
		}
		if len(d.buffer) < 27 {
			return
		}
		segmentCount := int(d.buffer[26])
		headerLen := 27 + segmentCount
		if len(d.buffer) < headerLen {
			return
		}
		lacing := d.buffer[27:headerLen]
		bodyLen := 0
		for _, lace := range lacing {
			bodyLen += int(lace)
		}
		if len(d.buffer) < headerLen+bodyLen {
			return
		}
		body := d.buffer[headerLen : headerLen+bodyLen]
		remainder := d.buffer[headerLen+bodyLen:]
		offset := 0
		var packet []byte
		for _, lace := range lacing {
			packet = append(packet, body[offset:offset+int(lace)]...)
			offset += int(lace)
			if lace < 255 {
				d.packets = append(d.packets, packet)
				packet = nil
			}
		}
		// A trailing 255 lace means the packet continues on the next page;
		// ffmpeg's 20 ms opus packets never span pages, so any remainder is
		// safe to prepend on the next parse (mirrors the Python parser).
		if packet != nil {
			d.buffer = append(packet, remainder...)
		} else {
			d.buffer = remainder
		}
	}
}

// FFmpegOpusSource execs ffmpeg with libopus producing an ogg/opus stream on
// stdout and demuxes the Ogg pages in pure Go — no re-encoding happens in
// this process. The first two Ogg packets (OpusHead/OpusTags headers) are
// skipped automatically.
type FFmpegOpusSource struct {
	cmd            *exec.Cmd
	stdout         io.ReadCloser
	stderr         *bytes.Buffer
	demux          OggDemuxer
	readBuf        []byte
	skippedHeaders int
	eof            bool
	waited         bool
	waitErr        error
}

// FFmpegOption customises the ffmpeg invocation.
type FFmpegOption func(*ffmpegConfig)

type ffmpegConfig struct {
	executable    string
	bitrateKbps   int
	beforeOptions []string
	options       []string
	stdin         io.Reader
}

// WithFFmpegExecutable overrides the ffmpeg binary name/path.
func WithFFmpegExecutable(executable string) FFmpegOption {
	return func(c *ffmpegConfig) { c.executable = executable }
}

// WithFFmpegBitrate sets the opus bitrate in kbps (default 128).
func WithFFmpegBitrate(kbps int) FFmpegOption {
	return func(c *ffmpegConfig) { c.bitrateKbps = kbps }
}

// WithFFmpegBeforeOptions injects arguments before -i (e.g. reconnect flags).
func WithFFmpegBeforeOptions(args ...string) FFmpegOption {
	return func(c *ffmpegConfig) { c.beforeOptions = append(c.beforeOptions, args...) }
}

// WithFFmpegOptions injects arguments after the output settings.
func WithFFmpegOptions(args ...string) FFmpegOption {
	return func(c *ffmpegConfig) { c.options = append(c.options, args...) }
}

// WithFFmpegStdin streams input from a reader; pair it with source "pipe:0".
func WithFFmpegStdin(reader io.Reader) FFmpegOption {
	return func(c *ffmpegConfig) { c.stdin = reader }
}

// NewFFmpegOpusSource starts ffmpeg decoding source (a path, URL, or
// "pipe:0" with WithFFmpegStdin) into 48 kHz stereo ogg/opus.
func NewFFmpegOpusSource(ctx context.Context, source string, options ...FFmpegOption) (*FFmpegOpusSource, error) {
	config := ffmpegConfig{executable: "ffmpeg", bitrateKbps: 128}
	for _, option := range options {
		option(&config)
	}
	args := []string{"-hide_banner", "-loglevel", "error"}
	args = append(args, config.beforeOptions...)
	args = append(args,
		"-i", source,
		"-map_metadata", "-1",
		"-c:a", "libopus",
		"-b:a", strconv.Itoa(config.bitrateKbps)+"k",
		"-ar", strconv.Itoa(OpusSampleRate),
		"-ac", strconv.Itoa(OpusChannels),
		"-f", "ogg",
	)
	args = append(args, config.options...)
	args = append(args, "pipe:1")

	cmd := exec.CommandContext(ctx, config.executable, args...)
	if config.stdin != nil {
		cmd.Stdin = config.stdin
	}
	stderr := &bytes.Buffer{}
	cmd.Stderr = stderr
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	return &FFmpegOpusSource{
		cmd:     cmd,
		stdout:  stdout,
		stderr:  stderr,
		readBuf: make([]byte, 8192),
	}, nil
}

// ReadOpus returns the next Opus packet from the ffmpeg stream.
func (s *FFmpegOpusSource) ReadOpus() ([]byte, error) {
	for {
		if packet, ok := s.demux.NextPacket(); ok {
			// The first two packets of an Ogg Opus stream are the
			// OpusHead/OpusTags headers, not audio.
			if s.skippedHeaders < 2 {
				s.skippedHeaders++
				continue
			}
			return packet, nil
		}
		if s.eof {
			if err := s.waitError(); err != nil {
				return nil, err
			}
			return nil, io.EOF
		}
		n, err := s.stdout.Read(s.readBuf)
		if n > 0 {
			s.demux.Write(s.readBuf[:n])
		}
		if err != nil {
			s.eof = true
		}
	}
}

func (s *FFmpegOpusSource) waitError() error {
	if s.waited {
		return s.waitErr
	}
	s.waited = true
	err := s.cmd.Wait()
	if err == nil {
		return nil
	}
	message := bytes.TrimSpace(s.stderr.Bytes())
	if len(message) > 0 {
		s.waitErr = fmt.Errorf("vaidcord-go: ffmpeg failed: %s", message)
	} else {
		s.waitErr = fmt.Errorf("vaidcord-go: ffmpeg failed: %w", err)
	}
	return s.waitErr
}

// Close terminates ffmpeg if it is still running.
func (s *FFmpegOpusSource) Close() error {
	if s.cmd.Process != nil && !s.waited {
		_ = s.cmd.Process.Kill()
		s.waited = true
		s.waitErr = nil
		_ = s.cmd.Wait()
		s.eof = true
	}
	return nil
}
