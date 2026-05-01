package vaidcord

import (
	"context"
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
	if user["id"] != "42" {
		t.Fatalf("unexpected user payload: %#v", user)
	}
}
