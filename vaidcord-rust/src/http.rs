//! HTTP rate limiting: per-route buckets fed by `X-RateLimit-*` headers.
//!
//! Requests are keyed by [`route_bucket_key`] (method + path with only the
//! *major* parameters kept — channel id, guild id, webhook id/token — and
//! every other id normalized). Before a request the bucket is awaited if
//! exhausted; after a response the bucket is refreshed from the reply
//! headers. 429s set an explicit penalty from `retry_after`.

use std::collections::HashMap;
use std::sync::Mutex;
use std::sync::Arc;

use tokio::time::{Duration, Instant};

/// Parsed `X-RateLimit-*` response headers.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct RateLimitInfo {
    pub limit: Option<u64>,
    pub remaining: Option<u64>,
    /// Seconds until the bucket resets.
    pub reset_after: Option<f64>,
    pub bucket: Option<String>,
    pub is_global: bool,
    /// Present on 429 responses.
    pub retry_after: Option<f64>,
}

/// Parse the Discord rate-limit headers from a response header map.
pub fn parse_rate_limit_headers(headers: &reqwest::header::HeaderMap) -> RateLimitInfo {
    fn get<T: std::str::FromStr>(headers: &reqwest::header::HeaderMap, name: &str) -> Option<T> {
        headers
            .get(name)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.parse().ok())
    }
    RateLimitInfo {
        limit: get(headers, "x-ratelimit-limit"),
        remaining: get(headers, "x-ratelimit-remaining"),
        reset_after: get(headers, "x-ratelimit-reset-after"),
        bucket: get(headers, "x-ratelimit-bucket"),
        is_global: headers
            .get("x-ratelimit-global")
            .and_then(|value| value.to_str().ok())
            .map(|value| value.eq_ignore_ascii_case("true"))
            .unwrap_or(false),
        retry_after: get(headers, "retry-after"),
    }
}

/// Compute the rate-limit bucket key for a request.
///
/// Major parameters (channel id, guild id, webhook id + token) stay in the
/// key; every other snowflake-looking segment is replaced with `:id` so all
/// e.g. message ids in one channel share a bucket, matching Discord's model.
pub fn route_bucket_key(method: &str, path: &str) -> String {
    let mut out = String::with_capacity(path.len() + method.len() + 1);
    out.push_str(method);
    out.push(':');
    let mut previous = "";
    for (index, segment) in path.trim_matches('/').split('/').enumerate() {
        if index > 0 {
            out.push('/');
        }
        let is_major = matches!(previous, "channels" | "guilds" | "webhooks");
        if !is_major && looks_like_snowflake(segment) {
            out.push_str(":id");
        } else {
            out.push_str(segment);
        }
        previous = segment;
    }
    out
}

fn looks_like_snowflake(segment: &str) -> bool {
    segment.len() >= 15 && segment.bytes().all(|byte| byte.is_ascii_digit())
}

#[derive(Debug, Default)]
struct BucketState {
    remaining: Option<u64>,
    reset_at: Option<Instant>,
}

/// Tracks one bucket per route key plus a process-wide global limit.
#[derive(Debug, Default)]
pub struct RateLimiter {
    buckets: Mutex<HashMap<String, Arc<tokio::sync::Mutex<BucketState>>>>,
    global_until: Mutex<Option<Instant>>,
}

impl RateLimiter {
    pub fn new() -> Self {
        Self::default()
    }

    fn bucket(&self, key: &str) -> Arc<tokio::sync::Mutex<BucketState>> {
        let mut buckets = self.buckets.lock().expect("rate limiter poisoned");
        Arc::clone(buckets.entry(key.to_string()).or_default())
    }

    fn global_delay(&self) -> Option<Duration> {
        let until = *self.global_until.lock().expect("rate limiter poisoned");
        until.and_then(|at| at.checked_duration_since(Instant::now()))
    }

    /// Wait until the route's bucket (and the global limit) allow a request.
    pub async fn acquire(&self, key: &str) {
        if let Some(delay) = self.global_delay() {
            tokio::time::sleep(delay).await;
        }
        let bucket = self.bucket(key);
        let mut state = bucket.lock().await;
        if state.remaining == Some(0)
            && let Some(reset_at) = state.reset_at
            && let Some(delay) = reset_at.checked_duration_since(Instant::now())
        {
            tokio::time::sleep(delay).await;
            state.remaining = None;
            state.reset_at = None;
        }
        // Provisionally consume a slot so concurrent tasks don't stampede.
        if let Some(remaining) = state.remaining.as_mut()
            && *remaining > 0
        {
            *remaining -= 1;
        }
    }

    /// Refresh a bucket from response headers.
    pub async fn update(&self, key: &str, info: &RateLimitInfo) {
        let bucket = self.bucket(key);
        let mut state = bucket.lock().await;
        state.remaining = info.remaining;
        state.reset_at = info
            .reset_after
            .map(|seconds| Instant::now() + Duration::from_secs_f64(seconds.max(0.0)));
    }

    /// Apply a 429 penalty (`retry_after` seconds) to a route or globally.
    pub async fn penalize(&self, key: &str, retry_after: f64, global: bool) {
        let until = Instant::now() + Duration::from_secs_f64(retry_after.max(0.0));
        if global {
            let mut global_until = self.global_until.lock().expect("rate limiter poisoned");
            *global_until = Some((*global_until).map_or(until, |existing| existing.max(until)));
            return;
        }
        let bucket = self.bucket(key);
        let mut state = bucket.lock().await;
        state.remaining = Some(0);
        state.reset_at = Some(until);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use reqwest::header::{HeaderMap, HeaderValue};

    fn headers(pairs: &[(&str, &str)]) -> HeaderMap {
        let mut map = HeaderMap::new();
        for (name, value) in pairs {
            map.insert(
                reqwest::header::HeaderName::from_bytes(name.as_bytes()).unwrap(),
                HeaderValue::from_str(value).unwrap(),
            );
        }
        map
    }

    #[test]
    fn parses_rate_limit_headers() {
        let info = parse_rate_limit_headers(&headers(&[
            ("x-ratelimit-limit", "5"),
            ("x-ratelimit-remaining", "3"),
            ("x-ratelimit-reset-after", "1.25"),
            ("x-ratelimit-bucket", "abcd1234"),
        ]));
        assert_eq!(info.limit, Some(5));
        assert_eq!(info.remaining, Some(3));
        assert_eq!(info.reset_after, Some(1.25));
        assert_eq!(info.bucket.as_deref(), Some("abcd1234"));
        assert!(!info.is_global);
        assert_eq!(info.retry_after, None);
    }

    #[test]
    fn parses_global_429_headers() {
        let info = parse_rate_limit_headers(&headers(&[
            ("x-ratelimit-global", "true"),
            ("retry-after", "6.5"),
        ]));
        assert!(info.is_global);
        assert_eq!(info.retry_after, Some(6.5));
    }

    #[test]
    fn missing_headers_parse_to_none() {
        let info = parse_rate_limit_headers(&HeaderMap::new());
        assert_eq!(info, RateLimitInfo::default());
    }

    #[test]
    fn bucket_key_keeps_major_parameters() {
        assert_eq!(
            route_bucket_key("GET", "/channels/123456789012345678/messages"),
            "GET:channels/123456789012345678/messages"
        );
        assert_eq!(
            route_bucket_key("DELETE", "/channels/123456789012345678/messages/876543210987654321"),
            "DELETE:channels/123456789012345678/messages/:id"
        );
        assert_eq!(
            route_bucket_key("GET", "/guilds/123456789012345678/members/876543210987654321"),
            "GET:guilds/123456789012345678/members/:id"
        );
    }

    #[test]
    fn bucket_key_leaves_non_snowflake_segments() {
        assert_eq!(route_bucket_key("GET", "/users/@me"), "GET:users/@me");
        assert_eq!(route_bucket_key("GET", "/gateway/bot"), "GET:gateway/bot");
    }

    #[tokio::test]
    async fn limiter_delays_when_bucket_exhausted() {
        tokio::time::pause();
        let limiter = RateLimiter::new();
        limiter
            .update(
                "k",
                &RateLimitInfo {
                    remaining: Some(0),
                    reset_after: Some(2.0),
                    ..Default::default()
                },
            )
            .await;
        let started = Instant::now();
        limiter.acquire("k").await;
        assert!(started.elapsed() >= Duration::from_secs(2));
    }

    #[tokio::test]
    async fn limiter_does_not_delay_with_remaining_budget() {
        tokio::time::pause();
        let limiter = RateLimiter::new();
        limiter
            .update(
                "k",
                &RateLimitInfo {
                    remaining: Some(3),
                    reset_after: Some(60.0),
                    ..Default::default()
                },
            )
            .await;
        let started = Instant::now();
        limiter.acquire("k").await;
        assert_eq!(started.elapsed(), Duration::ZERO);
    }

    #[tokio::test]
    async fn global_penalty_blocks_every_route() {
        tokio::time::pause();
        let limiter = RateLimiter::new();
        limiter.penalize("any", 3.0, true).await;
        let started = Instant::now();
        limiter.acquire("other-route").await;
        assert!(started.elapsed() >= Duration::from_secs(3));
    }
}
