package vaidcord

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

func TestClassifyGatewayCloseCode(t *testing.T) {
	cases := []struct {
		code   int
		action GatewayCloseAction
	}{
		{-1, GatewayCloseResume}, // closed without a code
		{1000, GatewayCloseResume},
		{1006, GatewayCloseResume},
		{4000, GatewayCloseResume},
		{4001, GatewayCloseResume},
		{4002, GatewayCloseResume},
		{4005, GatewayCloseResume},
		{4008, GatewayCloseResume},
		{4003, GatewayCloseReidentify},
		{4007, GatewayCloseReidentify},
		{4009, GatewayCloseReidentify},
		{4004, GatewayCloseFatal},
		{4010, GatewayCloseFatal},
		{4011, GatewayCloseFatal},
		{4012, GatewayCloseFatal},
		{4013, GatewayCloseFatal},
		{4014, GatewayCloseFatal},
	}
	for _, testCase := range cases {
		if got := ClassifyGatewayCloseCode(testCase.code); got != testCase.action {
			t.Fatalf("code %d: expected %s, got %s", testCase.code, testCase.action, got)
		}
	}
}

// fakeGateway is a scripted Discord gateway: an HTTP server that serves both
// GET /api/v10/gateway/bot and the websocket endpoint.
type fakeGateway struct {
	t        *testing.T
	server   *httptest.Server
	upgrader websocket.Upgrader

	mu          sync.Mutex
	connections int
	handlers    []func(conn *websocket.Conn, connIndex int)
}

func newFakeGateway(t *testing.T, handlers ...func(conn *websocket.Conn, connIndex int)) *fakeGateway {
	fake := &fakeGateway{t: t, handlers: handlers}
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v10/gateway/bot", func(w http.ResponseWriter, r *http.Request) {
		wsURL := "ws" + strings.TrimPrefix(fake.server.URL, "http") + "/ws"
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"url":%q}`, wsURL)
	})
	mux.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		conn, err := fake.upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		fake.mu.Lock()
		index := fake.connections
		fake.connections++
		var handler func(*websocket.Conn, int)
		if index < len(fake.handlers) {
			handler = fake.handlers[index]
		}
		fake.mu.Unlock()
		if handler != nil {
			handler(conn, index)
		}
		conn.Close()
	})
	fake.server = httptest.NewServer(mux)
	t.Cleanup(fake.server.Close)
	return fake
}

func (f *fakeGateway) client() *Client {
	return NewClient(Config{Token: "token", BaseURL: f.server.URL + "/api"}, f.server.Client())
}

func (f *fakeGateway) connectionCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.connections
}

func wsSend(t *testing.T, conn *websocket.Conn, payload string) {
	t.Helper()
	if err := conn.WriteMessage(websocket.TextMessage, []byte(payload)); err != nil {
		t.Logf("fake gateway write failed: %v", err)
	}
}

func wsExpect(t *testing.T, conn *websocket.Conn, op int) map[string]any {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	_ = conn.SetReadDeadline(deadline)
	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			t.Fatalf("fake gateway expected op %d, read failed: %v", op, err)
		}
		var payload struct {
			Op int             `json:"op"`
			D  json.RawMessage `json:"d"`
		}
		if err := json.Unmarshal(data, &payload); err != nil {
			t.Fatalf("fake gateway received invalid JSON: %v", err)
		}
		if payload.Op == GatewayOpHeartbeat {
			// Always acknowledge heartbeats so they never zombie the test.
			wsSend(t, conn, `{"op":11}`)
			if op != GatewayOpHeartbeat {
				continue
			}
		}
		if payload.Op != op {
			t.Fatalf("fake gateway expected op %d, got op %d", op, payload.Op)
		}
		var decoded map[string]any
		_ = json.Unmarshal(payload.D, &decoded)
		return decoded
	}
}

func wsClose(conn *websocket.Conn, code int) {
	_ = conn.WriteControl(
		websocket.CloseMessage,
		websocket.FormatCloseMessage(code, ""),
		time.Now().Add(time.Second),
	)
	conn.Close()
}

// TestGatewayIdentifyResumeFlow drives a full connect -> READY -> transient
// close -> RESUME -> fatal close lifecycle and checks the payloads.
func TestGatewayIdentifyResumeFlow(t *testing.T) {
	var fake *fakeGateway
	fake = newFakeGateway(t,
		func(conn *websocket.Conn, _ int) {
			wsSend(t, conn, `{"op":10,"d":{"heartbeat_interval":60000}}`)
			identify := wsExpect(t, conn, GatewayOpIdentify)
			if identify["token"] != "token" {
				t.Errorf("IDENTIFY token mismatch: %v", identify["token"])
			}
			if int(identify["intents"].(float64)) != int(IntentsDefault|IntentMessageContent) {
				t.Errorf("IDENTIFY intents mismatch: %v", identify["intents"])
			}
			ready := fmt.Sprintf(
				`{"op":0,"t":"READY","s":1,"d":{"v":10,"user":{"id":"1","username":"bot"},"session_id":"sess-1","resume_gateway_url":%q}}`,
				"ws"+strings.TrimPrefix(fake.server.URL, "http")+"/ws",
			)
			wsSend(t, conn, ready)
			wsSend(t, conn, `{"op":0,"t":"MESSAGE_CREATE","s":5,"d":{"id":"m1","channel_id":"c1","author":{"id":"2","username":"user"},"content":"hello"}}`)
			time.Sleep(50 * time.Millisecond) // let the client record seq 5
			wsClose(conn, 4000)               // resumable close
		},
		func(conn *websocket.Conn, _ int) {
			wsSend(t, conn, `{"op":10,"d":{"heartbeat_interval":60000}}`)
			resume := wsExpect(t, conn, GatewayOpResume)
			if resume["session_id"] != "sess-1" {
				t.Errorf("RESUME session mismatch: %v", resume["session_id"])
			}
			if resume["token"] != "token" {
				t.Errorf("RESUME token mismatch: %v", resume["token"])
			}
			if int(resume["seq"].(float64)) != 5 {
				t.Errorf("RESUME seq mismatch: %v", resume["seq"])
			}
			wsSend(t, conn, `{"op":0,"t":"RESUMED","s":6,"d":{}}`)
			time.Sleep(50 * time.Millisecond)
			wsClose(conn, 4004) // fatal: authentication failed
		},
	)

	gateway := NewGateway(fake.client(), IntentsDefault|IntentMessageContent,
		WithGatewayBackoff(time.Millisecond, 5*time.Millisecond))

	var mu sync.Mutex
	var events []string
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	err := gateway.Run(ctx, func(_ context.Context, dispatch GatewayDispatch) {
		mu.Lock()
		events = append(events, dispatch.Type)
		mu.Unlock()
	})

	var closed *GatewayClosedError
	if !errors.As(err, &closed) || closed.Code != 4004 {
		t.Fatalf("expected fatal 4004 close, got %v", err)
	}
	mu.Lock()
	defer mu.Unlock()
	joined := strings.Join(events, ",")
	if joined != "READY,MESSAGE_CREATE,RESUMED" {
		t.Fatalf("unexpected dispatch order: %s", joined)
	}
	if gateway.SessionID() != "sess-1" {
		t.Fatalf("session id not tracked: %q", gateway.SessionID())
	}
	if fake.connectionCount() != 2 {
		t.Fatalf("expected 2 connections, got %d", fake.connectionCount())
	}
}

// TestGatewayHeartbeatAndACK verifies heartbeats run on their own goroutine
// (the server never has to prompt them) and that ACKs record latency.
func TestGatewayHeartbeatAndACK(t *testing.T) {
	heartbeatSeen := make(chan struct{}, 1)
	fake := newFakeGateway(t,
		func(conn *websocket.Conn, _ int) {
			wsSend(t, conn, `{"op":10,"d":{"heartbeat_interval":30}}`)
			wsExpect(t, conn, GatewayOpIdentify)
			wsSend(t, conn, `{"op":0,"t":"READY","s":1,"d":{"session_id":"s","resume_gateway_url":"","user":{"id":"1","username":"b"}}}`)
			wsExpect(t, conn, GatewayOpHeartbeat) // acked inside wsExpect
			select {
			case heartbeatSeen <- struct{}{}:
			default:
			}
			time.Sleep(20 * time.Millisecond) // give the ACK time to land
			wsClose(conn, 4004)
		},
	)
	gateway := NewGateway(fake.client(), IntentsDefault,
		WithGatewayBackoff(time.Millisecond, 5*time.Millisecond))
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	err := gateway.Run(ctx, nil)
	var closed *GatewayClosedError
	if !errors.As(err, &closed) || closed.Code != 4004 {
		t.Fatalf("expected fatal 4004 close, got %v", err)
	}
	select {
	case <-heartbeatSeen:
	default:
		t.Fatal("no heartbeat was sent")
	}
	if gateway.Latency() <= 0 {
		t.Fatal("heartbeat ACK latency was not recorded")
	}
}

// TestGatewayReconnectsOnMissedHeartbeatACK starves the client of ACKs and
// expects it to recycle the connection and reconnect.
func TestGatewayReconnectsOnMissedHeartbeatACK(t *testing.T) {
	fake := newFakeGateway(t,
		func(conn *websocket.Conn, _ int) {
			wsSend(t, conn, `{"op":10,"d":{"heartbeat_interval":20}}`)
			// Read frames but never send op 11: the client must give up.
			_ = conn.SetReadDeadline(time.Now().Add(5 * time.Second))
			for {
				if _, _, err := conn.ReadMessage(); err != nil {
					return
				}
			}
		},
		func(conn *websocket.Conn, _ int) {
			wsSend(t, conn, `{"op":10,"d":{"heartbeat_interval":60000}}`)
			wsExpect(t, conn, GatewayOpIdentify)
			wsClose(conn, 4004)
		},
	)
	gateway := NewGateway(fake.client(), IntentsDefault,
		WithGatewayBackoff(time.Millisecond, 5*time.Millisecond))
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	err := gateway.Run(ctx, nil)
	var closed *GatewayClosedError
	if !errors.As(err, &closed) || closed.Code != 4004 {
		t.Fatalf("expected fatal 4004 close after reconnect, got %v", err)
	}
	if fake.connectionCount() != 2 {
		t.Fatalf("expected 2 connections (initial + reconnect), got %d", fake.connectionCount())
	}
}

// TestGatewayInvalidSessionReidentifies covers op 9 with d=false: the client
// must drop the session and IDENTIFY on the next connection.
func TestGatewayInvalidSessionReidentifies(t *testing.T) {
	fake := newFakeGateway(t,
		func(conn *websocket.Conn, _ int) {
			wsSend(t, conn, `{"op":10,"d":{"heartbeat_interval":60000}}`)
			wsExpect(t, conn, GatewayOpIdentify)
			wsSend(t, conn, `{"op":0,"t":"READY","s":1,"d":{"session_id":"sess-1","resume_gateway_url":"","user":{"id":"1","username":"b"}}}`)
			wsSend(t, conn, `{"op":9,"d":false}`)
			time.Sleep(50 * time.Millisecond)
		},
		func(conn *websocket.Conn, _ int) {
			wsSend(t, conn, `{"op":10,"d":{"heartbeat_interval":60000}}`)
			wsExpect(t, conn, GatewayOpIdentify) // NOT resume
			wsClose(conn, 4004)
		},
	)
	gateway := NewGateway(fake.client(), IntentsDefault,
		WithGatewayBackoff(time.Millisecond, 5*time.Millisecond))
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	err := gateway.Run(ctx, nil)
	var closed *GatewayClosedError
	if !errors.As(err, &closed) || closed.Code != 4004 {
		t.Fatalf("expected fatal 4004 close, got %v", err)
	}
	if gateway.SessionID() != "" {
		t.Fatalf("session should have been cleared, got %q", gateway.SessionID())
	}
}

// TestGatewaySendHelpers checks the op 3 / op 8 / op 4 helper payloads.
func TestGatewaySendHelpers(t *testing.T) {
	ready := make(chan *Gateway, 1)
	fake := newFakeGateway(t,
		func(conn *websocket.Conn, _ int) {
			wsSend(t, conn, `{"op":10,"d":{"heartbeat_interval":60000}}`)
			wsExpect(t, conn, GatewayOpIdentify)
			wsSend(t, conn, `{"op":0,"t":"READY","s":1,"d":{"session_id":"s","resume_gateway_url":"","user":{"id":"1","username":"b"}}}`)

			presence := wsExpect(t, conn, GatewayOpPresenceUpdate)
			if presence["status"] != "dnd" {
				t.Errorf("unexpected presence status: %v", presence["status"])
			}
			activities, ok := presence["activities"].([]any)
			if !ok || len(activities) != 1 {
				t.Errorf("unexpected presence activities: %v", presence["activities"])
			}

			members := wsExpect(t, conn, GatewayOpRequestGuildMembers)
			if members["guild_id"] != "g1" || members["query"] != "vai" {
				t.Errorf("unexpected member request: %v", members)
			}

			voice := wsExpect(t, conn, GatewayOpVoiceStateUpdate)
			if voice["guild_id"] != "g1" || voice["channel_id"] != "c9" || voice["self_deaf"] != true {
				t.Errorf("unexpected voice state update: %v", voice)
			}
			wsClose(conn, 4004)
		},
	)
	gateway := NewGateway(fake.client(), IntentsDefault,
		WithGatewayBackoff(time.Millisecond, 5*time.Millisecond))
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	go func() {
		gw := <-ready
		if err := gw.UpdatePresence(PresenceUpdate{Status: "dnd", Activities: []Activity{{Name: "tests", Type: 0}}}); err != nil {
			t.Errorf("UpdatePresence failed: %v", err)
		}
		if err := gw.RequestGuildMembers(GuildMembersRequest{GuildID: "g1", Query: "vai", Limit: 10}); err != nil {
			t.Errorf("RequestGuildMembers failed: %v", err)
		}
		if err := gw.UpdateVoiceState("g1", "c9", false, true); err != nil {
			t.Errorf("UpdateVoiceState failed: %v", err)
		}
	}()

	err := gateway.Run(ctx, func(_ context.Context, dispatch GatewayDispatch) {
		if dispatch.Type == "READY" {
			select {
			case ready <- gateway:
			default:
			}
		}
	})
	var closed *GatewayClosedError
	if !errors.As(err, &closed) || closed.Code != 4004 {
		t.Fatalf("expected fatal 4004 close, got %v", err)
	}
}

func TestGatewayClientStreamUpdatesCompat(t *testing.T) {
	fake := newFakeGateway(t,
		func(conn *websocket.Conn, _ int) {
			wsSend(t, conn, `{"op":10,"d":{"heartbeat_interval":60000}}`)
			wsExpect(t, conn, GatewayOpIdentify)
			wsSend(t, conn, `{"op":0,"t":"READY","s":1,"d":{"session_id":"s","resume_gateway_url":"","user":{"id":"1","username":"b"}}}`)
			time.Sleep(100 * time.Millisecond)
		},
	)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	updates, _ := NewGatewayClient(fake.client()).StreamUpdates(ctx, int(IntentsDefault))
	select {
	case dispatch := <-updates:
		if dispatch.Type != "READY" {
			t.Fatalf("unexpected dispatch: %s", dispatch.Type)
		}
		cancel()
	case <-ctx.Done():
		t.Fatal("no dispatch received")
	}
}
