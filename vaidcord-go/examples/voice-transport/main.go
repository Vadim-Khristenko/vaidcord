// Example voice-transport: a no-network tour of the voice wire format.
//
// Demonstrates the exact packet layout used on Discord's voice UDP
// transport — identical across the Python, Rust and Go SDKs:
//
//	packet = RTP header || ciphertext || 4-byte big-endian nonce counter
//
// for every _rtpsize encryption mode, plus IP discovery packets and RTP
// parsing, entirely offline.
package main

import (
	"encoding/hex"
	"fmt"
	"log"

	vaidcord "github.com/Vadim-Khristenko/vaidcord/vaidcord-go"
)

func main() {
	secretKey := make([]byte, 32) // in production: op 4 session description
	for i := range secretKey {
		secretKey[i] = byte(i)
	}

	fmt.Println("== Transport encryption (seal -> wire bytes -> open) ==")
	for _, mode := range vaidcord.SupportedEncryptionModes() {
		box, err := vaidcord.CreateVoiceBox(mode, secretKey)
		if err != nil {
			log.Fatal(err)
		}

		// One 20 ms opus frame at sequence 1, timestamp 960, ssrc 7.
		header := vaidcord.BuildRTPHeader(0x78, 1, 960, 7)
		opusFrame := []byte("fake opus frame")
		nonceCounter := uint32(1234)

		sealed := box.Seal(header, opusFrame, nonceCounter)
		datagram := append(append([]byte{}, header...), sealed...)
		fmt.Printf("\n%s\n  datagram: %s\n", mode, hex.EncodeToString(datagram))

		// The receiving side: parse, authenticate, decrypt.
		packet, plaintext, err := vaidcord.OpenVoicePacket(box, datagram)
		if err != nil {
			log.Fatal(err)
		}
		fmt.Printf("  opened:   ssrc=%d seq=%d ts=%d payload=%q\n",
			packet.SSRC, packet.Sequence, packet.Timestamp, plaintext)

		// Tampering with the authenticated RTP prefix must fail (AEAD modes).
		tampered := append([]byte{}, datagram...)
		tampered[8] ^= 0xFF
		if _, _, err := vaidcord.OpenVoicePacket(box, tampered); err != nil {
			fmt.Printf("  tamper:   rejected (%v)\n", err)
		} else {
			fmt.Println("  tamper:   accepted (secretbox does not authenticate the header)")
		}
	}

	fmt.Println("\n== IP discovery (74-byte packets) ==")
	discovery := vaidcord.BuildIPDiscoveryPacket(0xDEADBEEF)
	fmt.Printf("request:  %s...\n", hex.EncodeToString(discovery[:16]))

	// Simulate the server's answer.
	response := append([]byte{}, discovery...)
	response[1] = 2 // type: response
	copy(response[8:], "203.0.113.5\x00")
	response[72], response[73] = 0xC3, 0x54 // port 50004
	address, port, err := vaidcord.ParseIPDiscoveryResponse(response)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("response: external address %s:%d\n", address, port)

	fmt.Println("\n== Opus passthrough source ==")
	source := vaidcord.NewOpusPacketSource([]byte{0x01}, []byte{0x02}, vaidcord.OpusSilenceFrame)
	for {
		frame, err := source.ReadOpus()
		if err != nil {
			break
		}
		fmt.Printf("frame: %x\n", frame)
	}
	fmt.Println("\nWith a live VoiceConnection this is: conn.Play(ctx, source)")
}
