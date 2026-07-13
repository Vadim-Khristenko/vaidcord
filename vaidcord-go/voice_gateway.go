package vaidcord

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// VoiceSpeakingFlag bits for the op 5 speaking payload.
const (
	VoiceSpeakingMicrophone = 1 << 0
	VoiceSpeakingSoundshare = 1 << 1
	VoiceSpeakingPriority   = 1 << 2
)

// VoiceGatewayConfig tunes the voice websocket client.
type VoiceGatewayConfig struct {
	// Version of the voice gateway protocol (default 8).
	Version int
	// PreferredModes orders encryption-mode negotiation (default AES256-GCM,
	// then XChaCha20-Poly1305).
	PreferredModes []string
	// Dialer overrides the websocket dialer.
	Dialer *websocket.Dialer
	// HandshakeTimeout bounds connect/resume handshakes (default 30s).
	HandshakeTimeout time.Duration
}

func (c VoiceGatewayConfig) withDefaults() VoiceGatewayConfig {
	if c.Version == 0 {
		c.Version = 8
	}
	if len(c.PreferredModes) == 0 {
		c.PreferredModes = []string{
			VoiceModeAEADAES256GCMRTPSize,
			VoiceModeAEADXChaCha20Poly1305RTPSize,
		}
	}
	if c.Dialer == nil {
		c.Dialer = websocket.DefaultDialer
	}
	if c.HandshakeTimeout <= 0 {
		c.HandshakeTimeout = 30 * time.Second
	}
	return c
}

// VoiceServerInfo carries the values gathered from VOICE_STATE_UPDATE +
// VOICE_SERVER_UPDATE that authenticate a voice session.
type VoiceServerInfo struct {
	GuildID   string
	UserID    string
	SessionID string
	Token     string
	Endpoint  string
}

// WebsocketURL normalises the endpoint into a wss:// URL.
func (i VoiceServerInfo) WebsocketURL(version int) string {
	endpoint := strings.TrimPrefix(strings.TrimPrefix(i.Endpoint, "wss://"), "https://")
	scheme := "wss"
	if strings.HasPrefix(i.Endpoint, "ws://") {
		scheme = "ws"
		endpoint = strings.TrimPrefix(i.Endpoint, "ws://")
	}
	return fmt.Sprintf("%s://%s?v=%d&encoding=json", scheme, endpoint, version)
}

// VoiceReady is the op 2 payload.
type VoiceReady struct {
	SSRC  uint32   `json:"ssrc"`
	IP    string   `json:"ip"`
	Port  int      `json:"port"`
	Modes []string `json:"modes"`
}

// SelectMode picks the first preferred mode the server offers, falling back
// to the server's first mode.
func (r VoiceReady) SelectMode(preferred []string) (string, error) {
	available := make(map[string]bool, len(r.Modes))
	for _, mode := range r.Modes {
		available[mode] = true
	}
	for _, mode := range preferred {
		if available[mode] {
			return mode, nil
		}
	}
	if len(r.Modes) > 0 {
		return r.Modes[0], nil
	}
	return "", errors.New("vaidcord-go: voice gateway did not provide encryption modes")
}

// VoiceSessionDescription is the op 4 payload.
type VoiceSessionDescription struct {
	Mode      string `json:"mode"`
	SecretKey []byte `json:"-"`
}

// VoiceFrame is one decrypted inbound audio frame.
type VoiceFrame struct {
	UserID    string
	SSRC      uint32
	Sequence  uint16
	Timestamp uint32
	Opus      []byte
}

// SpeakingCallback receives op 5 speaking events for other users.
type SpeakingCallback func(userID string, ssrc uint32, flags int)

type VoicePayload struct {
	Op   int             `json:"op"`
	Seq  *int            `json:"seq"`
	Data json.RawMessage `json:"d"`
}

// VoiceConnection is a Discord voice gateway (v8) client plus the UDP media
// transport: identify/resume with seq_ack, heartbeats on their own
// goroutine, READY/session-description handshake, IP discovery, transport
// encryption in both directions, and an SSRC->user map fed by op 5.
type VoiceConnection struct {
	info   VoiceServerInfo
	config VoiceGatewayConfig

	writeMu sync.Mutex

	mu                sync.Mutex
	conn              *websocket.Conn
	udp               *VoiceUDPConn
	ready             *VoiceReady
	session           *VoiceSessionDescription
	box               VoiceBox
	seqAck            int
	helloInterval     time.Duration
	lastHeartbeatSent time.Time
	latency           time.Duration
	awaitingACK       bool
	resumed           bool
	ssrcUsers         map[uint32]string
	speakingCallbacks []SpeakingCallback
	closing           bool
	closeReason       error

	rtpSequence  uint16
	rtpTimestamp uint32
	nonceCounter uint32

	heartbeatStop chan struct{}
	done          chan struct{}
	doneOnce      sync.Once
	runErr        error
}

// NewVoiceConnection builds an unconnected voice connection.
func NewVoiceConnection(info VoiceServerInfo, config VoiceGatewayConfig) *VoiceConnection {
	return &VoiceConnection{
		info:      info,
		config:    config.withDefaults(),
		seqAck:    -1,
		ssrcUsers: make(map[uint32]string),
		done:      make(chan struct{}),
	}
}

// Ready returns the op 2 payload once received.
func (v *VoiceConnection) Ready() *VoiceReady {
	v.mu.Lock()
	defer v.mu.Unlock()
	return v.ready
}

// SessionDescription returns the negotiated mode/secret key once received.
func (v *VoiceConnection) SessionDescription() *VoiceSessionDescription {
	v.mu.Lock()
	defer v.mu.Unlock()
	return v.session
}

// Box returns the negotiated transport-encryption strategy, if any.
func (v *VoiceConnection) Box() VoiceBox {
	v.mu.Lock()
	defer v.mu.Unlock()
	return v.box
}

// Latency reports the last voice heartbeat round-trip time.
func (v *VoiceConnection) Latency() time.Duration {
	v.mu.Lock()
	defer v.mu.Unlock()
	return v.latency
}

// SSRCUser resolves an inbound SSRC to the speaking user's id.
func (v *VoiceConnection) SSRCUser(ssrc uint32) (string, bool) {
	v.mu.Lock()
	defer v.mu.Unlock()
	userID, ok := v.ssrcUsers[ssrc]
	return userID, ok
}

// OnSpeaking registers a callback for op 5 speaking events of other users.
func (v *VoiceConnection) OnSpeaking(callback SpeakingCallback) {
	v.mu.Lock()
	defer v.mu.Unlock()
	v.speakingCallbacks = append(v.speakingCallbacks, callback)
}

// Done closes when the connection has permanently ended; Err reports why.
func (v *VoiceConnection) Done() <-chan struct{} { return v.done }

func (v *VoiceConnection) Err() error {
	v.mu.Lock()
	defer v.mu.Unlock()
	return v.runErr
}

// Connect dials the voice gateway, identifies, waits for READY, performs
// UDP IP discovery + SELECT PROTOCOL, waits for the session description and
// then keeps the connection alive in the background (heartbeats, automatic
// resume per close-code policy).
func (v *VoiceConnection) Connect(ctx context.Context) error {
	if err := v.handshake(ctx, false); err != nil {
		v.finish(err)
		return err
	}
	go v.readLoop(ctx)
	return nil
}

func (v *VoiceConnection) handshake(ctx context.Context, resume bool) error {
	handshakeCtx, cancel := context.WithTimeout(ctx, v.config.HandshakeTimeout)
	defer cancel()

	conn, _, err := v.config.Dialer.DialContext(handshakeCtx, v.info.WebsocketURL(v.config.Version), nil)
	if err != nil {
		return err
	}
	v.mu.Lock()
	v.conn = conn
	v.awaitingACK = false
	if !resume {
		v.ready = nil
		v.session = nil
		v.box = nil
	}
	v.resumed = false
	v.mu.Unlock()

	if resume {
		err = v.sendResume()
	} else {
		err = v.sendIdentify()
	}
	if err != nil {
		conn.Close()
		return err
	}

	deadline := time.Now().Add(v.config.HandshakeTimeout)
	_ = conn.SetReadDeadline(deadline)
	defer conn.SetReadDeadline(time.Time{})

	for {
		v.mu.Lock()
		hasReady := v.ready != nil
		hasSession := v.session != nil
		hasResumed := v.resumed
		hasUDP := v.udp != nil
		v.mu.Unlock()
		if resume && (hasResumed || hasSession) {
			v.startHeartbeat()
			return nil
		}
		if !resume && hasReady && !hasUDP {
			if err := v.establishUDP(); err != nil {
				conn.Close()
				return err
			}
		}
		if !resume && hasSession {
			v.startHeartbeat()
			return nil
		}
		payload, err := readVoicePayload(conn)
		if err != nil {
			conn.Close()
			return fmt.Errorf("vaidcord-go: voice handshake failed: %w", err)
		}
		if err := v.HandlePayload(payload); err != nil {
			conn.Close()
			return err
		}
	}
}

// establishUDP dials the media socket, runs IP discovery and answers with
// SELECT PROTOCOL.
func (v *VoiceConnection) establishUDP() error {
	v.mu.Lock()
	ready := v.ready
	v.mu.Unlock()
	if ready == nil {
		return errors.New("vaidcord-go: voice READY payload not received")
	}
	udp, err := DialVoiceUDP(ready.IP, ready.Port)
	if err != nil {
		return err
	}
	address, port, err := udp.DiscoverIP(ready.SSRC, v.config.HandshakeTimeout)
	if err != nil {
		udp.Close()
		return err
	}
	mode, err := ready.SelectMode(v.config.PreferredModes)
	if err != nil {
		udp.Close()
		return err
	}
	v.mu.Lock()
	v.udp = udp
	v.mu.Unlock()
	return v.send(int(VoiceOpSelectProtocol), map[string]any{
		"protocol": "udp",
		"data": map[string]any{
			"address": address,
			"port":    port,
			"mode":    mode,
		},
	})
}

func (v *VoiceConnection) startHeartbeat() {
	v.mu.Lock()
	interval := v.helloInterval
	if v.heartbeatStop != nil {
		close(v.heartbeatStop)
	}
	stop := make(chan struct{})
	v.heartbeatStop = stop
	v.mu.Unlock()
	if interval <= 0 {
		return
	}
	go v.heartbeatLoop(interval, stop)
}

func (v *VoiceConnection) heartbeatLoop(interval time.Duration, stop <-chan struct{}) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-stop:
			return
		case <-ticker.C:
		}
		v.mu.Lock()
		missed := v.awaitingACK
		conn := v.conn
		v.mu.Unlock()
		if missed && conn != nil {
			// Zombied voice connection: recycle it so the read loop resumes.
			v.mu.Lock()
			v.closeReason = ErrMissedHeartbeatACK
			v.mu.Unlock()
			conn.Close()
			return
		}
		if err := v.sendHeartbeat(); err != nil {
			return
		}
	}
}

func (v *VoiceConnection) sendIdentify() error {
	return v.send(int(VoiceOpIdentify), map[string]any{
		"server_id":  v.info.GuildID,
		"user_id":    v.info.UserID,
		"session_id": v.info.SessionID,
		"token":      v.info.Token,
	})
}

func (v *VoiceConnection) sendResume() error {
	v.mu.Lock()
	seqAck := v.seqAck
	v.mu.Unlock()
	return v.send(int(VoiceOpResume), map[string]any{
		"server_id":  v.info.GuildID,
		"session_id": v.info.SessionID,
		"token":      v.info.Token,
		"seq_ack":    seqAck,
	})
}

func (v *VoiceConnection) sendHeartbeat() error {
	v.mu.Lock()
	v.lastHeartbeatSent = time.Now()
	v.awaitingACK = true
	seqAck := v.seqAck
	v.mu.Unlock()
	return v.send(int(VoiceOpHeartbeat), map[string]any{
		"t":       time.Now().UnixMilli(),
		"seq_ack": seqAck,
	})
}

// Speaking sends the op 5 speaking payload (flags 0 = stopped).
func (v *VoiceConnection) Speaking(flags int) error {
	v.mu.Lock()
	ready := v.ready
	v.mu.Unlock()
	if ready == nil {
		return errors.New("vaidcord-go: voice connection is not ready")
	}
	return v.send(int(VoiceOpSpeaking), map[string]any{
		"speaking": flags,
		"delay":    0,
		"ssrc":     ready.SSRC,
	})
}

func (v *VoiceConnection) send(op int, data any) error {
	v.mu.Lock()
	conn := v.conn
	v.mu.Unlock()
	if conn == nil {
		return errors.New("vaidcord-go: voice websocket is not connected")
	}
	v.writeMu.Lock()
	defer v.writeMu.Unlock()
	return conn.WriteJSON(map[string]any{"op": op, "d": data})
}

func readVoicePayload(conn *websocket.Conn) (VoicePayload, error) {
	var payload VoicePayload
	messageType, data, err := conn.ReadMessage()
	if err != nil {
		return payload, err
	}
	if messageType != websocket.TextMessage {
		// v8 binary frames carry DAVE traffic; not handled here.
		payload.Op = -1
		return payload, nil
	}
	err = json.Unmarshal(data, &payload)
	return payload, err
}

// HandlePayload applies one voice gateway payload to the connection state.
// Exported for tests and custom transports.
func (v *VoiceConnection) HandlePayload(payload VoicePayload) error {
	if payload.Seq != nil {
		v.mu.Lock()
		v.seqAck = *payload.Seq
		v.mu.Unlock()
	}
	switch VoiceGatewayOpcode(payload.Op) {
	case VoiceOpHello:
		var hello struct {
			HeartbeatInterval float64 `json:"heartbeat_interval"`
		}
		if err := json.Unmarshal(payload.Data, &hello); err != nil {
			return err
		}
		v.mu.Lock()
		v.helloInterval = time.Duration(hello.HeartbeatInterval * float64(time.Millisecond))
		v.mu.Unlock()
	case VoiceOpReady:
		var ready VoiceReady
		if err := json.Unmarshal(payload.Data, &ready); err != nil {
			return err
		}
		v.mu.Lock()
		v.ready = &ready
		v.mu.Unlock()
	case VoiceOpSessionDescription:
		var description struct {
			Mode      string `json:"mode"`
			SecretKey []int  `json:"secret_key"`
		}
		if err := json.Unmarshal(payload.Data, &description); err != nil {
			return err
		}
		secretKey := make([]byte, len(description.SecretKey))
		for index, value := range description.SecretKey {
			secretKey[index] = byte(value)
		}
		box, err := CreateVoiceBox(description.Mode, secretKey)
		if err != nil {
			return err
		}
		v.mu.Lock()
		v.session = &VoiceSessionDescription{Mode: description.Mode, SecretKey: secretKey}
		v.box = box
		v.mu.Unlock()
	case VoiceOpSpeaking:
		var speaking struct {
			SSRC     uint32 `json:"ssrc"`
			UserID   string `json:"user_id"`
			Speaking int    `json:"speaking"`
		}
		if err := json.Unmarshal(payload.Data, &speaking); err != nil {
			return err
		}
		if speaking.UserID == "" {
			return nil
		}
		v.mu.Lock()
		v.ssrcUsers[speaking.SSRC] = speaking.UserID
		callbacks := append([]SpeakingCallback(nil), v.speakingCallbacks...)
		v.mu.Unlock()
		for _, callback := range callbacks {
			callback(speaking.UserID, speaking.SSRC, speaking.Speaking)
		}
	case VoiceOpHeartbeatAck:
		v.mu.Lock()
		if v.awaitingACK {
			v.awaitingACK = false
			v.latency = time.Since(v.lastHeartbeatSent)
		}
		v.mu.Unlock()
	case VoiceOpResumed:
		v.mu.Lock()
		v.resumed = true
		v.mu.Unlock()
	case VoiceOpVideo:
		// The op 12 video announcement also carries the sender's audio SSRC.
		var connect struct {
			UserID    string `json:"user_id"`
			AudioSSRC uint32 `json:"audio_ssrc"`
		}
		if err := json.Unmarshal(payload.Data, &connect); err == nil && connect.UserID != "" && connect.AudioSSRC != 0 {
			v.mu.Lock()
			v.ssrcUsers[connect.AudioSSRC] = connect.UserID
			v.mu.Unlock()
		}
	case VoiceOpClientDisconnect:
		var disconnect struct {
			UserID string `json:"user_id"`
		}
		if err := json.Unmarshal(payload.Data, &disconnect); err == nil && disconnect.UserID != "" {
			v.mu.Lock()
			for ssrc, userID := range v.ssrcUsers {
				if userID == disconnect.UserID {
					delete(v.ssrcUsers, ssrc)
				}
			}
			v.mu.Unlock()
		}
	}
	return nil
}

// readLoop keeps consuming the websocket after the handshake, driving the
// reconnect policy when the socket closes.
func (v *VoiceConnection) readLoop(ctx context.Context) {
	backoff := time.Second
	for {
		v.mu.Lock()
		conn := v.conn
		closing := v.closing
		v.mu.Unlock()
		if closing || conn == nil {
			v.finish(nil)
			return
		}

		payload, err := readVoicePayload(conn)
		if err == nil {
			if payload.Op >= 0 {
				if handleErr := v.HandlePayload(payload); handleErr != nil {
					v.finish(handleErr)
					return
				}
			}
			backoff = time.Second
			continue
		}

		v.mu.Lock()
		closing = v.closing
		reason := v.closeReason
		v.closeReason = nil
		v.mu.Unlock()
		if closing || ctx.Err() != nil {
			v.finish(ctx.Err())
			return
		}

		code := -1
		var closeErr *websocket.CloseError
		if errors.As(err, &closeErr) {
			code = closeErr.Code
		}
		action := ClassifyVoiceCloseCode(code)
		if reason != nil {
			// Missed heartbeat ACK: always worth a resume.
			action = VoiceCloseActionResume
		}
		if action != VoiceCloseActionResume {
			v.finish(&VoiceClosedError{Code: code, Action: action})
			return
		}
		if err := sleepContext(ctx, jitter(backoff)); err != nil {
			v.finish(err)
			return
		}
		backoff *= 2
		if backoff > 30*time.Second {
			backoff = 30 * time.Second
		}
		if err := v.handshake(ctx, true); err != nil {
			// Resume rejected: try a fresh identify once before giving up.
			if err := v.handshake(ctx, false); err != nil {
				v.finish(err)
				return
			}
		}
	}
}

func (v *VoiceConnection) finish(err error) {
	v.doneOnce.Do(func() {
		v.mu.Lock()
		v.runErr = err
		if v.heartbeatStop != nil {
			close(v.heartbeatStop)
			v.heartbeatStop = nil
		}
		v.mu.Unlock()
		close(v.done)
	})
}

// Close tears down the websocket, UDP socket and heartbeat.
func (v *VoiceConnection) Close() error {
	v.mu.Lock()
	v.closing = true
	conn := v.conn
	udp := v.udp
	v.conn = nil
	v.udp = nil
	v.mu.Unlock()
	if conn != nil {
		_ = conn.WriteControl(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""),
			time.Now().Add(time.Second),
		)
		conn.Close()
	}
	if udp != nil {
		udp.Close()
	}
	v.finish(nil)
	return nil
}

// VoiceClosedError reports a voice websocket close that the client will not
// transparently recover from (rejoin required or fatal).
type VoiceClosedError struct {
	Code   int
	Action VoiceCloseAction
}

func (e *VoiceClosedError) Error() string {
	return fmt.Sprintf("vaidcord-go: voice gateway closed with code %d (action=%s)", e.Code, e.Action)
}

// --------------------------------------------------------------------- //
// Outbound media                                                        //
// --------------------------------------------------------------------- //

// SealOpusFrame encrypts one opus packet into a full RTP datagram and
// advances the RTP sequence/timestamp/nonce counters. Exposed so custom
// transports can be built on top; most callers want SendOpusFrame or Play.
func (v *VoiceConnection) SealOpusFrame(opus []byte) ([]byte, error) {
	v.mu.Lock()
	defer v.mu.Unlock()
	if v.ready == nil {
		return nil, errors.New("vaidcord-go: voice connection is not ready")
	}
	if v.box == nil {
		return nil, errors.New("vaidcord-go: voice session description not received")
	}
	header := BuildRTPHeader(0x78, v.rtpSequence, v.rtpTimestamp, v.ready.SSRC)
	sealed := v.box.Seal(header, opus, v.nonceCounter)
	v.rtpSequence++
	v.rtpTimestamp += OpusTimestampStep
	v.nonceCounter++
	return append(header, sealed...), nil
}

// SendOpusFrame seals and transmits one opus packet over UDP.
func (v *VoiceConnection) SendOpusFrame(opus []byte) error {
	packet, err := v.SealOpusFrame(opus)
	if err != nil {
		return err
	}
	v.mu.Lock()
	udp := v.udp
	v.mu.Unlock()
	if udp == nil {
		return errors.New("vaidcord-go: voice UDP transport is not connected")
	}
	return udp.Send(packet)
}

// Play streams an AudioSource with drift-corrected 20 ms pacing: frames are
// scheduled against absolute deadlines, so a slow frame shortens the next
// sleep instead of accumulating drift. It sends the speaking payload before
// the first frame and silence frames + speaking(0) afterwards.
func (v *VoiceConnection) Play(ctx context.Context, source AudioSource) error {
	defer source.Close()
	if err := v.Speaking(VoiceSpeakingMicrophone); err != nil {
		return err
	}
	frameDuration := OpusFrameLengthMS * time.Millisecond
	next := time.Now()
	var playErr error
	for {
		if err := ctx.Err(); err != nil {
			playErr = err
			break
		}
		frame, err := source.ReadOpus()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			playErr = err
			break
		}
		if len(frame) == 0 {
			continue
		}
		if err := v.SendOpusFrame(frame); err != nil {
			playErr = err
			break
		}
		next = next.Add(frameDuration)
		delay := time.Until(next)
		if delay > 0 {
			if err := sleepContext(ctx, delay); err != nil {
				playErr = err
				break
			}
		} else if delay < -100*time.Millisecond {
			// We fell far behind (blocked source/socket): resynchronise
			// instead of bursting packets to catch up.
			next = time.Now()
		}
	}
	// Trailing silence lets receivers flush their jitter buffers.
	for i := 0; i < 5; i++ {
		if err := v.SendOpusFrame(OpusSilenceFrame); err != nil {
			break
		}
	}
	if err := v.Speaking(0); err != nil && playErr == nil {
		playErr = err
	}
	return playErr
}

// --------------------------------------------------------------------- //
// Inbound media                                                         //
// --------------------------------------------------------------------- //

// Listen reads inbound datagrams, drops RTCP, decrypts RTP and hands
// (userID, opusPacket) frames to sink until ctx is cancelled or the socket
// closes. Packets from unmapped SSRCs are delivered with an empty UserID.
func (v *VoiceConnection) Listen(ctx context.Context, sink func(VoiceFrame)) error {
	v.mu.Lock()
	udp := v.udp
	box := v.box
	v.mu.Unlock()
	if udp == nil {
		return errors.New("vaidcord-go: voice UDP transport is not connected")
	}
	if box == nil {
		return errors.New("vaidcord-go: voice session description not received")
	}
	buf := make([]byte, 4096)
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		data, err := udp.Receive(buf, time.Second)
		if err != nil {
			var netErr interface{ Timeout() bool }
			if errors.As(err, &netErr) && netErr.Timeout() {
				continue
			}
			if ctx.Err() != nil {
				return ctx.Err()
			}
			return err
		}
		if IsRTCPPacket(data) {
			continue
		}
		packet, opus, err := OpenVoicePacket(box, data)
		if err != nil {
			continue // undecryptable/foreign packet
		}
		userID, _ := v.SSRCUser(packet.SSRC)
		sink(VoiceFrame{
			UserID:    userID,
			SSRC:      packet.SSRC,
			Sequence:  packet.Sequence,
			Timestamp: packet.Timestamp,
			Opus:      opus,
		})
	}
}
