package vaidcord

import (
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestRouteBucketKeyMajorParameters(t *testing.T) {
	cases := []struct {
		method string
		path   string
		key    string
	}{
		{
			http.MethodDelete,
			"/channels/123456789012345678/messages/987654321098765432",
			"DELETE channels/123456789012345678/messages/:id",
		},
		{
			http.MethodGet,
			"/guilds/123456789012345678/members/987654321098765432",
			"GET guilds/123456789012345678/members/:id",
		},
		{
			http.MethodPost,
			"/webhooks/123456789012345678/token-value",
			"POST webhooks/123456789012345678/token-value",
		},
		{
			http.MethodGet,
			"/users/@me",
			"GET users/@me",
		},
	}
	for _, testCase := range cases {
		if got := routeBucketKey(testCase.method, testCase.path); got != testCase.key {
			t.Fatalf("%s %s: expected %q, got %q", testCase.method, testCase.path, testCase.key, got)
		}
	}
	// Same channel, different messages share a bucket; different channels don't.
	a := routeBucketKey(http.MethodDelete, "/channels/111111111111111111/messages/222222222222222222")
	b := routeBucketKey(http.MethodDelete, "/channels/111111111111111111/messages/333333333333333333")
	c := routeBucketKey(http.MethodDelete, "/channels/444444444444444444/messages/222222222222222222")
	if a != b {
		t.Fatalf("expected shared bucket, got %q vs %q", a, b)
	}
	if a == c {
		t.Fatalf("expected distinct buckets per channel, got %q", a)
	}
}

func jsonResponse(status int, body string, header http.Header) *http.Response {
	if header == nil {
		header = http.Header{}
	}
	header.Set("Content-Type", "application/json")
	return &http.Response{
		StatusCode: status,
		Header:     header,
		Body:       io.NopCloser(strings.NewReader(body)),
	}
}

// headers builds an http.Header with canonicalised keys (as the net/http
// response parser would).
func headers(pairs ...string) http.Header {
	header := http.Header{}
	for i := 0; i+1 < len(pairs); i += 2 {
		header.Set(pairs[i], pairs[i+1])
	}
	return header
}

func TestClientRetriesAfter429(t *testing.T) {
	var calls int32
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if atomic.AddInt32(&calls, 1) == 1 {
			return jsonResponse(http.StatusTooManyRequests,
				`{"message":"You are being rate limited.","retry_after":0.02,"global":false}`,
				headers("Retry-After", "0.02"),
			), nil
		}
		return jsonResponse(http.StatusOK, `{"id":"42","username":"vaidcord"}`, nil), nil
	})}
	client := NewClient(Config{Token: "token"}, httpClient)

	started := time.Now()
	user, err := client.GetCurrentUser(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if user.ID != "42" {
		t.Fatalf("unexpected user: %+v", user)
	}
	if got := atomic.LoadInt32(&calls); got != 2 {
		t.Fatalf("expected 2 requests, got %d", got)
	}
	if elapsed := time.Since(started); elapsed < 20*time.Millisecond {
		t.Fatalf("429 retry did not honour retry_after: %v", elapsed)
	}
}

func TestClientWaitsForExhaustedBucket(t *testing.T) {
	var calls int32
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		atomic.AddInt32(&calls, 1)
		return jsonResponse(http.StatusOK, `{"id":"42","username":"vaidcord"}`, headers(
			"X-RateLimit-Remaining", "0",
			"X-RateLimit-Reset-After", "0.05",
		)), nil
	})}
	client := NewClient(Config{Token: "token"}, httpClient)

	if _, err := client.GetCurrentUser(context.Background()); err != nil {
		t.Fatal(err)
	}
	started := time.Now()
	if _, err := client.GetCurrentUser(context.Background()); err != nil {
		t.Fatal(err)
	}
	if elapsed := time.Since(started); elapsed < 45*time.Millisecond {
		t.Fatalf("second request did not wait for bucket reset: %v", elapsed)
	}
	if got := atomic.LoadInt32(&calls); got != 2 {
		t.Fatalf("expected 2 requests, got %d", got)
	}
}

func TestClientRetriesOn5xx(t *testing.T) {
	var calls int32
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if atomic.AddInt32(&calls, 1) < 3 {
			return jsonResponse(http.StatusBadGateway, `{"message":"bad gateway"}`, nil), nil
		}
		return jsonResponse(http.StatusOK, `{"id":"42","username":"vaidcord"}`, nil), nil
	})}
	client := NewClient(Config{Token: "token"}, httpClient)

	user, err := client.GetCurrentUser(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if user.ID != "42" || atomic.LoadInt32(&calls) != 3 {
		t.Fatalf("unexpected result: %+v after %d calls", user, calls)
	}
}

func TestClientRetriesOnNetworkError(t *testing.T) {
	var calls int32
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if atomic.AddInt32(&calls, 1) == 1 {
			return nil, errors.New("connection reset by peer")
		}
		return jsonResponse(http.StatusOK, `{"id":"42","username":"vaidcord"}`, nil), nil
	})}
	client := NewClient(Config{Token: "token"}, httpClient)

	if _, err := client.GetCurrentUser(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := atomic.LoadInt32(&calls); got != 2 {
		t.Fatalf("expected 2 requests, got %d", got)
	}
}

func TestClientGivesUpAfterMaxRetries(t *testing.T) {
	var calls int32
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		atomic.AddInt32(&calls, 1)
		return jsonResponse(http.StatusInternalServerError, `{"message":"boom"}`, nil), nil
	})}
	client := NewClient(Config{Token: "token", MaxRetries: 2}, httpClient)

	_, err := client.GetCurrentUser(context.Background())
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.StatusCode != http.StatusInternalServerError {
		t.Fatalf("expected 500 APIError, got %v", err)
	}
	if got := atomic.LoadInt32(&calls); got != 3 { // 1 try + 2 retries
		t.Fatalf("expected 3 requests, got %d", got)
	}
}

func TestClientDoesNotRetryOn4xx(t *testing.T) {
	var calls int32
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		atomic.AddInt32(&calls, 1)
		return jsonResponse(http.StatusNotFound, `{"code":10003,"message":"Unknown Channel"}`, nil), nil
	})}
	client := NewClient(Config{Token: "token"}, httpClient)

	_, err := client.FetchChannel(context.Background(), "123")
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.Code != 10003 {
		t.Fatalf("expected Unknown Channel APIError, got %v", err)
	}
	if got := atomic.LoadInt32(&calls); got != 1 {
		t.Fatalf("4xx must not be retried, got %d calls", got)
	}
}

func TestRateLimiterGlobalWindowPausesAllRoutes(t *testing.T) {
	limiter := newRateLimiter()
	limiter.handle429("GET users/@me", headers(
		"X-RateLimit-Global", "true",
		"Retry-After", "0.05",
	), nil)
	started := time.Now()
	if err := limiter.wait(context.Background(), "GET channels/1"); err != nil {
		t.Fatal(err)
	}
	if elapsed := time.Since(started); elapsed < 45*time.Millisecond {
		t.Fatalf("global window did not pause an unrelated route: %v", elapsed)
	}
}

func TestRateLimiterWaitHonoursContext(t *testing.T) {
	limiter := newRateLimiter()
	limiter.handle429("GET users/@me", headers("Retry-After", "5"), nil)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	if err := limiter.wait(ctx, "GET users/@me"); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected deadline exceeded, got %v", err)
	}
}

func TestClientContextCancellationStopsRetries(t *testing.T) {
	var calls int32
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		atomic.AddInt32(&calls, 1)
		return jsonResponse(http.StatusInternalServerError, `{}`, nil), nil
	})}
	client := NewClient(Config{Token: "token"}, httpClient)
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	_, err := client.GetCurrentUser(ctx)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected deadline exceeded, got %v", err)
	}
}
