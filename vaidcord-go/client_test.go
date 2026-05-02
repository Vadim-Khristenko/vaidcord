package vaidcord

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return fn(req)
}

func TestClientGetCurrentUser(t *testing.T) {
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if r.URL.Path != "/api/v10/users/@me" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if got := r.Header.Get("Authorization"); got != "Bot token" {
			t.Fatalf("unexpected authorization header: %s", got)
		}
		if got := r.Header.Get("User-Agent"); got != UserAgent {
			t.Fatalf("unexpected user-agent header: %s", got)
		}
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(strings.NewReader(`{"id":"42","username":"vaidcord"}`)),
		}, nil
	})}

	client := NewClient(Config{Token: "token"}, httpClient)

	user, err := client.GetCurrentUser(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if user.ID != "42" || user.Username != "vaidcord" {
		t.Fatalf("unexpected user payload: %#v", user)
	}
}

func TestClientConfiguresProxyTransport(t *testing.T) {
	client := NewClient(Config{Token: "token", ProxyURL: "http://127.0.0.1:8080"}, nil)

	transport, ok := client.http.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("expected http.Transport, got %T", client.http.Transport)
	}
	if transport.Proxy == nil {
		t.Fatal("expected proxy function to be configured")
	}
}

func TestClientSendMessageEncodesJSONAndErrors(t *testing.T) {
	var captured map[string]any
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if r.Method != http.MethodPost {
			t.Fatalf("unexpected method: %s", r.Method)
		}
		if r.URL.Path != "/api/v10/channels/123/messages" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if got := r.Header.Get("Content-Type"); got != "application/json" {
			t.Fatalf("unexpected content-type header: %s", got)
		}
		if err := json.NewDecoder(r.Body).Decode(&captured); err != nil {
			t.Fatal(err)
		}
		return &http.Response{
			StatusCode: http.StatusBadRequest,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(strings.NewReader(`{"code":50035,"message":"Invalid Form Body"}`)),
		}, nil
	})}

	client := NewClient(Config{Token: "token"}, httpClient)

	_, err := client.SendMessage(context.Background(), "123", MessagePayload{Content: "hello"})
	if err == nil {
		t.Fatal("expected api error")
	}
	var apiErr *APIError
	if !errors.As(err, &apiErr) {
		t.Fatalf("expected APIError, got %T", err)
	}
	if apiErr.Code != 50035 {
		t.Fatalf("unexpected api error: %#v", apiErr)
	}
	if captured["content"] != "hello" {
		t.Fatalf("unexpected request payload: %#v", captured)
	}
}

func TestClientSendMessageDecodesTypedMessage(t *testing.T) {
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(strings.NewReader(`{"id":"900","channel_id":"123","author":{"id":"42","username":"vaidcord"},"content":"pong"}`)),
		}, nil
	})}

	client := NewClient(Config{Token: "token"}, httpClient)

	message, err := client.SendMessage(context.Background(), "123", MessagePayload{Content: "pong"})
	if err != nil {
		t.Fatal(err)
	}
	if message.ID != "900" || message.Author.Username != "vaidcord" || message.Content != "pong" {
		t.Fatalf("unexpected typed message: %#v", message)
	}
}

func TestClientBulkOverwriteGlobalCommands(t *testing.T) {
	var captured []map[string]any
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if r.Method != http.MethodPut {
			t.Fatalf("unexpected method: %s", r.Method)
		}
		if r.URL.Path != "/api/v10/applications/42/commands" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if err := json.NewDecoder(r.Body).Decode(&captured); err != nil {
			t.Fatal(err)
		}
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(strings.NewReader(`[{"id":"1","name":"start","type":1}]`)),
		}, nil
	})}

	client := NewClient(Config{Token: "token"}, httpClient)
	commands, err := client.BulkOverwriteGlobalCommands(
		context.Background(),
		"42",
		[]map[string]any{{"name": "start", "type": 1, "description": "Start bot"}},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(commands) != 1 || commands[0]["name"] != "start" {
		t.Fatalf("unexpected commands response: %#v", commands)
	}
	if len(captured) != 1 || captured[0]["name"] != "start" {
		t.Fatalf("unexpected request payload: %#v", captured)
	}
}

func TestClientBulkOverwriteGuildCommands(t *testing.T) {
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if r.Method != http.MethodPut {
			t.Fatalf("unexpected method: %s", r.Method)
		}
		if r.URL.Path != "/api/v10/applications/42/guilds/777/commands" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(strings.NewReader(`[{"id":"1","name":"ping","type":1}]`)),
		}, nil
	})}

	client := NewClient(Config{Token: "token"}, httpClient)
	commands, err := client.BulkOverwriteGuildCommands(
		context.Background(),
		"42",
		"777",
		[]map[string]any{{"name": "ping", "type": 1, "description": "Ping"}},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(commands) != 1 || commands[0]["name"] != "ping" {
		t.Fatalf("unexpected commands response: %#v", commands)
	}
}

func TestVoiceCloseCodeReconnectPolicy(t *testing.T) {
	if VoiceCloseE2EEDaveRequired != 4017 {
		t.Fatalf("unexpected DAVE required close code: %d", VoiceCloseE2EEDaveRequired)
	}
	if VoiceCloseDisconnected.ShouldReconnect() {
		t.Fatal("disconnect close code should not reconnect")
	}
	if !VoiceCloseVoiceServerCrashed.ShouldReconnect() {
		t.Fatal("server crash close code should reconnect")
	}
}
