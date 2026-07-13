package vaidcord

import (
	"crypto/aes"
	"crypto/cipher"
	"encoding/binary"
	"errors"
	"fmt"

	"golang.org/x/crypto/chacha20poly1305"
	"golang.org/x/crypto/nacl/secretbox"
)

// Voice encryption mode identifiers, matching the strings negotiated on the
// voice gateway.
const (
	VoiceModeAEADAES256GCMRTPSize         = "aead_aes256_gcm_rtpsize"
	VoiceModeAEADXChaCha20Poly1305RTPSize = "aead_xchacha20_poly1305_rtpsize"
	VoiceModeXSalsa20Poly1305LiteRTPSize  = "xsalsa20_poly1305_lite_rtpsize"
)

// ErrVoiceDecryption is returned when an inbound voice packet fails
// authentication/decryption.
var ErrVoiceDecryption = errors.New("vaidcord-go: voice packet authentication failed")

// VoiceBox seals outbound and opens inbound RTP payloads for one session
// key. For every mode the wire format is
//
//	unencrypted RTP prefix || ciphertext || 4-byte big-endian nonce counter
//
// and the AEAD modes authenticate the unencrypted prefix as associated data.
type VoiceBox interface {
	// Mode returns the encryption mode identifier.
	Mode() string
	// Seal encrypts plaintext; the result is ciphertext || nonce4 to append
	// after header on the wire.
	Seal(header, plaintext []byte, nonceCounter uint32) []byte
	// Open decrypts ciphertext given the unencrypted prefix and the 4-byte
	// nonce suffix.
	Open(header, ciphertext, nonce4 []byte) ([]byte, error)
}

// OpenVoicePacket parses and decrypts a full inbound RTP datagram. It
// returns the parsed packet and the decrypted media payload with any
// header-extension words already stripped.
func OpenVoicePacket(box VoiceBox, datagram []byte) (RTPPacket, []byte, error) {
	packet, err := ParseRTPPacket(datagram)
	if err != nil {
		return packet, nil, err
	}
	if len(packet.Payload) < 4 {
		return packet, nil, fmt.Errorf("%w: encrypted RTP payload too short for nonce suffix", ErrVoiceDecryption)
	}
	ciphertext := packet.Payload[:len(packet.Payload)-4]
	nonce4 := packet.Payload[len(packet.Payload)-4:]
	plaintext, err := box.Open(packet.Header, ciphertext, nonce4)
	if err != nil {
		return packet, nil, err
	}
	return packet, StripHeaderExtension(packet, plaintext), nil
}

// SupportedEncryptionModes lists the transport encryption modes this SDK
// implements, most preferred first.
func SupportedEncryptionModes() []string {
	return []string{
		VoiceModeAEADAES256GCMRTPSize,
		VoiceModeAEADXChaCha20Poly1305RTPSize,
		VoiceModeXSalsa20Poly1305LiteRTPSize,
	}
}

// CreateVoiceBox builds the VoiceBox for a negotiated mode and 32-byte
// session key.
func CreateVoiceBox(mode string, secretKey []byte) (VoiceBox, error) {
	if len(secretKey) != 32 {
		return nil, fmt.Errorf("vaidcord-go: voice secret key must be 32 bytes, got %d", len(secretKey))
	}
	key := make([]byte, 32)
	copy(key, secretKey)
	switch mode {
	case VoiceModeAEADAES256GCMRTPSize:
		block, err := aes.NewCipher(key)
		if err != nil {
			return nil, err
		}
		aead, err := cipher.NewGCM(block)
		if err != nil {
			return nil, err
		}
		return &aeadVoiceBox{mode: mode, aead: aead, nonceSize: 12}, nil
	case VoiceModeAEADXChaCha20Poly1305RTPSize:
		aead, err := chacha20poly1305.NewX(key)
		if err != nil {
			return nil, err
		}
		return &aeadVoiceBox{mode: mode, aead: aead, nonceSize: chacha20poly1305.NonceSizeX}, nil
	case VoiceModeXSalsa20Poly1305LiteRTPSize:
		var boxed [32]byte
		copy(boxed[:], key)
		return &secretboxVoiceBox{key: boxed}, nil
	default:
		return nil, fmt.Errorf("vaidcord-go: unsupported voice encryption mode: %s", mode)
	}
}

func nonceFromCounter(counter uint32, size int) []byte {
	nonce := make([]byte, size)
	binary.BigEndian.PutUint32(nonce[:4], counter)
	return nonce
}

func nonceFromSuffix(nonce4 []byte, size int) []byte {
	nonce := make([]byte, size)
	copy(nonce[:4], nonce4)
	return nonce
}

// aeadVoiceBox serves both AEAD modes (AES256-GCM with a 12-byte nonce,
// XChaCha20-Poly1305 with a 24-byte nonce). The AEAD nonce is the 4-byte
// big-endian counter zero-padded to the nonce size; AAD is the unencrypted
// RTP prefix.
type aeadVoiceBox struct {
	mode      string
	aead      cipher.AEAD
	nonceSize int
}

func (b *aeadVoiceBox) Mode() string { return b.mode }

func (b *aeadVoiceBox) Seal(header, plaintext []byte, nonceCounter uint32) []byte {
	nonce := nonceFromCounter(nonceCounter, b.nonceSize)
	sealed := b.aead.Seal(nil, nonce, plaintext, header)
	return append(sealed, nonce[:4]...)
}

func (b *aeadVoiceBox) Open(header, ciphertext, nonce4 []byte) ([]byte, error) {
	if len(nonce4) != 4 {
		return nil, fmt.Errorf("%w: nonce suffix must be 4 bytes", ErrVoiceDecryption)
	}
	plaintext, err := b.aead.Open(nil, nonceFromSuffix(nonce4, b.nonceSize), ciphertext, header)
	if err != nil {
		return nil, fmt.Errorf("%w: %s", ErrVoiceDecryption, b.mode)
	}
	return plaintext, nil
}

// secretboxVoiceBox implements the legacy xsalsa20_poly1305_lite_rtpsize
// mode. Secretbox has no AAD; the 24-byte nonce is the 4-byte counter
// zero-padded.
type secretboxVoiceBox struct {
	key [32]byte
}

func (b *secretboxVoiceBox) Mode() string { return VoiceModeXSalsa20Poly1305LiteRTPSize }

func (b *secretboxVoiceBox) Seal(_, plaintext []byte, nonceCounter uint32) []byte {
	var nonce [24]byte
	binary.BigEndian.PutUint32(nonce[:4], nonceCounter)
	sealed := secretbox.Seal(nil, plaintext, &nonce, &b.key)
	return append(sealed, nonce[:4]...)
}

func (b *secretboxVoiceBox) Open(_, ciphertext, nonce4 []byte) ([]byte, error) {
	if len(nonce4) != 4 {
		return nil, fmt.Errorf("%w: nonce suffix must be 4 bytes", ErrVoiceDecryption)
	}
	var nonce [24]byte
	copy(nonce[:4], nonce4)
	plaintext, ok := secretbox.Open(nil, ciphertext, &nonce, &b.key)
	if !ok {
		return nil, fmt.Errorf("%w: %s", ErrVoiceDecryption, VoiceModeXSalsa20Poly1305LiteRTPSize)
	}
	return plaintext, nil
}
