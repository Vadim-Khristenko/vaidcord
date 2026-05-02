use serde::{Serialize, de::DeserializeOwned};

use crate::USER_AGENT;
use crate::config::Config;
use crate::error::{DiscordApiErrorBody, Error};
use crate::models::{Channel, Message, MessagePayload, User};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RequestParts {
    pub method: String,
    pub url: String,
    pub authorization: String,
    pub user_agent: String,
    pub content_type: Option<String>,
}

#[derive(Debug, Clone)]
pub struct Client {
    config: Config,
    http: reqwest::Client,
}

impl Client {
    pub fn new(config: Config) -> Self {
        Self {
            config,
            http: reqwest::Client::new(),
        }
    }

    pub fn with_http_client(config: Config, http: reqwest::Client) -> Self {
        Self { config, http }
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
        let mut request = self.request_builder(method, path);
        if let Some(body) = body {
            request = request.json(body);
        }
        let response = request.send().await?;
        let status = response.status();
        let text = response.text().await?;
        if !status.is_success() {
            let decoded = serde_json::from_str::<DiscordApiErrorBody>(&text).ok();
            return Err(Error::Api {
                status,
                code: decoded.as_ref().and_then(|value| value.code),
                message: decoded.and_then(|value| value.message),
                body: text,
            });
        }
        Ok(serde_json::from_str(&text)?)
    }

    pub async fn get_current_user(&self) -> Result<User, Error> {
        self.request_json::<User, MessagePayload>(reqwest::Method::GET, "/users/@me", None)
            .await
    }

    pub async fn fetch_channel(
        &self,
        channel_id: impl std::fmt::Display,
    ) -> Result<Channel, Error> {
        self.request_json::<Channel, MessagePayload>(
            reqwest::Method::GET,
            &format!("/channels/{channel_id}"),
            None,
        )
        .await
    }

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
}
