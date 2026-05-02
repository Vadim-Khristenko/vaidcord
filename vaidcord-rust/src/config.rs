#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    pub token: String,
    pub api_version: String,
    pub base_url: String,
    pub proxy_url: Option<String>,
}

impl Config {
    pub fn new(token: impl Into<String>) -> Self {
        Self {
            token: token.into(),
            api_version: "10".to_string(),
            base_url: "https://discord.com/api".to_string(),
            proxy_url: None,
        }
    }

    pub fn with_proxy_url(mut self, proxy_url: impl Into<String>) -> Self {
        self.proxy_url = Some(proxy_url.into());
        self
    }
}
