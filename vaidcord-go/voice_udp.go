package vaidcord

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"net"
	"strconv"
	"time"
)

// BuildIPDiscoveryPacket assembles the 74-byte voice IP discovery request
// (type=1, length=70, ssrc, 64-byte address field, 2-byte port).
func BuildIPDiscoveryPacket(ssrc uint32) []byte {
	packet := make([]byte, 74)
	binary.BigEndian.PutUint16(packet[0:2], 1)
	binary.BigEndian.PutUint16(packet[2:4], 70)
	binary.BigEndian.PutUint32(packet[4:8], ssrc)
	return packet
}

// ParseIPDiscoveryResponse extracts the public address and port from a
// 74-byte IP discovery response (type=2).
func ParseIPDiscoveryResponse(packet []byte) (string, int, error) {
	if len(packet) < 74 {
		return "", 0, fmt.Errorf("vaidcord-go: voice IP discovery response must be at least 74 bytes, got %d", len(packet))
	}
	responseType := binary.BigEndian.Uint16(packet[0:2])
	length := binary.BigEndian.Uint16(packet[2:4])
	if responseType != 2 || length != 70 {
		return "", 0, fmt.Errorf("vaidcord-go: invalid voice IP discovery response header (type=%d, length=%d)", responseType, length)
	}
	rawAddress := packet[8:72]
	if index := bytes.IndexByte(rawAddress, 0); index >= 0 {
		rawAddress = rawAddress[:index]
	}
	port := binary.BigEndian.Uint16(packet[72:74])
	return string(rawAddress), int(port), nil
}

// VoiceUDPConn is the UDP media transport for one voice connection.
type VoiceUDPConn struct {
	conn *net.UDPConn
}

// DialVoiceUDP connects a UDP socket to the voice server announced in the
// voice READY payload.
func DialVoiceUDP(ip string, port int) (*VoiceUDPConn, error) {
	addr, err := net.ResolveUDPAddr("udp", net.JoinHostPort(ip, strconv.Itoa(port)))
	if err != nil {
		return nil, err
	}
	conn, err := net.DialUDP("udp", nil, addr)
	if err != nil {
		return nil, err
	}
	return &VoiceUDPConn{conn: conn}, nil
}

// Send writes one datagram.
func (u *VoiceUDPConn) Send(data []byte) error {
	_, err := u.conn.Write(data)
	return err
}

// Receive reads one datagram into buf and returns the filled slice. A zero
// timeout blocks indefinitely.
func (u *VoiceUDPConn) Receive(buf []byte, timeout time.Duration) ([]byte, error) {
	if timeout > 0 {
		if err := u.conn.SetReadDeadline(time.Now().Add(timeout)); err != nil {
			return nil, err
		}
	} else if err := u.conn.SetReadDeadline(time.Time{}); err != nil {
		return nil, err
	}
	n, err := u.conn.Read(buf)
	if err != nil {
		return nil, err
	}
	return buf[:n], nil
}

// DiscoverIP performs the 74-byte IP discovery round trip and returns the
// external address/port Discord sees for this socket.
func (u *VoiceUDPConn) DiscoverIP(ssrc uint32, timeout time.Duration) (string, int, error) {
	if timeout <= 0 {
		timeout = 5 * time.Second
	}
	if err := u.Send(BuildIPDiscoveryPacket(ssrc)); err != nil {
		return "", 0, err
	}
	buf := make([]byte, 128)
	deadline := time.Now().Add(timeout)
	for {
		remaining := time.Until(deadline)
		if remaining <= 0 {
			return "", 0, fmt.Errorf("vaidcord-go: voice IP discovery timed out")
		}
		data, err := u.Receive(buf, remaining)
		if err != nil {
			return "", 0, err
		}
		address, port, err := ParseIPDiscoveryResponse(data)
		if err != nil {
			// Not the discovery response (e.g. an early media packet); keep
			// waiting until the deadline.
			continue
		}
		return address, port, nil
	}
}

// LocalAddr exposes the local UDP address.
func (u *VoiceUDPConn) LocalAddr() net.Addr { return u.conn.LocalAddr() }

// Close tears down the socket.
func (u *VoiceUDPConn) Close() error { return u.conn.Close() }
