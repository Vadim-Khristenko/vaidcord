package vaidcord

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math/rand"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// Gateway opcodes (https://discord.com/developers/docs/topics/opcodes-and-status-codes).
const (
	GatewayOpDispatch            = 0
	GatewayOpHeartbeat           = 1
	GatewayOpIdentify            = 2
	GatewayOpPresenceUpdate      = 3
	GatewayOpVoiceStateUpdate    = 4
	GatewayOpResume              = 6
	GatewayOpReconnect           = 7
	GatewayOpRequestGuildMembers = 8
	GatewayOpInvalidSession      = 9
	GatewayOpHello               = 10
	GatewayOpHeartbeatACK        = 11
)

// GatewayDispatch is a raw gateway frame. For op 0 frames Type carries the
// event name and Data the event payload.
type GatewayDispatch struct {
	Op   int             `json:"op"`
	Type string          `json:"t"`
	Seq  *int            `json:"s"`
	Data json.RawMessage `json:"d"`
}

// GatewayCloseAction describes how the client should react to a websocket
// close code, mirroring the voice-side VoiceCloseAction.
type GatewayCloseAction int

const (
	// GatewayCloseResume — reconnect and RESUME the existing session.
	GatewayCloseResume GatewayCloseAction = iota
	// GatewayCloseReidentify — the session is gone; reconnect and IDENTIFY.
	GatewayCloseReidentify
	// GatewayCloseFatal — reconnecting is pointless or forbidden.
	GatewayCloseFatal
)

func (a GatewayCloseAction) String() string {
	switch a {
	case GatewayCloseResume:
		return "resume"
	case GatewayCloseReidentify:
		return "reidentify"
	default:
		return "fatal"
	}
}

// ClassifyGatewayCloseCode maps a main-gateway close code to the reconnect
// policy from the Discord docs. Pass a negative code for "unknown/no code".
func ClassifyGatewayCloseCode(code int) GatewayCloseAction {
	switch code {
	case 4004, // Authentication failed
		4010, // Invalid shard
		4011, // Sharding required
		4012, // Invalid API version
		4013, // Invalid intents
		4014: // Disallowed intents
		return GatewayCloseFatal
	case 4003, // Not authenticated
		4007, // Invalid seq
		4009: // Session timed out
		return GatewayCloseReidentify
	default:
		// 4000/4001/4002/4005/4008 and network-level closes (1000, 1001,
		// 1006, no code) are worth a resume attempt; the server will send
		// INVALID SESSION if the session actually died.
		return GatewayCloseResume
	}
}

// GatewayClosedError is returned by the read loop when the websocket closes.
type GatewayClosedError struct {
	Code   int
	Reason string
}

func (e *GatewayClosedError) Error() string {
	return fmt.Sprintf("vaidcord-go: gateway closed with code %d: %s", e.Code, e.Reason)
}

// Action returns the reconnect policy for this close code.
func (e *GatewayClosedError) Action() GatewayCloseAction {
	return ClassifyGatewayCloseCode(e.Code)
}

// ErrMissedHeartbeatACK is the reason a connection was recycled after the
// server failed to acknowledge a heartbeat in time.
var ErrMissedHeartbeatACK = errors.New("vaidcord-go: gateway missed heartbeat ACK")

var errGatewayReconnectRequested = errors.New("vaidcord-go: gateway requested reconnect (op 7)")

type errInvalidSession struct{ resumable bool }

func (e *errInvalidSession) Error() string {
	return fmt.Sprintf("vaidcord-go: gateway invalidated session (resumable=%t)", e.resumable)
}

// Activity is a single presence activity entry.
type Activity struct {
	Name  string `json:"name"`
	Type  int    `json:"type"`
	URL   string `json:"url,omitempty"`
	State string `json:"state,omitempty"`
}

// PresenceUpdate is the op 3 payload (also embeddable into IDENTIFY).
type PresenceUpdate struct {
	Since      *int64     `json:"since"`
	Activities []Activity `json:"activities"`
	Status     string     `json:"status"`
	AFK        bool       `json:"afk"`
}

func (p PresenceUpdate) withDefaults() PresenceUpdate {
	if p.Status == "" {
		p.Status = "online"
	}
	if p.Activities == nil {
		p.Activities = []Activity{}
	}
	return p
}

// GuildMembersRequest is the op 8 payload. Exactly one of Query or UserIDs
// should be used; an empty Query with Limit 0 requests every member (needs
// the GUILD_MEMBERS intent).
type GuildMembersRequest struct {
	GuildID   string
	Query     string
	UserIDs   []string
	Limit     int
	Presences bool
	Nonce     string
}

func (r GuildMembersRequest) payload() map[string]any {
	payload := map[string]any{
		"guild_id": r.GuildID,
		"limit":    r.Limit,
	}
	if len(r.UserIDs) > 0 {
		payload["user_ids"] = r.UserIDs
	} else {
		payload["query"] = r.Query
	}
	if r.Presences {
		payload["presences"] = true
	}
	if r.Nonce != "" {
		payload["nonce"] = r.Nonce
	}
	return payload
}

// DispatchFunc receives every op 0 gateway frame.
type DispatchFunc func(ctx context.Context, dispatch GatewayDispatch)

// GatewayOption customises a Gateway.
type GatewayOption func(*Gateway)

// WithGatewayPresence sets the presence embedded into IDENTIFY.
func WithGatewayPresence(presence PresenceUpdate) GatewayOption {
	return func(g *Gateway) {
		p := presence.withDefaults()
		g.identifyPresence = &p
	}
}

// WithGatewayDialer overrides the websocket dialer (useful for proxies/tests).
func WithGatewayDialer(dialer *websocket.Dialer) GatewayOption {
	return func(g *Gateway) { g.dialer = dialer }
}

// WithGatewayBackoff bounds the reconnect backoff window.
func WithGatewayBackoff(min, max time.Duration) GatewayOption {
	return func(g *Gateway) {
		if min > 0 {
			g.backoffMin = min
		}
		if max > 0 {
			g.backoffMax = max
		}
	}
}

// Gateway is a robust Discord gateway connection: it heartbeats on its own
// goroutine, tracks heartbeat ACKs, resumes sessions after transient closes
// and reconnects with exponential backoff according to the close-code policy.
type Gateway struct {
	client           *Client
	intents          Intents
	dialer           *websocket.Dialer
	identifyPresence *PresenceUpdate
	backoffMin       time.Duration
	backoffMax       time.Duration

	writeMu sync.Mutex // serialises websocket writes

	stateMu          sync.Mutex
	conn             *websocket.Conn
	sessionID        string
	resumeGatewayURL string
	seq              int
	latency          time.Duration
	closeReason      error // set before force-closing conn from another goroutine
}

// NewGateway builds a Gateway on top of the REST client (used to discover the
// websocket URL via GET /gateway/bot).
func NewGateway(client *Client, intents Intents, options ...GatewayOption) *Gateway {
	gateway := &Gateway{
		client:     client,
		intents:    intents,
		dialer:     websocket.DefaultDialer,
		backoffMin: time.Second,
		backoffMax: 60 * time.Second,
	}
	for _, option := range options {
		option(gateway)
	}
	return gateway
}

// SessionID returns the current gateway session id (empty before READY).
func (g *Gateway) SessionID() string {
	g.stateMu.Lock()
	defer g.stateMu.Unlock()
	return g.sessionID
}

// Sequence returns the last sequence number seen on this session.
func (g *Gateway) Sequence() int {
	g.stateMu.Lock()
	defer g.stateMu.Unlock()
	return g.seq
}

// Latency returns the last measured heartbeat round-trip time.
func (g *Gateway) Latency() time.Duration {
	g.stateMu.Lock()
	defer g.stateMu.Unlock()
	return g.latency
}

// UpdatePresence sends an op 3 presence update on the live connection.
func (g *Gateway) UpdatePresence(presence PresenceUpdate) error {
	return g.send(GatewayOpPresenceUpdate, presence.withDefaults())
}

// RequestGuildMembers sends an op 8 request; results arrive as
// GUILD_MEMBERS_CHUNK dispatches.
func (g *Gateway) RequestGuildMembers(request GuildMembersRequest) error {
	return g.send(GatewayOpRequestGuildMembers, request.payload())
}

// UpdateVoiceState sends an op 4 voice state update. Pass an empty channelID
// to disconnect from voice in that guild.
func (g *Gateway) UpdateVoiceState(guildID, channelID string, selfMute, selfDeaf bool) error {
	var channel any
	if channelID != "" {
		channel = channelID
	}
	return g.send(GatewayOpVoiceStateUpdate, map[string]any{
		"guild_id":   guildID,
		"channel_id": channel,
		"self_mute":  selfMute,
		"self_deaf":  selfDeaf,
	})
}

// Run connects and keeps the gateway alive until ctx is cancelled or a fatal
// close code is received. onDispatch is invoked for every op 0 frame.
func (g *Gateway) Run(ctx context.Context, onDispatch DispatchFunc) error {
	backoff := g.backoffMin
	resume := false
	for {
		started := time.Now()
		err := g.runOnce(ctx, onDispatch, resume)
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if time.Since(started) > 2*time.Minute {
			backoff = g.backoffMin
		}

		action := GatewayCloseResume
		var closed *GatewayClosedError
		var invalid *errInvalidSession
		switch {
		case errors.As(err, &closed):
			action = closed.Action()
		case errors.As(err, &invalid):
			if invalid.resumable {
				action = GatewayCloseResume
			} else {
				action = GatewayCloseReidentify
			}
		case errors.Is(err, ErrMissedHeartbeatACK), errors.Is(err, errGatewayReconnectRequested):
			action = GatewayCloseResume
		}
		switch action {
		case GatewayCloseFatal:
			return err
		case GatewayCloseReidentify:
			g.clearSession()
			resume = false
		default:
			resume = g.canResume()
		}

		if err := sleepContext(ctx, jitter(backoff)); err != nil {
			return err
		}
		backoff *= 2
		if backoff > g.backoffMax {
			backoff = g.backoffMax
		}
	}
}

func (g *Gateway) canResume() bool {
	g.stateMu.Lock()
	defer g.stateMu.Unlock()
	return g.sessionID != "" && g.resumeGatewayURL != ""
}

func (g *Gateway) clearSession() {
	g.stateMu.Lock()
	g.sessionID = ""
	g.resumeGatewayURL = ""
	g.seq = 0
	g.stateMu.Unlock()
}

func (g *Gateway) gatewayURL(ctx context.Context, resume bool) (string, error) {
	if resume {
		g.stateMu.Lock()
		base := g.resumeGatewayURL
		g.stateMu.Unlock()
		if base != "" {
			return buildGatewayURL(base, g.client.config.APIVersion)
		}
	}
	var info struct {
		URL string `json:"url"`
	}
	if err := g.client.DoJSON(ctx, http.MethodGet, "/gateway/bot", nil, &info); err != nil {
		return "", err
	}
	return buildGatewayURL(info.URL, g.client.config.APIVersion)
}

// runOnce performs a single connect -> handshake -> read-loop cycle. The
// returned error describes why the connection ended.
func (g *Gateway) runOnce(ctx context.Context, onDispatch DispatchFunc, resume bool) error {
	wsURL, err := g.gatewayURL(ctx, resume)
	if err != nil {
		return err
	}
	conn, _, err := g.dialer.DialContext(ctx, wsURL, http.Header{
		"User-Agent": []string{UserAgent},
	})
	if err != nil {
		return err
	}
	conn.SetReadLimit(16 << 20)

	g.stateMu.Lock()
	g.conn = conn
	g.closeReason = nil
	g.stateMu.Unlock()
	defer func() {
		g.stateMu.Lock()
		g.conn = nil
		g.stateMu.Unlock()
		conn.Close()
	}()

	// The first frame must be HELLO.
	hello, err := g.readFrame(conn)
	if err != nil {
		return err
	}
	if hello.Op != GatewayOpHello {
		return fmt.Errorf("vaidcord-go: expected HELLO, got op %d", hello.Op)
	}
	var helloData struct {
		HeartbeatInterval float64 `json:"heartbeat_interval"`
	}
	if err := json.Unmarshal(hello.Data, &helloData); err != nil {
		return err
	}
	interval := time.Duration(helloData.HeartbeatInterval * float64(time.Millisecond))
	if interval <= 0 {
		return fmt.Errorf("vaidcord-go: invalid heartbeat interval %v", helloData.HeartbeatInterval)
	}

	if resume {
		err = g.sendResume()
	} else {
		err = g.sendIdentify()
	}
	if err != nil {
		return err
	}

	// Heartbeat loop on its own goroutine. ackC delivers op 11 receipts,
	// beatC requests an immediate heartbeat (server op 1).
	ackC := make(chan struct{}, 1)
	beatC := make(chan struct{}, 1)
	heartbeatCtx, stopHeartbeat := context.WithCancel(ctx)
	defer stopHeartbeat()
	go g.heartbeatLoop(heartbeatCtx, conn, interval, ackC, beatC)

	// Watch ctx so cancellation unblocks the blocking ReadMessage below.
	go func() {
		<-heartbeatCtx.Done()
		conn.Close()
	}()

	for {
		frame, err := g.readFrame(conn)
		if err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			if reason := g.takeCloseReason(); reason != nil {
				return reason
			}
			var closeErr *websocket.CloseError
			if errors.As(err, &closeErr) {
				return &GatewayClosedError{Code: closeErr.Code, Reason: closeErr.Text}
			}
			return err
		}
		if frame.Seq != nil {
			g.stateMu.Lock()
			g.seq = *frame.Seq
			g.stateMu.Unlock()
		}

		switch frame.Op {
		case GatewayOpDispatch:
			if frame.Type == "READY" {
				var ready struct {
					SessionID        string `json:"session_id"`
					ResumeGatewayURL string `json:"resume_gateway_url"`
				}
				if err := json.Unmarshal(frame.Data, &ready); err == nil {
					g.stateMu.Lock()
					g.sessionID = ready.SessionID
					g.resumeGatewayURL = ready.ResumeGatewayURL
					g.stateMu.Unlock()
				}
			}
			if onDispatch != nil {
				onDispatch(ctx, frame)
			}
		case GatewayOpHeartbeat:
			select {
			case beatC <- struct{}{}:
			default:
			}
		case GatewayOpReconnect:
			return errGatewayReconnectRequested
		case GatewayOpInvalidSession:
			var resumable bool
			_ = json.Unmarshal(frame.Data, &resumable)
			return &errInvalidSession{resumable: resumable}
		case GatewayOpHeartbeatACK:
			select {
			case ackC <- struct{}{}:
			default:
			}
		}
	}
}

func (g *Gateway) readFrame(conn *websocket.Conn) (GatewayDispatch, error) {
	var frame GatewayDispatch
	_, payload, err := conn.ReadMessage()
	if err != nil {
		return frame, err
	}
	if err := json.Unmarshal(payload, &frame); err != nil {
		return frame, err
	}
	return frame, nil
}

// heartbeatLoop sends op 1 every interval and recycles the connection when
// the previous heartbeat was never acknowledged.
func (g *Gateway) heartbeatLoop(ctx context.Context, conn *websocket.Conn, interval time.Duration, ackC, beatC <-chan struct{}) {
	awaitingACK := false
	var sentAt time.Time
	// Discord asks for interval*jitter before the very first heartbeat.
	timer := time.NewTimer(jitter(interval))
	defer timer.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ackC:
			awaitingACK = false
			g.stateMu.Lock()
			g.latency = time.Since(sentAt)
			g.stateMu.Unlock()
			continue
		case <-beatC:
		case <-timer.C:
			timer.Reset(interval)
			if awaitingACK {
				// Zombied connection: close it so the read loop reconnects
				// and resumes (per Discord docs).
				g.forceClose(conn, ErrMissedHeartbeatACK)
				return
			}
		}
		if err := g.sendHeartbeat(); err != nil {
			return
		}
		awaitingACK = true
		sentAt = time.Now()
	}
}

func (g *Gateway) forceClose(conn *websocket.Conn, reason error) {
	g.stateMu.Lock()
	g.closeReason = reason
	g.stateMu.Unlock()
	_ = conn.WriteControl(
		websocket.CloseMessage,
		websocket.FormatCloseMessage(websocket.CloseServiceRestart, "heartbeat ack timeout"),
		time.Now().Add(time.Second),
	)
	conn.Close()
}

func (g *Gateway) takeCloseReason() error {
	g.stateMu.Lock()
	defer g.stateMu.Unlock()
	reason := g.closeReason
	g.closeReason = nil
	return reason
}

func (g *Gateway) sendIdentify() error {
	payload := map[string]any{
		"token":   g.client.config.Token,
		"intents": int(g.intents),
		"properties": map[string]string{
			"os":      "linux",
			"browser": LibraryName,
			"device":  LibraryName,
		},
	}
	if g.identifyPresence != nil {
		payload["presence"] = *g.identifyPresence
	}
	return g.send(GatewayOpIdentify, payload)
}

func (g *Gateway) sendResume() error {
	g.stateMu.Lock()
	sessionID := g.sessionID
	seq := g.seq
	g.stateMu.Unlock()
	return g.send(GatewayOpResume, map[string]any{
		"token":      g.client.config.Token,
		"session_id": sessionID,
		"seq":        seq,
	})
}

func (g *Gateway) sendHeartbeat() error {
	g.stateMu.Lock()
	seq := g.seq
	hasSession := g.sessionID != ""
	g.stateMu.Unlock()
	var value any
	if hasSession || seq > 0 {
		value = seq
	}
	return g.send(GatewayOpHeartbeat, value)
}

func (g *Gateway) send(op int, data any) error {
	g.stateMu.Lock()
	conn := g.conn
	g.stateMu.Unlock()
	if conn == nil {
		return errors.New("vaidcord-go: gateway is not connected")
	}
	g.writeMu.Lock()
	defer g.writeMu.Unlock()
	return conn.WriteJSON(map[string]any{"op": op, "d": data})
}

// jitter returns a random duration in [d/2, d] so reconnect storms and first
// heartbeats spread out.
func jitter(d time.Duration) time.Duration {
	if d <= 0 {
		return 0
	}
	half := d / 2
	return half + time.Duration(rand.Int63n(int64(half)+1))
}

func sleepContext(ctx context.Context, d time.Duration) error {
	if d <= 0 {
		return ctx.Err()
	}
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

// GatewayClient is the historical thin streaming API, now backed by the
// robust Gateway implementation (heartbeats, RESUME, reconnect policy).
type GatewayClient struct {
	client *Client
}

func NewGatewayClient(client *Client) *GatewayClient {
	return &GatewayClient{client: client}
}

// StreamUpdates yields every op 0 dispatch until ctx is cancelled or the
// connection fails fatally.
func (g *GatewayClient) StreamUpdates(ctx context.Context, intents int) (<-chan GatewayDispatch, <-chan error) {
	updates := make(chan GatewayDispatch)
	errs := make(chan error, 1)
	gateway := NewGateway(g.client, Intents(intents))
	go func() {
		defer close(updates)
		defer close(errs)
		err := gateway.Run(ctx, func(ctx context.Context, dispatch GatewayDispatch) {
			select {
			case <-ctx.Done():
			case updates <- dispatch:
			}
		})
		if err != nil && ctx.Err() == nil {
			errs <- err
		}
	}()
	return updates, errs
}

func buildGatewayURL(base string, version string) (string, error) {
	parsed, err := url.Parse(base)
	if err != nil {
		return "", err
	}
	if parsed.Scheme == "" {
		parsed.Scheme = "wss"
	}
	if !strings.HasPrefix(parsed.Scheme, "ws") {
		parsed.Scheme = "wss"
	}
	query := parsed.Query()
	query.Set("v", version)
	query.Set("encoding", "json")
	parsed.RawQuery = query.Encode()
	if parsed.Host == "" {
		return "", fmt.Errorf("invalid gateway URL: %s", base)
	}
	return parsed.String(), nil
}
