package vaidcord

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

func TestParseDispatchTypedEvents(t *testing.T) {
	ready, ok := ParseDispatch(GatewayDispatch{
		Op:   GatewayOpDispatch,
		Type: "READY",
		Data: json.RawMessage(`{"user":{"id":"1","username":"bot"},"session_id":"s1","resume_gateway_url":"wss://x","application":{"id":"app-1"}}`),
	})
	if !ok || ready.Ready == nil {
		t.Fatal("READY not parsed")
	}
	if ready.Ready.User.ID != "1" || ready.Ready.SessionID != "s1" || ready.Ready.ApplicationID != "app-1" {
		t.Fatalf("unexpected READY: %+v", ready.Ready)
	}

	message, ok := ParseDispatch(GatewayDispatch{
		Op:   GatewayOpDispatch,
		Type: "MESSAGE_CREATE",
		Data: json.RawMessage(`{"id":"m1","channel_id":"c1","author":{"id":"2","username":"u"},"content":"!ping"}`),
	})
	if !ok || message.Message == nil || message.Message.Content != "!ping" {
		t.Fatalf("MESSAGE_CREATE not parsed: %+v", message.Message)
	}

	deleted, ok := ParseDispatch(GatewayDispatch{
		Op:   GatewayOpDispatch,
		Type: "MESSAGE_DELETE",
		Data: json.RawMessage(`{"id":"m1","channel_id":"c1"}`),
	})
	if !ok || deleted.Deleted == nil || deleted.Deleted.ID != "m1" {
		t.Fatalf("MESSAGE_DELETE not parsed: %+v", deleted.Deleted)
	}

	guild, ok := ParseDispatch(GatewayDispatch{
		Op:   GatewayOpDispatch,
		Type: "GUILD_CREATE",
		Data: json.RawMessage(`{"id":"g1","name":"Guild","member_count":3,"roles":[{"id":"r1","name":"admin"}],"channels":[{"id":"c1","type":0}]}`),
	})
	if !ok || guild.Guild == nil || guild.Guild.Name != "Guild" || len(guild.Guild.Roles) != 1 {
		t.Fatalf("GUILD_CREATE not parsed: %+v", guild.Guild)
	}

	interaction, ok := ParseDispatch(GatewayDispatch{
		Op:   GatewayOpDispatch,
		Type: "INTERACTION_CREATE",
		Data: json.RawMessage(`{"id":"i1","application_id":"app","type":2,"token":"tok","data":{"name":"ping","type":1}}`),
	})
	if !ok || interaction.Interaction == nil || interaction.Interaction.Data.Name != "ping" {
		t.Fatalf("INTERACTION_CREATE not parsed: %+v", interaction.Interaction)
	}

	unknown, ok := ParseDispatch(GatewayDispatch{
		Op:   GatewayOpDispatch,
		Type: "TYPING_START",
		Data: json.RawMessage(`{"channel_id":"c1"}`),
	})
	if !ok || unknown.Type != EventType("TYPING_START") || len(unknown.Raw) == 0 {
		t.Fatal("unknown events must still expose the raw payload")
	}
}

// TestBotRunEndToEnd drives the full facade: NewBot -> Include -> Run
// against a scripted gateway, checking that dispatches reach typed handlers.
func TestBotRunEndToEnd(t *testing.T) {
	fake := newFakeGateway(t,
		func(conn *websocket.Conn, _ int) {
			wsSend(t, conn, `{"op":10,"d":{"heartbeat_interval":60000}}`)
			wsExpect(t, conn, GatewayOpIdentify)
			wsSend(t, conn, `{"op":0,"t":"READY","s":1,"d":{"session_id":"s","resume_gateway_url":"","user":{"id":"1","username":"bot"}}}`)
			wsSend(t, conn, `{"op":0,"t":"MESSAGE_CREATE","s":2,"d":{"id":"m1","channel_id":"c1","author":{"id":"2","username":"u"},"content":"!ping now"}}`)
			wsSend(t, conn, `{"op":0,"t":"MESSAGE_CREATE","s":3,"d":{"id":"m2","channel_id":"c1","author":{"id":"2","username":"u"},"content":"unrelated"}}`)
			wsSend(t, conn, `{"op":0,"t":"INTERACTION_CREATE","s":4,"d":{"id":"i1","application_id":"a","type":2,"token":"tok","data":{"name":"hello","type":1}}}`)
			time.Sleep(100 * time.Millisecond)
			wsClose(conn, 4004)
		},
	)

	var mu sync.Mutex
	var pings, interactions, readies []string

	router := NewRouter("test")
	router.OnReady().Handle(func(_ context.Context, ready ReadyEvent) error {
		mu.Lock()
		readies = append(readies, ready.User.Username)
		mu.Unlock()
		return nil
	})
	router.OnMessageCreate(Command("ping")).Handle(func(_ context.Context, message Message) error {
		mu.Lock()
		pings = append(pings, message.Content)
		mu.Unlock()
		return nil
	})
	router.OnInteractionCreate(SlashCommand("hello")).Handle(func(_ context.Context, interaction Interaction) error {
		mu.Lock()
		interactions = append(interactions, interaction.ID)
		mu.Unlock()
		return nil
	})

	bot := NewBot(
		BotConfig{Config: Config{Token: "token", BaseURL: fake.server.URL + "/api"}},
		WithHTTPClient(fake.server.Client()),
	)
	bot.Include(router)

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	err := bot.Run(ctx)
	var closed *GatewayClosedError
	if !errors.As(err, &closed) || closed.Code != 4004 {
		t.Fatalf("expected fatal 4004 close, got %v", err)
	}

	mu.Lock()
	defer mu.Unlock()
	if len(readies) != 1 || readies[0] != "bot" {
		t.Fatalf("READY handler not invoked: %v", readies)
	}
	if len(pings) != 1 || pings[0] != "!ping now" {
		t.Fatalf("filtered message handler mismatch: %v", pings)
	}
	if len(interactions) != 1 || interactions[0] != "i1" {
		t.Fatalf("interaction handler mismatch: %v", interactions)
	}
	if bot.API() == nil || bot.Gateway() == nil || bot.Dispatcher() == nil {
		t.Fatal("facade accessors must be wired")
	}
}

// TestDispatcherStartPolling exercises the low-level polling loop that
// replaced the stub.
func TestDispatcherStartPolling(t *testing.T) {
	fake := newFakeGateway(t,
		func(conn *websocket.Conn, _ int) {
			wsSend(t, conn, `{"op":10,"d":{"heartbeat_interval":60000}}`)
			wsExpect(t, conn, GatewayOpIdentify)
			wsSend(t, conn, `{"op":0,"t":"MESSAGE_CREATE","s":1,"d":{"id":"m1","channel_id":"c1","author":{"id":"2","username":"u"},"content":"hi"}}`)
			time.Sleep(100 * time.Millisecond)
			wsClose(conn, 4004)
		},
	)
	var mu sync.Mutex
	var contents []string
	router := NewRouter("poll")
	router.OnMessageCreate().Handle(func(_ context.Context, message Message) error {
		mu.Lock()
		contents = append(contents, message.Content)
		mu.Unlock()
		return nil
	})
	dispatcher := NewDispatcher()
	dispatcher.Include(router)

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	err := dispatcher.StartPolling(ctx, fake.client(), WithIntents(IntentsDefault|IntentMessageContent))
	var closed *GatewayClosedError
	if !errors.As(err, &closed) || closed.Code != 4004 {
		t.Fatalf("expected fatal 4004 close, got %v", err)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(contents) != 1 || contents[0] != "hi" {
		t.Fatalf("StartPolling did not dispatch: %v", contents)
	}
}
