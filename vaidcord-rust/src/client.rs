//! Discord REST client with per-route rate-limit buckets and retries.
//!
//! Every request flows through the shared [`RateLimiter`]: the route bucket
//! is awaited before sending, refreshed from `X-RateLimit-*` reply headers,
//! and 429s sleep for `retry_after` and retry. 5xx and transport errors are
//! retried with exponential backoff.

use std::sync::Arc;

use serde::{Serialize, de::DeserializeOwned};
use serde_json::Value;
use tokio::time::Duration;

use crate::USER_AGENT;
use crate::config::Config;
use crate::error::{DiscordApiErrorBody, Error};
use crate::http::{RateLimiter, parse_rate_limit_headers, route_bucket_key};
use crate::models::{
    Channel, Guild, InteractionResponse, Member, Message, MessagePayload, Role, User,
};

/// Maximum attempts per request (including the first one).
const MAX_ATTEMPTS: u32 = 5;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RequestParts {
    pub method: String,
    pub url: String,
    pub authorization: String,
    pub user_agent: String,
    pub content_type: Option<String>,
}

/// REST client. Cheap to clone; clones share the rate limiter and the
/// underlying connection pool.
#[derive(Debug, Clone)]
pub struct Client {
    config: Config,
    http: reqwest::Client,
    rate_limiter: Arc<RateLimiter>,
}

impl Client {
    pub fn new(config: Config) -> Self {
        let http = build_http_client(&config);
        Self::with_http_client(config, http)
    }

    pub fn with_http_client(config: Config, http: reqwest::Client) -> Self {
        Self {
            config,
            http,
            rate_limiter: Arc::new(RateLimiter::new()),
        }
    }

    pub fn config(&self) -> &Config {
        &self.config
    }

    pub fn endpoint(&self, path: &str) -> String {
        format!(
            "{}/v{}/{}",
            self.config.base_url.trim_end_matches('/'),
            self.config.api_version,
            path.trim_start_matches('/')
        )
    }

    pub fn request_parts(
        &self,
        method: impl Into<String>,
        path: &str,
        has_json_body: bool,
    ) -> RequestParts {
        RequestParts {
            method: method.into(),
            url: self.endpoint(path),
            authorization: format!("Bot {}", self.config.token),
            user_agent: USER_AGENT.to_string(),
            content_type: has_json_body.then(|| "application/json".to_string()),
        }
    }

    fn request_builder(&self, method: reqwest::Method, path: &str) -> reqwest::RequestBuilder {
        self.http
            .request(method, self.endpoint(path))
            .header(
                reqwest::header::AUTHORIZATION,
                format!("Bot {}", self.config.token),
            )
            .header(reqwest::header::USER_AGENT, USER_AGENT)
            .header(reqwest::header::ACCEPT, "application/json")
    }

    /// Perform a request and return the raw response body on success.
    ///
    /// Handles rate limiting (bucket wait, 429 sleep-and-retry via
    /// `retry_after`) and retries 5xx/transport errors with backoff.
    async fn request_text<B>(
        &self,
        method: reqwest::Method,
        path: &str,
        body: Option<&B>,
    ) -> Result<String, Error>
    where
        B: Serialize + ?Sized,
    {
        let bucket_key = route_bucket_key(method.as_str(), path);
        let mut backoff = Duration::from_millis(500);
        let mut last_error: Option<Error> = None;

        for attempt in 0..MAX_ATTEMPTS {
            self.rate_limiter.acquire(&bucket_key).await;

            let mut request = self.request_builder(method.clone(), path);
            if let Some(body) = body {
                request = request.json(body);
            }

            let response = match request.send().await {
                Ok(response) => response,
                Err(error) => {
                    last_error = Some(Error::Http(error));
                    if attempt + 1 < MAX_ATTEMPTS {
                        tokio::time::sleep(backoff).await;
                        backoff *= 2;
                        continue;
                    }
                    break;
                }
            };

            let status = response.status();
            let rate_info = parse_rate_limit_headers(response.headers());
            self.rate_limiter.update(&bucket_key, &rate_info).await;
            let text = response.text().await.unwrap_or_default();

            if status == reqwest::StatusCode::TOO_MANY_REQUESTS {
                let retry_after = rate_info
                    .retry_after
                    .or_else(|| {
                        serde_json::from_str::<Value>(&text)
                            .ok()
                            .and_then(|body| body.get("retry_after").and_then(Value::as_f64))
                    })
                    .unwrap_or(1.0);
                self.rate_limiter
                    .penalize(&bucket_key, retry_after, rate_info.is_global)
                    .await;
                last_error = Some(Error::Other(format!(
                    "rate limited on {bucket_key} (retry_after {retry_after}s)"
                )));
                continue;
            }

            if status.is_server_error() && attempt + 1 < MAX_ATTEMPTS {
                last_error = Some(Error::Api {
                    status,
                    code: None,
                    message: None,
                    body: text,
                });
                tokio::time::sleep(backoff).await;
                backoff *= 2;
                continue;
            }

            if !status.is_success() {
                let decoded = serde_json::from_str::<DiscordApiErrorBody>(&text).ok();
                return Err(Error::Api {
                    status,
                    code: decoded.as_ref().and_then(|value| value.code),
                    message: decoded.and_then(|value| value.message),
                    body: text,
                });
            }
            return Ok(text);
        }
        Err(last_error.unwrap_or_else(|| Error::Other("request retries exhausted".to_string())))
    }

    /// Perform a JSON request and decode the response body.
    pub async fn request_json<T, B>(
        &self,
        method: reqwest::Method,
        path: &str,
        body: Option<&B>,
    ) -> Result<T, Error>
    where
        T: DeserializeOwned,
        B: Serialize + ?Sized,
    {
        let text = self.request_text(method, path, body).await?;
        Ok(serde_json::from_str(&text)?)
    }

    /// Perform a request whose success response has no useful body (204s).
    pub async fn request_empty<B>(
        &self,
        method: reqwest::Method,
        path: &str,
        body: Option<&B>,
    ) -> Result<(), Error>
    where
        B: Serialize + ?Sized,
    {
        self.request_text(method, path, body).await.map(|_| ())
    }

    // ------------------------------------------------------------------ //
    // Users & channels                                                    //
    // ------------------------------------------------------------------ //

    /// `GET /users/@me`
    pub async fn get_current_user(&self) -> Result<User, Error> {
        self.request_json::<User, Value>(reqwest::Method::GET, "/users/@me", None)
            .await
    }

    /// `GET /channels/{channel_id}`
    pub async fn fetch_channel(
        &self,
        channel_id: impl std::fmt::Display,
    ) -> Result<Channel, Error> {
        self.request_json::<Channel, Value>(
            reqwest::Method::GET,
            &format!("/channels/{channel_id}"),
            None,
        )
        .await
    }

    /// `PATCH /channels/{channel_id}`
    pub async fn modify_channel(
        &self,
        channel_id: impl std::fmt::Display,
        payload: &Value,
    ) -> Result<Channel, Error> {
        self.request_json(
            reqwest::Method::PATCH,
            &format!("/channels/{channel_id}"),
            Some(payload),
        )
        .await
    }

    /// `DELETE /channels/{channel_id}`
    pub async fn delete_channel(&self, channel_id: impl std::fmt::Display) -> Result<(), Error> {
        self.request_empty::<Value>(
            reqwest::Method::DELETE,
            &format!("/channels/{channel_id}"),
            None,
        )
        .await
    }

    // ------------------------------------------------------------------ //
    // Messages & reactions                                                //
    // ------------------------------------------------------------------ //

    /// `POST /channels/{channel_id}/messages`
    pub async fn send_message(
        &self,
        channel_id: impl std::fmt::Display,
        message: &MessagePayload,
    ) -> Result<Message, Error> {
        self.request_json(
            reqwest::Method::POST,
            &format!("/channels/{channel_id}/messages"),
            Some(message),
        )
        .await
    }

    /// `GET /channels/{channel_id}/messages/{message_id}`
    pub async fn get_message(
        &self,
        channel_id: impl std::fmt::Display,
        message_id: impl std::fmt::Display,
    ) -> Result<Message, Error> {
        self.request_json::<Message, Value>(
            reqwest::Method::GET,
            &format!("/channels/{channel_id}/messages/{message_id}"),
            None,
        )
        .await
    }

    /// `GET /channels/{channel_id}/messages?limit={limit}`
    pub async fn get_messages(
        &self,
        channel_id: impl std::fmt::Display,
        limit: u8,
    ) -> Result<Vec<Message>, Error> {
        self.request_json::<Vec<Message>, Value>(
            reqwest::Method::GET,
            &format!("/channels/{channel_id}/messages?limit={limit}"),
            None,
        )
        .await
    }

    /// `PATCH /channels/{channel_id}/messages/{message_id}`
    pub async fn edit_message(
        &self,
        channel_id: impl std::fmt::Display,
        message_id: impl std::fmt::Display,
        payload: &MessagePayload,
    ) -> Result<Message, Error> {
        self.request_json(
            reqwest::Method::PATCH,
            &format!("/channels/{channel_id}/messages/{message_id}"),
            Some(payload),
        )
        .await
    }

    /// `DELETE /channels/{channel_id}/messages/{message_id}`
    pub async fn delete_message(
        &self,
        channel_id: impl std::fmt::Display,
        message_id: impl std::fmt::Display,
    ) -> Result<(), Error> {
        self.request_empty::<Value>(
            reqwest::Method::DELETE,
            &format!("/channels/{channel_id}/messages/{message_id}"),
            None,
        )
        .await
    }

    /// `PUT /channels/{c}/messages/{m}/reactions/{emoji}/@me`
    pub async fn create_reaction(
        &self,
        channel_id: impl std::fmt::Display,
        message_id: impl std::fmt::Display,
        emoji: &str,
    ) -> Result<(), Error> {
        let emoji = encode_path_segment(emoji);
        self.request_empty::<Value>(
            reqwest::Method::PUT,
            &format!("/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"),
            None,
        )
        .await
    }

    /// `DELETE /channels/{c}/messages/{m}/reactions/{emoji}/@me`
    pub async fn delete_own_reaction(
        &self,
        channel_id: impl std::fmt::Display,
        message_id: impl std::fmt::Display,
        emoji: &str,
    ) -> Result<(), Error> {
        let emoji = encode_path_segment(emoji);
        self.request_empty::<Value>(
            reqwest::Method::DELETE,
            &format!("/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"),
            None,
        )
        .await
    }

    /// `DELETE /channels/{c}/messages/{m}/reactions/{emoji}/{user_id}`
    pub async fn delete_user_reaction(
        &self,
        channel_id: impl std::fmt::Display,
        message_id: impl std::fmt::Display,
        emoji: &str,
        user_id: impl std::fmt::Display,
    ) -> Result<(), Error> {
        let emoji = encode_path_segment(emoji);
        self.request_empty::<Value>(
            reqwest::Method::DELETE,
            &format!("/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/{user_id}"),
            None,
        )
        .await
    }

    /// `DELETE /channels/{c}/messages/{m}/reactions`
    pub async fn delete_all_reactions(
        &self,
        channel_id: impl std::fmt::Display,
        message_id: impl std::fmt::Display,
    ) -> Result<(), Error> {
        self.request_empty::<Value>(
            reqwest::Method::DELETE,
            &format!("/channels/{channel_id}/messages/{message_id}/reactions"),
            None,
        )
        .await
    }

    // ------------------------------------------------------------------ //
    // Guilds, roles, members                                              //
    // ------------------------------------------------------------------ //

    /// `GET /guilds/{guild_id}`
    pub async fn get_guild(&self, guild_id: impl std::fmt::Display) -> Result<Guild, Error> {
        self.request_json::<Guild, Value>(
            reqwest::Method::GET,
            &format!("/guilds/{guild_id}"),
            None,
        )
        .await
    }

    /// `GET /guilds/{guild_id}/channels`
    pub async fn get_guild_channels(
        &self,
        guild_id: impl std::fmt::Display,
    ) -> Result<Vec<Channel>, Error> {
        self.request_json::<Vec<Channel>, Value>(
            reqwest::Method::GET,
            &format!("/guilds/{guild_id}/channels"),
            None,
        )
        .await
    }

    /// `GET /guilds/{guild_id}/roles`
    pub async fn get_guild_roles(
        &self,
        guild_id: impl std::fmt::Display,
    ) -> Result<Vec<Role>, Error> {
        self.request_json::<Vec<Role>, Value>(
            reqwest::Method::GET,
            &format!("/guilds/{guild_id}/roles"),
            None,
        )
        .await
    }

    /// `POST /guilds/{guild_id}/roles`
    pub async fn create_guild_role(
        &self,
        guild_id: impl std::fmt::Display,
        payload: &Value,
    ) -> Result<Role, Error> {
        self.request_json(
            reqwest::Method::POST,
            &format!("/guilds/{guild_id}/roles"),
            Some(payload),
        )
        .await
    }

    /// `PATCH /guilds/{guild_id}/roles/{role_id}`
    pub async fn modify_guild_role(
        &self,
        guild_id: impl std::fmt::Display,
        role_id: impl std::fmt::Display,
        payload: &Value,
    ) -> Result<Role, Error> {
        self.request_json(
            reqwest::Method::PATCH,
            &format!("/guilds/{guild_id}/roles/{role_id}"),
            Some(payload),
        )
        .await
    }

    /// `DELETE /guilds/{guild_id}/roles/{role_id}`
    pub async fn delete_guild_role(
        &self,
        guild_id: impl std::fmt::Display,
        role_id: impl std::fmt::Display,
    ) -> Result<(), Error> {
        self.request_empty::<Value>(
            reqwest::Method::DELETE,
            &format!("/guilds/{guild_id}/roles/{role_id}"),
            None,
        )
        .await
    }

    /// `GET /guilds/{guild_id}/members/{user_id}`
    pub async fn get_guild_member(
        &self,
        guild_id: impl std::fmt::Display,
        user_id: impl std::fmt::Display,
    ) -> Result<Member, Error> {
        self.request_json::<Member, Value>(
            reqwest::Method::GET,
            &format!("/guilds/{guild_id}/members/{user_id}"),
            None,
        )
        .await
    }

    /// `GET /guilds/{guild_id}/members?limit={limit}`
    pub async fn list_guild_members(
        &self,
        guild_id: impl std::fmt::Display,
        limit: u16,
    ) -> Result<Vec<Member>, Error> {
        self.request_json::<Vec<Member>, Value>(
            reqwest::Method::GET,
            &format!("/guilds/{guild_id}/members?limit={limit}"),
            None,
        )
        .await
    }

    /// `PUT /guilds/{g}/members/{u}/roles/{r}`
    pub async fn add_guild_member_role(
        &self,
        guild_id: impl std::fmt::Display,
        user_id: impl std::fmt::Display,
        role_id: impl std::fmt::Display,
    ) -> Result<(), Error> {
        self.request_empty::<Value>(
            reqwest::Method::PUT,
            &format!("/guilds/{guild_id}/members/{user_id}/roles/{role_id}"),
            None,
        )
        .await
    }

    /// `DELETE /guilds/{g}/members/{u}/roles/{r}`
    pub async fn remove_guild_member_role(
        &self,
        guild_id: impl std::fmt::Display,
        user_id: impl std::fmt::Display,
        role_id: impl std::fmt::Display,
    ) -> Result<(), Error> {
        self.request_empty::<Value>(
            reqwest::Method::DELETE,
            &format!("/guilds/{guild_id}/members/{user_id}/roles/{role_id}"),
            None,
        )
        .await
    }

    /// `DELETE /guilds/{guild_id}/members/{user_id}` (kick)
    pub async fn remove_guild_member(
        &self,
        guild_id: impl std::fmt::Display,
        user_id: impl std::fmt::Display,
    ) -> Result<(), Error> {
        self.request_empty::<Value>(
            reqwest::Method::DELETE,
            &format!("/guilds/{guild_id}/members/{user_id}"),
            None,
        )
        .await
    }

    /// `PUT /guilds/{guild_id}/bans/{user_id}`
    pub async fn create_guild_ban(
        &self,
        guild_id: impl std::fmt::Display,
        user_id: impl std::fmt::Display,
        delete_message_seconds: u32,
    ) -> Result<(), Error> {
        let payload = serde_json::json!({ "delete_message_seconds": delete_message_seconds });
        self.request_empty(
            reqwest::Method::PUT,
            &format!("/guilds/{guild_id}/bans/{user_id}"),
            Some(&payload),
        )
        .await
    }

    /// `DELETE /guilds/{guild_id}/bans/{user_id}`
    pub async fn remove_guild_ban(
        &self,
        guild_id: impl std::fmt::Display,
        user_id: impl std::fmt::Display,
    ) -> Result<(), Error> {
        self.request_empty::<Value>(
            reqwest::Method::DELETE,
            &format!("/guilds/{guild_id}/bans/{user_id}"),
            None,
        )
        .await
    }

    // ------------------------------------------------------------------ //
    // Interactions & webhooks                                             //
    // ------------------------------------------------------------------ //

    /// `POST /interactions/{id}/{token}/callback`
    pub async fn create_interaction_response(
        &self,
        interaction_id: impl std::fmt::Display,
        interaction_token: &str,
        response: &InteractionResponse,
    ) -> Result<(), Error> {
        self.request_empty(
            reqwest::Method::POST,
            &format!("/interactions/{interaction_id}/{interaction_token}/callback"),
            Some(response),
        )
        .await
    }

    /// `GET /webhooks/{application_id}/{token}/messages/@original`
    pub async fn get_original_interaction_response(
        &self,
        application_id: impl std::fmt::Display,
        interaction_token: &str,
    ) -> Result<Message, Error> {
        self.request_json::<Message, Value>(
            reqwest::Method::GET,
            &format!("/webhooks/{application_id}/{interaction_token}/messages/@original"),
            None,
        )
        .await
    }

    /// `PATCH /webhooks/{application_id}/{token}/messages/@original`
    pub async fn edit_original_interaction_response(
        &self,
        application_id: impl std::fmt::Display,
        interaction_token: &str,
        payload: &MessagePayload,
    ) -> Result<Message, Error> {
        self.request_json(
            reqwest::Method::PATCH,
            &format!("/webhooks/{application_id}/{interaction_token}/messages/@original"),
            Some(payload),
        )
        .await
    }

    /// `POST /webhooks/{application_id}/{token}` (interaction followup)
    pub async fn create_followup_message(
        &self,
        application_id: impl std::fmt::Display,
        interaction_token: &str,
        payload: &MessagePayload,
    ) -> Result<Message, Error> {
        self.request_json(
            reqwest::Method::POST,
            &format!("/webhooks/{application_id}/{interaction_token}"),
            Some(payload),
        )
        .await
    }

    /// `POST /webhooks/{webhook_id}/{token}?wait=true`
    pub async fn execute_webhook(
        &self,
        webhook_id: impl std::fmt::Display,
        webhook_token: &str,
        payload: &MessagePayload,
    ) -> Result<Message, Error> {
        self.request_json(
            reqwest::Method::POST,
            &format!("/webhooks/{webhook_id}/{webhook_token}?wait=true"),
            Some(payload),
        )
        .await
    }

    // ------------------------------------------------------------------ //
    // Threads                                                             //
    // ------------------------------------------------------------------ //

    /// `POST /channels/{c}/messages/{m}/threads`
    pub async fn start_thread_from_message(
        &self,
        channel_id: impl std::fmt::Display,
        message_id: impl std::fmt::Display,
        name: &str,
    ) -> Result<Channel, Error> {
        let payload = serde_json::json!({ "name": name });
        self.request_json(
            reqwest::Method::POST,
            &format!("/channels/{channel_id}/messages/{message_id}/threads"),
            Some(&payload),
        )
        .await
    }

    /// `POST /channels/{channel_id}/threads`
    pub async fn start_thread(
        &self,
        channel_id: impl std::fmt::Display,
        name: &str,
        kind: u8,
    ) -> Result<Channel, Error> {
        let payload = serde_json::json!({ "name": name, "type": kind });
        self.request_json(
            reqwest::Method::POST,
            &format!("/channels/{channel_id}/threads"),
            Some(&payload),
        )
        .await
    }

    /// `PUT /channels/{channel_id}/thread-members/@me`
    pub async fn join_thread(&self, channel_id: impl std::fmt::Display) -> Result<(), Error> {
        self.request_empty::<Value>(
            reqwest::Method::PUT,
            &format!("/channels/{channel_id}/thread-members/@me"),
            None,
        )
        .await
    }

    /// `DELETE /channels/{channel_id}/thread-members/@me`
    pub async fn leave_thread(&self, channel_id: impl std::fmt::Display) -> Result<(), Error> {
        self.request_empty::<Value>(
            reqwest::Method::DELETE,
            &format!("/channels/{channel_id}/thread-members/@me"),
            None,
        )
        .await
    }

    // ------------------------------------------------------------------ //
    // Application commands                                                //
    // ------------------------------------------------------------------ //

    /// `GET /applications/{application_id}/commands`
    pub async fn list_global_commands(
        &self,
        application_id: impl std::fmt::Display,
    ) -> Result<Vec<Value>, Error> {
        self.request_json::<Vec<Value>, Value>(
            reqwest::Method::GET,
            &format!("/applications/{application_id}/commands"),
            None,
        )
        .await
    }

    /// `PUT /applications/{application_id}/commands`
    pub async fn bulk_overwrite_global_commands(
        &self,
        application_id: impl std::fmt::Display,
        commands: &[Value],
    ) -> Result<Vec<Value>, Error> {
        self.request_json(
            reqwest::Method::PUT,
            &format!("/applications/{application_id}/commands"),
            Some(commands),
        )
        .await
    }

    /// `GET /applications/{application_id}/guilds/{guild_id}/commands`
    pub async fn list_guild_commands(
        &self,
        application_id: impl std::fmt::Display,
        guild_id: impl std::fmt::Display,
    ) -> Result<Vec<Value>, Error> {
        self.request_json::<Vec<Value>, Value>(
            reqwest::Method::GET,
            &format!("/applications/{application_id}/guilds/{guild_id}/commands"),
            None,
        )
        .await
    }

    /// `PUT /applications/{application_id}/guilds/{guild_id}/commands`
    pub async fn bulk_overwrite_guild_commands(
        &self,
        application_id: impl std::fmt::Display,
        guild_id: impl std::fmt::Display,
        commands: &[Value],
    ) -> Result<Vec<Value>, Error> {
        self.request_json(
            reqwest::Method::PUT,
            &format!("/applications/{application_id}/guilds/{guild_id}/commands"),
            Some(commands),
        )
        .await
    }
}

/// Percent-encode a path segment (used for reaction emoji).
fn encode_path_segment(segment: &str) -> String {
    let mut out = String::with_capacity(segment.len() * 3);
    for byte in segment.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' | b':' => {
                out.push(byte as char);
            }
            _ => {
                out.push('%');
                out.push_str(&format!("{byte:02X}"));
            }
        }
    }
    out
}

fn build_http_client(config: &Config) -> reqwest::Client {
    let mut builder = reqwest::Client::builder();
    if let Some(proxy_url) = &config.proxy_url
        && let Ok(proxy) = reqwest::Proxy::all(proxy_url)
    {
        builder = builder.proxy(proxy);
    }
    builder.build().unwrap_or_else(|_| reqwest::Client::new())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn client_builds_discord_request_parts() {
        let client = Client::new(Config::new("token"));

        let request = client.request_parts("GET", "/users/@me", false);

        assert_eq!(request.method, "GET");
        assert_eq!(request.url, "https://discord.com/api/v10/users/@me");
        assert_eq!(request.authorization, "Bot token");
        assert_eq!(request.content_type, None);
        assert!(request.user_agent.contains("vaidcord-rust/"));
    }

    #[test]
    fn post_request_parts_include_json_content_type() {
        let client = Client::new(Config::new("token"));

        let request = client.request_parts("POST", "/channels/1/messages", true);

        assert_eq!(request.content_type.as_deref(), Some("application/json"));
    }

    #[test]
    fn config_accepts_proxy_url() {
        let config = Config::new("token").with_proxy_url("http://127.0.0.1:8080");

        assert_eq!(config.proxy_url.as_deref(), Some("http://127.0.0.1:8080"));
    }

    #[test]
    fn global_commands_endpoint_is_built_correctly() {
        let client = Client::new(Config::new("token"));
        assert_eq!(
            client.endpoint("/applications/42/commands"),
            "https://discord.com/api/v10/applications/42/commands"
        );
    }

    #[test]
    fn guild_commands_endpoint_is_built_correctly() {
        let client = Client::new(Config::new("token"));
        assert_eq!(
            client.endpoint("/applications/42/guilds/777/commands"),
            "https://discord.com/api/v10/applications/42/guilds/777/commands"
        );
    }

    #[test]
    fn emoji_path_segments_are_percent_encoded() {
        assert_eq!(encode_path_segment("👍"), "%F0%9F%91%8D");
        assert_eq!(
            encode_path_segment("custom_emoji:123456789012345678"),
            "custom_emoji:123456789012345678"
        );
    }
}
