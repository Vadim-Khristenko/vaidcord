use serde::Deserialize;

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct DiscordApiErrorBody {
    pub code: Option<i64>,
    pub message: Option<String>,
}

#[derive(Debug)]
pub enum Error {
    Http(reqwest::Error),
    Decode(serde_json::Error),
    MissingExtractor(&'static str),
    Api {
        status: reqwest::StatusCode,
        code: Option<i64>,
        message: Option<String>,
        body: String,
    },
}

impl std::fmt::Display for Error {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Http(error) => write!(formatter, "{error}"),
            Self::Decode(error) => write!(formatter, "{error}"),
            Self::MissingExtractor(name) => write!(formatter, "missing handler extractor: {name}"),
            Self::Api {
                status,
                code,
                message,
                body,
            } => write!(
                formatter,
                "discord api returned status {status} code {code:?}: {}",
                message.as_deref().unwrap_or(body)
            ),
        }
    }
}

impl std::error::Error for Error {}

impl From<reqwest::Error> for Error {
    fn from(error: reqwest::Error) -> Self {
        Self::Http(error)
    }
}

impl From<serde_json::Error> for Error {
    fn from(error: serde_json::Error) -> Self {
        Self::Decode(error)
    }
}
