package vaidcord

import (
	"bytes"
	"context"
	"io"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

// buildOggPage assembles a minimal Ogg page carrying the given packets.
// Packets longer than 255 bytes get split into 255-byte laces with a final
// short lace, per the Ogg framing spec.
func buildOggPage(packets ...[]byte) []byte {
	var lacing []byte
	var body []byte
	for _, packet := range packets {
		remaining := packet
		for len(remaining) >= 255 {
			lacing = append(lacing, 255)
			body = append(body, remaining[:255]...)
			remaining = remaining[255:]
		}
		lacing = append(lacing, byte(len(remaining)))
		body = append(body, remaining...)
	}
	page := []byte("OggS")
	page = append(page, make([]byte, 22)...) // version..crc placeholders
	page = append(page, byte(len(lacing)))
	page = append(page, lacing...)
	page = append(page, body...)
	return page
}

func TestOggDemuxerYieldsPackets(t *testing.T) {
	var demux OggDemuxer
	demux.Write(buildOggPage([]byte("first"), []byte("second")))

	packet, ok := demux.NextPacket()
	if !ok || string(packet) != "first" {
		t.Fatalf("unexpected packet: %q %v", packet, ok)
	}
	packet, ok = demux.NextPacket()
	if !ok || string(packet) != "second" {
		t.Fatalf("unexpected packet: %q %v", packet, ok)
	}
	if _, ok := demux.NextPacket(); ok {
		t.Fatal("no more packets expected")
	}
}

func TestOggDemuxerHandlesChunkedWritesAndGarbage(t *testing.T) {
	var demux OggDemuxer
	page := buildOggPage([]byte("payload-a"), []byte("payload-b"))
	stream := append([]byte("garbage-before"), page...)
	// Feed one byte at a time to stress the incremental parser.
	for _, b := range stream {
		demux.Write([]byte{b})
	}
	var got []string
	for {
		packet, ok := demux.NextPacket()
		if !ok {
			break
		}
		got = append(got, string(packet))
	}
	if len(got) != 2 || got[0] != "payload-a" || got[1] != "payload-b" {
		t.Fatalf("unexpected packets: %v", got)
	}
}

func TestOggDemuxerReassemblesLongPackets(t *testing.T) {
	long := bytes.Repeat([]byte{0xAB}, 600) // 255+255+90 lacing
	var demux OggDemuxer
	demux.Write(buildOggPage(long, []byte("tail")))

	packet, ok := demux.NextPacket()
	if !ok || !bytes.Equal(packet, long) {
		t.Fatalf("long packet not reassembled (len=%d, ok=%v)", len(packet), ok)
	}
	packet, ok = demux.NextPacket()
	if !ok || string(packet) != "tail" {
		t.Fatalf("unexpected trailing packet: %q", packet)
	}
}

func TestOggDemuxerMultiplePages(t *testing.T) {
	var demux OggDemuxer
	demux.Write(buildOggPage([]byte("page1-packet")))
	demux.Write(buildOggPage([]byte("page2-packet")))
	first, _ := demux.NextPacket()
	second, _ := demux.NextPacket()
	if string(first) != "page1-packet" || string(second) != "page2-packet" {
		t.Fatalf("unexpected packets: %q %q", first, second)
	}
}

func ffmpegAvailable() bool {
	_, err := exec.LookPath("ffmpeg")
	return err == nil
}

// TestFFmpegOpusSource pipes a generated tone through ffmpeg and checks the
// demuxed opus packet stream (headers skipped, ~24-26 packets for 0.5s).
func TestFFmpegOpusSource(t *testing.T) {
	if !ffmpegAvailable() {
		t.Skip("ffmpeg not available")
	}
	toneWav := filepath.Join(t.TempDir(), "tone.wav")
	generate := exec.Command(
		"ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
		"-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
		"-ac", "2", "-ar", "48000", toneWav,
	)
	if output, err := generate.CombinedOutput(); err != nil {
		t.Fatalf("ffmpeg tone generation failed: %v (%s)", err, output)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	source, err := NewFFmpegOpusSource(ctx, toneWav)
	if err != nil {
		t.Fatal(err)
	}
	defer source.Close()

	packets := 0
	for {
		packet, err := source.ReadOpus()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		if len(packet) == 0 {
			t.Fatal("empty opus packet")
		}
		// Opus packets must not still look like Ogg headers.
		if bytes.HasPrefix(packet, []byte("OpusHead")) || bytes.HasPrefix(packet, []byte("OpusTags")) {
			t.Fatal("header packet leaked into the audio stream")
		}
		packets++
	}
	if packets < 20 || packets > 30 {
		t.Fatalf("expected ~25 packets for 0.5s of audio, got %d", packets)
	}
}

func TestFFmpegOpusSourceReportsFailure(t *testing.T) {
	if !ffmpegAvailable() {
		t.Skip("ffmpeg not available")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	source, err := NewFFmpegOpusSource(ctx, filepath.Join(t.TempDir(), "missing.wav"))
	if err != nil {
		t.Fatal(err)
	}
	defer source.Close()
	if _, err := source.ReadOpus(); err == nil || err == io.EOF {
		t.Fatalf("expected ffmpeg failure, got %v", err)
	}
}
