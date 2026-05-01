pub const LIBRARY_NAME: &str = "vaidcord-rust";
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
pub const USER_AGENT: &str = concat!(
    "DiscordBot (https://github.com/Vadim-Khristenko/vaidcord, ",
    env!("CARGO_PKG_VERSION"),
    ") vaidcord-rust/",
    env!("CARGO_PKG_VERSION")
);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    pub token: String,
    pub api_version: String,
    pub base_url: String,
}

impl Config {
    pub fn new(token: impl Into<String>) -> Self {
        Self {
            token: token.into(),
            api_version: "10".to_string(),
            base_url: "https://discord.com/api".to_string(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RequestParts {
    pub method: String,
    pub url: String,
    pub authorization: String,
    pub user_agent: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Client {
    config: Config,
}

impl Client {
    pub fn new(config: Config) -> Self {
        Self { config }
    }

    pub fn endpoint(&self, path: &str) -> String {
        format!(
            "{}/v{}/{}",
            self.config.base_url.trim_end_matches('/'),
            self.config.api_version,
            path.trim_start_matches('/')
        )
    }

    pub fn request_parts(&self, method: impl Into<String>, path: &str) -> RequestParts {
        RequestParts {
            method: method.into(),
            url: self.endpoint(path),
            authorization: format!("Bot {}", self.config.token),
            user_agent: USER_AGENT.to_string(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn client_builds_discord_request_parts() {
        let client = Client::new(Config::new("token"));

        let request = client.request_parts("GET", "/users/@me");

        assert_eq!(request.method, "GET");
        assert_eq!(request.url, "https://discord.com/api/v10/users/@me");
        assert_eq!(request.authorization, "Bot token");
        assert!(request.user_agent.contains("vaidcord-rust/"));
    }
}
