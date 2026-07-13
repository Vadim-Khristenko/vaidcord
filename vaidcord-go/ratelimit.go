package vaidcord

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
)

// rateLimiter tracks per-route rate-limit buckets from X-RateLimit-* headers
// plus the global rate-limit window. Requests to the same bucket serialise
// while the bucket is exhausted; requests to different buckets proceed
// independently.
type rateLimiter struct {
	mu          sync.Mutex
	buckets     map[string]*rateLimitBucket
	globalUntil time.Time
}

type rateLimitBucket struct {
	mu        sync.Mutex
	remaining int
	resetAt   time.Time
	known     bool // whether headers have populated this bucket yet
}

func newRateLimiter() *rateLimiter {
	return &rateLimiter{buckets: make(map[string]*rateLimitBucket)}
}

// routeBucketKey normalises a request path into a rate-limit route key.
// Major parameters (the IDs directly following channels/guilds/webhooks)
// stay in the key; every other snowflake collapses to ":id" so e.g. all
// message deletes in one channel share a bucket.
func routeBucketKey(method, path string) string {
	segments := strings.Split(strings.Trim(path, "/"), "/")
	var builder strings.Builder
	builder.WriteString(method)
	builder.WriteByte(' ')
	previous := ""
	for index, segment := range segments {
		if index > 0 {
			builder.WriteByte('/')
		}
		if isSnowflake(segment) && previous != "channels" && previous != "guilds" && previous != "webhooks" {
			builder.WriteString(":id")
		} else {
			builder.WriteString(segment)
		}
		previous = segment
	}
	return builder.String()
}

func isSnowflake(segment string) bool {
	if len(segment) < 15 {
		return false
	}
	for _, char := range segment {
		if char < '0' || char > '9' {
			return false
		}
	}
	return true
}

func (l *rateLimiter) bucket(key string) *rateLimitBucket {
	l.mu.Lock()
	defer l.mu.Unlock()
	bucket := l.buckets[key]
	if bucket == nil {
		bucket = &rateLimitBucket{remaining: 1}
		l.buckets[key] = bucket
	}
	return bucket
}

// wait blocks until the route bucket (and the global window) allow one more
// request, then optimistically consumes a slot.
func (l *rateLimiter) wait(ctx context.Context, key string) error {
	if err := l.waitGlobal(ctx); err != nil {
		return err
	}
	bucket := l.bucket(key)
	bucket.mu.Lock()
	defer bucket.mu.Unlock()
	for bucket.known && bucket.remaining <= 0 {
		delay := time.Until(bucket.resetAt)
		if delay <= 0 {
			bucket.remaining = 1
			bucket.known = false
			break
		}
		bucket.mu.Unlock()
		err := sleepContext(ctx, delay)
		bucket.mu.Lock()
		if err != nil {
			return err
		}
	}
	if bucket.known {
		bucket.remaining--
	}
	return nil
}

func (l *rateLimiter) waitGlobal(ctx context.Context) error {
	for {
		l.mu.Lock()
		delay := time.Until(l.globalUntil)
		l.mu.Unlock()
		if delay <= 0 {
			return nil
		}
		if err := sleepContext(ctx, delay); err != nil {
			return err
		}
	}
}

// update ingests X-RateLimit-* headers from a response.
func (l *rateLimiter) update(key string, header http.Header) {
	remaining, remainingErr := strconv.Atoi(header.Get("X-RateLimit-Remaining"))
	resetAfter, resetErr := strconv.ParseFloat(header.Get("X-RateLimit-Reset-After"), 64)
	if remainingErr != nil || resetErr != nil {
		return
	}
	bucket := l.bucket(key)
	bucket.mu.Lock()
	bucket.remaining = remaining
	bucket.resetAt = time.Now().Add(time.Duration(resetAfter * float64(time.Second)))
	bucket.known = true
	bucket.mu.Unlock()
}

// handle429 records the retry-after window (global or per-route) and returns
// how long the caller should sleep before retrying.
func (l *rateLimiter) handle429(key string, header http.Header, body []byte) time.Duration {
	retryAfter := parseRetryAfter(header, body)
	if strings.EqualFold(header.Get("X-RateLimit-Global"), "true") {
		l.mu.Lock()
		until := time.Now().Add(retryAfter)
		if until.After(l.globalUntil) {
			l.globalUntil = until
		}
		l.mu.Unlock()
		return retryAfter
	}
	bucket := l.bucket(key)
	bucket.mu.Lock()
	bucket.remaining = 0
	bucket.resetAt = time.Now().Add(retryAfter)
	bucket.known = true
	bucket.mu.Unlock()
	return retryAfter
}

func parseRetryAfter(header http.Header, body []byte) time.Duration {
	if value := header.Get("Retry-After"); value != "" {
		if seconds, err := strconv.ParseFloat(value, 64); err == nil && seconds >= 0 {
			return time.Duration(seconds * float64(time.Second))
		}
	}
	if seconds, ok := retryAfterFromBody(body); ok {
		return time.Duration(seconds * float64(time.Second))
	}
	return time.Second
}

func retryAfterFromBody(body []byte) (float64, bool) {
	var decoded struct {
		RetryAfter *float64 `json:"retry_after"`
	}
	if json.Unmarshal(body, &decoded) != nil || decoded.RetryAfter == nil || *decoded.RetryAfter < 0 {
		return 0, false
	}
	return *decoded.RetryAfter, true
}
