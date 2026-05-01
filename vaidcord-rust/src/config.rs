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
