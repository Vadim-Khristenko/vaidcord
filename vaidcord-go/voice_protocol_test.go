package vaidcord

import (
	"bytes"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"testing"
)

// makeRTPHeader mirrors the helper in the Python SDK's test_voice_protocol.py
// so the two test suites exercise identical wire bytes.
func makeRTPHeader(t *testing.T, sequence uint16, timestamp uint32, ssrc uint32, extension bool) []byte {
	t.Helper()
	first := byte(0x80)
	if extension {
		first |= 0x10
	}
	header := make([]byte, 12)
	header[0] = first
	header[1] = 0x78
	binary.BigEndian.PutUint16(header[2:4], sequence)
	binary.BigEndian.PutUint32(header[4:8], timestamp)
	binary.BigEndian.PutUint32(header[8:12], ssrc)
	if extension {
		ext := make([]byte, 4)
		binary.BigEndian.PutUint16(ext[0:2], 0xBEDE)
		binary.BigEndian.PutUint16(ext[2:4], 1) // one 4-byte extension word
		header = append(header, ext...)
	}
	return header
}

func defaultRTPHeader(t *testing.T) []byte {
	return makeRTPHeader(t, 1, 960, 7, false)
}

func testSecretKey() []byte {
	key := make([]byte, 32)
	for i := range key {
		key[i] = byte(i)
	}
	return key
}

// --------------------------------------------------------------------- //
// RTP parsing                                                           //
// --------------------------------------------------------------------- //

func TestParseRTPPacketBasicFields(t *testing.T) {
	data := append(makeRTPHeader(t, 42, 1920, 99, false), []byte("payload")...)
	packet, err := ParseRTPPacket(data)
	if err != nil {
		t.Fatal(err)
	}
	if packet.Version != 2 {
		t.Fatalf("unexpected version: %d", packet.Version)
	}
	if packet.PayloadType != 0x78 {
		t.Fatalf("unexpected payload type: %#x", packet.PayloadType)
	}
	if packet.Sequence != 42 || packet.Timestamp != 1920 || packet.SSRC != 99 {
		t.Fatalf("unexpected header fields: %+v", packet)
	}
	if !bytes.Equal(packet.Header, data[:12]) {
		t.Fatalf("unexpected header slice: %x", packet.Header)
	}
	if string(packet.Payload) != "payload" {
		t.Fatalf("unexpected payload: %q", packet.Payload)
	}
}

func TestParseRTPPacketWithExtensionPreamble(t *testing.T) {
	data := append(makeRTPHeader(t, 1, 960, 7, true), []byte("rest")...)
	packet, err := ParseRTPPacket(data)
	if err != nil {
		t.Fatal(err)
	}
	if !packet.Extension {
		t.Fatal("extension bit not detected")
	}
	if len(packet.Header) != 16 {
		t.Fatalf("unexpected header length: %d", len(packet.Header))
	}
	if string(packet.Payload) != "rest" {
		t.Fatalf("unexpected payload: %q", packet.Payload)
	}
	// one extension word (4 bytes) is stripped from the decrypted payload
	if got := StripHeaderExtension(packet, []byte("WORDopus")); string(got) != "opus" {
		t.Fatalf("unexpected stripped payload: %q", got)
	}
}

func TestRTCPDetection(t *testing.T) {
	rtcp := append([]byte{0x80, 201}, make([]byte, 6)...)
	if !IsRTCPPacket(rtcp) {
		t.Fatal("RTCP packet not detected")
	}
	if IsRTCPPacket(append(defaultRTPHeader(t), 'x')) {
		t.Fatal("RTP packet misclassified as RTCP")
	}
}

func TestParseRTPPacketRejectsShortInput(t *testing.T) {
	if _, err := ParseRTPPacket([]byte{0x80, 0x78}); err == nil {
		t.Fatal("expected error for short packet")
	}
	truncated := makeRTPHeader(t, 1, 960, 7, true)[:14]
	if _, err := ParseRTPPacket(truncated); err == nil {
		t.Fatal("expected error for truncated extension preamble")
	}
}

func TestBuildRTPHeaderMatchesParse(t *testing.T) {
	header := BuildRTPHeader(0x78, 9, 4800, 321)
	if !bytes.Equal(header, makeRTPHeader(t, 9, 4800, 321, false)) {
		t.Fatalf("BuildRTPHeader mismatch: %x", header)
	}
}

// --------------------------------------------------------------------- //
// Transport encryption                                                  //
// --------------------------------------------------------------------- //

func TestVoiceBoxSealOpenRoundtrip(t *testing.T) {
	for _, mode := range SupportedEncryptionModes() {
		t.Run(mode, func(t *testing.T) {
			box, err := CreateVoiceBox(mode, testSecretKey())
			if err != nil {
				t.Fatal(err)
			}
			header := defaultRTPHeader(t)
			sealed := box.Seal(header, []byte("opus data"), 1234)
			packet, payload, err := OpenVoicePacket(box, append(append([]byte{}, header...), sealed...))
			if err != nil {
				t.Fatal(err)
			}
			if string(payload) != "opus data" {
				t.Fatalf("unexpected payload: %q", payload)
			}
			if packet.SSRC != 7 {
				t.Fatalf("unexpected ssrc: %d", packet.SSRC)
			}
		})
	}
}

// TestVoiceBoxWireCompatibilityWithPython pins the exact datagrams produced
// by the Python SDK (vaidcord-py) for key=bytes(range(32)), header
// (seq=1, ts=960, ssrc=7), plaintext "opus data", nonce counter 1234. Both
// SDKs must remain byte-for-byte compatible.
func TestVoiceBoxWireCompatibilityWithPython(t *testing.T) {
	vectors := map[string]string{
		VoiceModeAEADAES256GCMRTPSize:         "80780001000003c0000000078641932b87e46e6c42cb696cc17b5e165566e1acc638f0f3f1000004d2",
		VoiceModeAEADXChaCha20Poly1305RTPSize: "80780001000003c00000000792df0c1bc738f2a047778ff92b6a374704ef5d31cbdf0de501000004d2",
		VoiceModeXSalsa20Poly1305LiteRTPSize:  "80780001000003c000000007db506a0b1857e425d0644e0d56efc188cbac1c3bf393c9d50e000004d2",
	}
	for mode, expectedHex := range vectors {
		t.Run(mode, func(t *testing.T) {
			box, err := CreateVoiceBox(mode, testSecretKey())
			if err != nil {
				t.Fatal(err)
			}
			header := defaultRTPHeader(t)
			datagram := append(append([]byte{}, header...), box.Seal(header, []byte("opus data"), 1234)...)
			if got := hex.EncodeToString(datagram); got != expectedHex {
				t.Fatalf("sealed datagram diverges from Python SDK:\n got %s\nwant %s", got, expectedHex)
			}
			expected, err := hex.DecodeString(expectedHex)
			if err != nil {
				t.Fatal(err)
			}
			_, payload, err := OpenVoicePacket(box, expected)
			if err != nil {
				t.Fatal(err)
			}
			if string(payload) != "opus data" {
				t.Fatalf("failed to open Python-sealed packet: %q", payload)
			}
		})
	}
}

func TestVoiceBoxRejectsTamperedHeader(t *testing.T) {
	for _, mode := range []string{VoiceModeAEADAES256GCMRTPSize, VoiceModeAEADXChaCha20Poly1305RTPSize} {
		t.Run(mode, func(t *testing.T) {
			box, err := CreateVoiceBox(mode, testSecretKey())
			if err != nil {
				t.Fatal(err)
			}
			header := defaultRTPHeader(t)
			sealed := box.Seal(header, []byte("opus data"), 1)
			tampered := append(append([]byte{}, header...), sealed...)
			tampered[8] ^= 0xFF // flip a bit inside the authenticated SSRC field
			if _, _, err := OpenVoicePacket(box, tampered); !errors.Is(err, ErrVoiceDecryption) {
				t.Fatalf("expected ErrVoiceDecryption, got %v", err)
			}
		})
	}
}

func TestVoiceBoxRejectsTamperedCiphertext(t *testing.T) {
	for _, mode := range SupportedEncryptionModes() {
		t.Run(mode, func(t *testing.T) {
			box, err := CreateVoiceBox(mode, testSecretKey())
			if err != nil {
				t.Fatal(err)
			}
			header := defaultRTPHeader(t)
			sealed := box.Seal(header, []byte("opus data"), 1)
			tampered := append(append([]byte{}, header...), sealed...)
			tampered[len(header)+2] ^= 0xFF
			if _, _, err := OpenVoicePacket(box, tampered); !errors.Is(err, ErrVoiceDecryption) {
				t.Fatalf("expected ErrVoiceDecryption, got %v", err)
			}
		})
	}
}

func TestVoiceBoxStripsEncryptedExtensionWords(t *testing.T) {
	box, err := CreateVoiceBox(VoiceModeAEADAES256GCMRTPSize, testSecretKey())
	if err != nil {
		t.Fatal(err)
	}
	header := makeRTPHeader(t, 1, 960, 7, true)
	sealed := box.Seal(header, append([]byte("EXT!"), []byte("opus data")...), 7)
	_, payload, err := OpenVoicePacket(box, append(append([]byte{}, header...), sealed...))
	if err != nil {
		t.Fatal(err)
	}
	if string(payload) != "opus data" {
		t.Fatalf("unexpected payload after extension strip: %q", payload)
	}
}

func TestVoiceBoxOpenRejectsShortPayload(t *testing.T) {
	box, err := CreateVoiceBox(VoiceModeAEADAES256GCMRTPSize, testSecretKey())
	if err != nil {
		t.Fatal(err)
	}
	short := append(defaultRTPHeader(t), 0x01, 0x02)
	if _, _, err := OpenVoicePacket(box, short); !errors.Is(err, ErrVoiceDecryption) {
		t.Fatalf("expected ErrVoiceDecryption for short payload, got %v", err)
	}
}

func TestCreateVoiceBoxUnknownMode(t *testing.T) {
	if _, err := CreateVoiceBox("xsalsa20_poly1305", testSecretKey()); err == nil {
		t.Fatal("expected error for unsupported mode")
	}
	if _, err := CreateVoiceBox(VoiceModeAEADAES256GCMRTPSize, make([]byte, 16)); err == nil {
		t.Fatal("expected error for short key")
	}
}

func TestSupportedModesCoverDiscordRequiredSet(t *testing.T) {
	modes := SupportedEncryptionModes()
	found := map[string]bool{}
	for _, mode := range modes {
		found[mode] = true
	}
	if !found[VoiceModeAEADAES256GCMRTPSize] || !found[VoiceModeAEADXChaCha20Poly1305RTPSize] {
		t.Fatalf("required encryption modes missing: %v", modes)
	}
}

// --------------------------------------------------------------------- //
// IP discovery                                                          //
// --------------------------------------------------------------------- //

func TestBuildIPDiscoveryPacket(t *testing.T) {
	packet := BuildIPDiscoveryPacket(0xDEADBEEF)
	if len(packet) != 74 {
		t.Fatalf("discovery packet must be 74 bytes, got %d", len(packet))
	}
	if binary.BigEndian.Uint16(packet[0:2]) != 1 || binary.BigEndian.Uint16(packet[2:4]) != 70 {
		t.Fatalf("unexpected discovery header: %x", packet[:4])
	}
	if binary.BigEndian.Uint32(packet[4:8]) != 0xDEADBEEF {
		t.Fatalf("unexpected ssrc: %x", packet[4:8])
	}
}

func TestParseIPDiscoveryResponse(t *testing.T) {
	response := make([]byte, 74)
	binary.BigEndian.PutUint16(response[0:2], 2)
	binary.BigEndian.PutUint16(response[2:4], 70)
	binary.BigEndian.PutUint32(response[4:8], 123)
	copy(response[8:], "203.0.113.5\x00")
	binary.BigEndian.PutUint16(response[72:74], 50004)

	address, port, err := ParseIPDiscoveryResponse(response)
	if err != nil {
		t.Fatal(err)
	}
	if address != "203.0.113.5" || port != 50004 {
		t.Fatalf("unexpected discovery result: %s:%d", address, port)
	}

	if _, _, err := ParseIPDiscoveryResponse(response[:40]); err == nil {
		t.Fatal("expected error for short response")
	}
	bad := append([]byte{}, response...)
	binary.BigEndian.PutUint16(bad[0:2], 1) // request type, not response
	if _, _, err := ParseIPDiscoveryResponse(bad); err == nil {
		t.Fatal("expected error for wrong response type")
	}
}

// --------------------------------------------------------------------- //
// Close-code policy                                                     //
// --------------------------------------------------------------------- //

func TestClassifyVoiceCloseCode(t *testing.T) {
	cases := []struct {
		code   int
		action VoiceCloseAction
	}{
		{-1, VoiceCloseActionResume}, // closed without a code
		{1000, VoiceCloseActionResume},
		{1006, VoiceCloseActionResume},
		{4015, VoiceCloseActionResume},
		{4006, VoiceCloseActionRejoin},
		{4009, VoiceCloseActionRejoin},
		{4004, VoiceCloseActionFatal},
		{4014, VoiceCloseActionFatal},
		{4017, VoiceCloseActionFatal},
	}
	for _, testCase := range cases {
		if got := ClassifyVoiceCloseCode(testCase.code); got != testCase.action {
			t.Fatalf("code %d: expected %s, got %s", testCase.code, testCase.action, got)
		}
	}
}
