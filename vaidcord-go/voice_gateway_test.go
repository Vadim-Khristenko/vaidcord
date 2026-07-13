package vaidcord

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// secretKeyJSON renders testSecretKey as the JSON int array Discord sends in
// the session description payload.
func secretKeyJSON() string {
	var builder strings.Builder
	builder.WriteByte('[')
	for i, value := range testSecretKey() {
		if i > 0 {
			builder.WriteByte(',')
		}
		fmt.Fprintf(&builder, "%d", value)
	}
	builder.WriteByte(']')
	return builder.String()
}

func voicePayloadFromJSON(t *testing.T, raw string) VoicePayload {
	t.Helper()
	var payload VoicePayload
	if err := json.Unmarshal([]byte(raw), &payload); err != nil {
		t.Fatal(err)
	}
	return payload
}

func TestVoiceConnectionTracksSpeakingSSRCMapAndCallbacks(t *testing.T) {
	conn := NewVoiceConnection(VoiceServerInfo{}, VoiceGatewayConfig{})
	var seen []string
	conn.OnSpeaking(func(userID string, ssrc uint32, flags int) {
		seen = append(seen, fmt.Sprintf("%s/%d/%d", userID, ssrc, flags))
	})

	if err := conn.HandlePayload(voicePayloadFromJSON(t, `{"op":5,"d":{"ssrc":555,"user_id":"42","speaking":1}}`)); err != nil {
		t.Fatal(err)
	}
	if userID, ok := conn.SSRCUser(555); !ok || userID != "42" {
		t.Fatalf("ssrc not mapped: %q %v", userID, ok)
	}
	if len(seen) != 1 || seen[0] != "42/555/1" {
		t.Fatalf("unexpected speaking callbacks: %v", seen)
	}

	if err := conn.HandlePayload(voicePayloadFromJSON(t, `{"op":13,"d":{"user_id":"42"}}`)); err != nil {
		t.Fatal(err)
	}
	if _, ok := conn.SSRCUser(555); ok {
		t.Fatal("ssrc map should forget disconnected users")
	}
}

func TestVoiceConnectionMapsAudioSSRCFromVideoPayload(t *testing.T) {
	conn := NewVoiceConnection(VoiceServerInfo{}, VoiceGatewayConfig{})
	payload := voicePayloadFromJSON(t, `{"op":12,"d":{"user_id":"9","audio_ssrc":777,"video_ssrc":778}}`)
	if err := conn.HandlePayload(payload); err != nil {
		t.Fatal(err)
	}
	if userID, ok := conn.SSRCUser(777); !ok || userID != "9" {
		t.Fatalf("audio ssrc not mapped from op 12: %q %v", userID, ok)
	}
}

func TestVoiceConnectionSessionDescriptionBuildsBox(t *testing.T) {
	conn := NewVoiceConnection(VoiceServerInfo{}, VoiceGatewayConfig{})
	keyJSON := secretKeyJSON()
	payload := voicePayloadFromJSON(t, fmt.Sprintf(
		`{"op":4,"d":{"mode":"aead_aes256_gcm_rtpsize","secret_key":%s}}`, keyJSON))
	if err := conn.HandlePayload(payload); err != nil {
		t.Fatal(err)
	}
	if conn.Box() == nil || conn.Box().Mode() != VoiceModeAEADAES256GCMRTPSize {
		t.Fatal("session description did not build a voice box")
	}
	// Seal a frame through the connection and open it with an independent box.
	if err := conn.HandlePayload(voicePayloadFromJSON(t, `{"op":2,"d":{"ssrc":321,"ip":"127.0.0.1","port":1,"modes":["aead_aes256_gcm_rtpsize"]}}`)); err != nil {
		t.Fatal(err)
	}
	datagram, err := conn.SealOpusFrame([]byte("opus"))
	if err != nil {
		t.Fatal(err)
	}
	box, _ := CreateVoiceBox(VoiceModeAEADAES256GCMRTPSize, testSecretKey())
	packet, opus, err := OpenVoicePacket(box, datagram)
	if err != nil {
		t.Fatal(err)
	}
	if string(opus) != "opus" || packet.SSRC != 321 {
		t.Fatalf("unexpected decrypted frame: %q ssrc=%d", opus, packet.SSRC)
	}
}

func TestVoiceConnectionSeqAckTrackingAndResumedFlag(t *testing.T) {
	conn := NewVoiceConnection(VoiceServerInfo{GuildID: "g", SessionID: "s", Token: "tok"}, VoiceGatewayConfig{})
	if err := conn.HandlePayload(voicePayloadFromJSON(t, `{"op":5,"seq":17,"d":{"ssrc":1,"user_id":"2","speaking":1}}`)); err != nil {
		t.Fatal(err)
	}
	conn.mu.Lock()
	seqAck := conn.seqAck
	conn.mu.Unlock()
	if seqAck != 17 {
		t.Fatalf("seq_ack not tracked: %d", seqAck)
	}
	if err := conn.HandlePayload(voicePayloadFromJSON(t, `{"op":9,"d":{}}`)); err != nil {
		t.Fatal(err)
	}
	conn.mu.Lock()
	resumed := conn.resumed
	conn.mu.Unlock()
	if !resumed {
		t.Fatal("op 9 should set the resumed flag")
	}
}

func TestVoiceReadySelectMode(t *testing.T) {
	ready := VoiceReady{Modes: []string{"weird_mode", VoiceModeAEADXChaCha20Poly1305RTPSize}}
	mode, err := ready.SelectMode([]string{VoiceModeAEADAES256GCMRTPSize, VoiceModeAEADXChaCha20Poly1305RTPSize})
	if err != nil || mode != VoiceModeAEADXChaCha20Poly1305RTPSize {
		t.Fatalf("unexpected mode selection: %q %v", mode, err)
	}
	fallback, err := ready.SelectMode([]string{"unavailable"})
	if err != nil || fallback != "weird_mode" {
		t.Fatalf("unexpected fallback: %q %v", fallback, err)
	}
	if _, err := (VoiceReady{}).SelectMode(nil); err == nil {
		t.Fatal("expected error when the server offers no modes")
	}
}

func TestVoiceServerInfoWebsocketURL(t *testing.T) {
	info := VoiceServerInfo{Endpoint: "wss://region.discord.media:443"}
	if got := info.WebsocketURL(8); got != "wss://region.discord.media:443?v=8&encoding=json" {
		t.Fatalf("unexpected URL: %s", got)
	}
	plain := VoiceServerInfo{Endpoint: "region.discord.media:443"}
	if got := plain.WebsocketURL(8); got != "wss://region.discord.media:443?v=8&encoding=json" {
		t.Fatalf("unexpected URL: %s", got)
	}
}

// fakeVoiceServer scripts the voice websocket handshake (v8) plus a local
// UDP socket that answers IP discovery and captures media packets.
type fakeVoiceServer struct {
	t      *testing.T
	server *httptest.Server
	udp    *net.UDPConn

	mu        sync.Mutex
	wsSeen    []int // ops received
	media     [][]byte
	mediaCond *sync.Cond
}

func newFakeVoiceServer(t *testing.T) *fakeVoiceServer {
	udp, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	fake := &fakeVoiceServer{t: t, udp: udp}
	fake.mediaCond = sync.NewCond(&fake.mu)
	go fake.udpLoop()

	upgrader := websocket.Upgrader{}
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		fake.serveWS(conn)
	})
	fake.server = httptest.NewServer(mux)
	t.Cleanup(func() {
		fake.server.Close()
		udp.Close()
	})
	return fake
}

func (f *fakeVoiceServer) udpPort() int {
	return f.udp.LocalAddr().(*net.UDPAddr).Port
}

func (f *fakeVoiceServer) udpLoop() {
	buf := make([]byte, 2048)
	for {
		n, addr, err := f.udp.ReadFromUDP(buf)
		if err != nil {
			return
		}
		data := append([]byte{}, buf[:n]...)
		if n == 74 && binary.BigEndian.Uint16(data[0:2]) == 1 {
			// IP discovery request -> answer with the client's address.
			response := make([]byte, 74)
			binary.BigEndian.PutUint16(response[0:2], 2)
			binary.BigEndian.PutUint16(response[2:4], 70)
			copy(response[4:8], data[4:8])
			copy(response[8:], addr.IP.String())
			binary.BigEndian.PutUint16(response[72:74], uint16(addr.Port))
			_, _ = f.udp.WriteToUDP(response, addr)
			continue
		}
		f.mu.Lock()
		f.media = append(f.media, data)
		f.mediaCond.Broadcast()
		f.mu.Unlock()
	}
}

func (f *fakeVoiceServer) waitForMedia(count int, timeout time.Duration) [][]byte {
	deadline := time.Now().Add(timeout)
	f.mu.Lock()
	defer f.mu.Unlock()
	for len(f.media) < count {
		if time.Now().After(deadline) {
			f.t.Fatalf("timed out waiting for %d media packets (have %d)", count, len(f.media))
		}
		f.mu.Unlock()
		time.Sleep(5 * time.Millisecond)
		f.mu.Lock()
	}
	return append([][]byte{}, f.media...)
}

func (f *fakeVoiceServer) serveWS(conn *websocket.Conn) {
	defer conn.Close()
	send := func(payload string) {
		_ = conn.WriteMessage(websocket.TextMessage, []byte(payload))
	}
	send(`{"op":8,"seq":1,"d":{"heartbeat_interval":30000}}`)
	_ = conn.SetReadDeadline(time.Now().Add(10 * time.Second))
	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			return
		}
		var payload struct {
			Op int             `json:"op"`
			D  json.RawMessage `json:"d"`
		}
		if json.Unmarshal(data, &payload) != nil {
			continue
		}
		f.mu.Lock()
		f.wsSeen = append(f.wsSeen, payload.Op)
		f.mu.Unlock()
		switch VoiceGatewayOpcode(payload.Op) {
		case VoiceOpIdentify:
			var identify struct {
				ServerID  string `json:"server_id"`
				SessionID string `json:"session_id"`
				Token     string `json:"token"`
			}
			_ = json.Unmarshal(payload.D, &identify)
			if identify.ServerID != "guild-1" || identify.SessionID != "sess" || identify.Token != "voice-token" {
				f.t.Errorf("unexpected identify payload: %+v", identify)
			}
			send(fmt.Sprintf(
				`{"op":2,"seq":2,"d":{"ssrc":321,"ip":"127.0.0.1","port":%d,"modes":["aead_aes256_gcm_rtpsize","aead_xchacha20_poly1305_rtpsize"]}}`,
				f.udpPort(),
			))
		case VoiceOpSelectProtocol:
			var selectProtocol struct {
				Protocol string `json:"protocol"`
				Data     struct {
					Address string `json:"address"`
					Port    int    `json:"port"`
					Mode    string `json:"mode"`
				} `json:"data"`
			}
			_ = json.Unmarshal(payload.D, &selectProtocol)
			if selectProtocol.Protocol != "udp" || selectProtocol.Data.Mode != VoiceModeAEADAES256GCMRTPSize {
				f.t.Errorf("unexpected select protocol payload: %+v", selectProtocol)
			}
			if selectProtocol.Data.Port == 0 || selectProtocol.Data.Address == "" {
				f.t.Errorf("IP discovery result missing from select protocol: %+v", selectProtocol)
			}
			keyJSON := secretKeyJSON()
			send(fmt.Sprintf(`{"op":4,"seq":3,"d":{"mode":"aead_aes256_gcm_rtpsize","secret_key":%s}}`, keyJSON))
		case VoiceOpHeartbeat:
			var beat struct {
				SeqAck *int `json:"seq_ack"`
			}
			if json.Unmarshal(payload.D, &beat) == nil && beat.SeqAck == nil {
				f.t.Error("voice heartbeat missing seq_ack")
			}
			send(`{"op":6,"d":{}}`)
		}
	}
}

// TestVoiceConnectionEndToEnd walks the full v8 handshake against a scripted
// server (identify -> READY -> UDP IP discovery -> select protocol ->
// session description), sends speaking + encrypted audio, and decrypts the
// captured packets like a remote peer would.
func TestVoiceConnectionEndToEnd(t *testing.T) {
	fake := newFakeVoiceServer(t)
	info := VoiceServerInfo{
		GuildID:   "guild-1",
		UserID:    "user-1",
		SessionID: "sess",
		Token:     "voice-token",
		Endpoint:  "ws" + strings.TrimPrefix(fake.server.URL, "http"),
	}
	conn := NewVoiceConnection(info, VoiceGatewayConfig{HandshakeTimeout: 5 * time.Second})
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := conn.Connect(ctx); err != nil {
		t.Fatal(err)
	}
	defer conn.Close()

	ready := conn.Ready()
	if ready == nil || ready.SSRC != 321 {
		t.Fatalf("unexpected READY: %+v", ready)
	}
	session := conn.SessionDescription()
	if session == nil || session.Mode != VoiceModeAEADAES256GCMRTPSize {
		t.Fatalf("unexpected session description: %+v", session)
	}

	if err := conn.Speaking(VoiceSpeakingMicrophone); err != nil {
		t.Fatal(err)
	}
	source := NewOpusPacketSource([]byte("frame-1"), []byte("frame-2"), []byte("frame-3"))
	if err := conn.Play(ctx, source); err != nil {
		t.Fatal(err)
	}

	// 3 audio frames + 5 trailing silence frames.
	packets := fake.waitForMedia(8, 5*time.Second)
	box, _ := CreateVoiceBox(VoiceModeAEADAES256GCMRTPSize, testSecretKey())
	var decrypted []string
	for _, datagram := range packets[:3] {
		packet, opus, err := OpenVoicePacket(box, datagram)
		if err != nil {
			t.Fatalf("server could not decrypt media packet: %v", err)
		}
		if packet.SSRC != 321 {
			t.Fatalf("unexpected media ssrc: %d", packet.SSRC)
		}
		decrypted = append(decrypted, string(opus))
	}
	if strings.Join(decrypted, ",") != "frame-1,frame-2,frame-3" {
		t.Fatalf("unexpected media stream: %v", decrypted)
	}
	// RTP sequence/timestamp must advance monotonically.
	first, _ := ParseRTPPacket(packets[0])
	second, _ := ParseRTPPacket(packets[1])
	if second.Sequence != first.Sequence+1 || second.Timestamp != first.Timestamp+OpusTimestampStep {
		t.Fatalf("RTP counters did not advance: %+v -> %+v", first, second)
	}
	// Trailing silence uses the canonical opus silence frame.
	_, silence, err := OpenVoicePacket(box, packets[3])
	if err != nil {
		t.Fatal(err)
	}
	if string(silence) != string(OpusSilenceFrame) {
		t.Fatalf("expected opus silence frame, got %x", silence)
	}
}

// TestVoiceConnectionPlayPacing verifies drift-corrected 20 ms pacing:
// 5 frames must take roughly 4 frame intervals (deadline-based), not less.
func TestVoiceConnectionPlayPacing(t *testing.T) {
	fake := newFakeVoiceServer(t)
	info := VoiceServerInfo{
		GuildID:   "guild-1",
		UserID:    "user-1",
		SessionID: "sess",
		Token:     "voice-token",
		Endpoint:  "ws" + strings.TrimPrefix(fake.server.URL, "http"),
	}
	conn := NewVoiceConnection(info, VoiceGatewayConfig{HandshakeTimeout: 5 * time.Second})
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := conn.Connect(ctx); err != nil {
		t.Fatal(err)
	}
	defer conn.Close()

	frames := make([][]byte, 5)
	for i := range frames {
		frames[i] = []byte{byte(i)}
	}
	started := time.Now()
	if err := conn.Play(ctx, NewOpusPacketSource(frames...)); err != nil {
		t.Fatal(err)
	}
	elapsed := time.Since(started)
	if elapsed < 80*time.Millisecond {
		t.Fatalf("playback finished too fast for 20ms pacing: %v", elapsed)
	}
	if elapsed > 400*time.Millisecond {
		t.Fatalf("playback paced too slowly: %v", elapsed)
	}
}
