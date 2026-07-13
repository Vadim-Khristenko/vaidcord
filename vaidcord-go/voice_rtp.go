package vaidcord

import (
	"encoding/binary"
	"fmt"
)

// RTPHeaderSize is the fixed RTP header length (before CSRCs/extensions).
const RTPHeaderSize = 12

// RTPPacket is a parsed (still encrypted) RTP packet.
//
// Header is the unencrypted prefix as defined by the _rtpsize encryption
// modes: the fixed 12-byte header, any CSRC entries, and — when the
// extension bit is set — the 4-byte extension profile/length preamble.
// Payload is everything after that prefix (ciphertext + nonce suffix for
// encrypted transports).
type RTPPacket struct {
	Version     int
	Padding     bool
	Extension   bool
	Marker      bool
	PayloadType byte
	Sequence    uint16
	Timestamp   uint32
	SSRC        uint32
	CSRCs       []uint32
	Header      []byte
	Payload     []byte
}

// IsRTCPPacket reports whether the datagram is RTCP (SR=200 … APP=204 in the
// full second byte).
func IsRTCPPacket(data []byte) bool {
	return len(data) >= 2 && data[1] >= 200 && data[1] <= 204
}

// ParseRTPPacket splits a raw datagram into the unencrypted RTP prefix and
// the (possibly encrypted) payload.
func ParseRTPPacket(data []byte) (RTPPacket, error) {
	var packet RTPPacket
	if len(data) < RTPHeaderSize {
		return packet, fmt.Errorf("vaidcord-go: RTP packet too short: %d bytes", len(data))
	}
	first := data[0]
	second := data[1]
	packet.Version = int(first >> 6)
	packet.Padding = first&0x20 != 0
	packet.Extension = first&0x10 != 0
	csrcCount := int(first & 0x0F)
	packet.Marker = second&0x80 != 0
	packet.PayloadType = second & 0x7F
	packet.Sequence = binary.BigEndian.Uint16(data[2:4])
	packet.Timestamp = binary.BigEndian.Uint32(data[4:8])
	packet.SSRC = binary.BigEndian.Uint32(data[8:12])

	offset := RTPHeaderSize
	if len(data) < offset+csrcCount*4 {
		return packet, fmt.Errorf("vaidcord-go: RTP packet truncated inside CSRC list")
	}
	if csrcCount > 0 {
		packet.CSRCs = make([]uint32, csrcCount)
		for index := range packet.CSRCs {
			packet.CSRCs[index] = binary.BigEndian.Uint32(data[offset : offset+4])
			offset += 4
		}
	}
	if packet.Extension {
		if len(data) < offset+4 {
			return packet, fmt.Errorf("vaidcord-go: RTP packet truncated inside extension preamble")
		}
		offset += 4
	}
	packet.Header = data[:offset]
	packet.Payload = data[offset:]
	return packet, nil
}

// StripHeaderExtension drops the decrypted header-extension words from
// plaintext. In the _rtpsize modes the 4-byte extension preamble stays in
// the clear (as part of RTPPacket.Header) while the extension words
// themselves are encrypted at the start of the payload.
func StripHeaderExtension(packet RTPPacket, plaintext []byte) []byte {
	if !packet.Extension {
		return plaintext
	}
	extWords := int(binary.BigEndian.Uint16(packet.Header[len(packet.Header)-2:]))
	if extWords*4 > len(plaintext) {
		return nil
	}
	return plaintext[extWords*4:]
}

// BuildRTPHeader assembles a 12-byte RTP header (version 2, no padding, no
// extension, no CSRCs).
func BuildRTPHeader(payloadType byte, sequence uint16, timestamp uint32, ssrc uint32) []byte {
	header := make([]byte, RTPHeaderSize)
	header[0] = 0x80
	header[1] = payloadType & 0x7F
	binary.BigEndian.PutUint16(header[2:4], sequence)
	binary.BigEndian.PutUint32(header[4:8], timestamp)
	binary.BigEndian.PutUint32(header[8:12], ssrc)
	return header
}
