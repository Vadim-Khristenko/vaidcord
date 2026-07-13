//! High-level bot runner: gateway dispatch -> parsed models -> dispatcher.
//!
//! ```no_run
//! use vaidcord::{Bot, HandlerResult, Intents, Message, Router};
//!
//! #[tokio::main]
//! async fn main() -> Result<(), vaidcord::Error> {
//!     let mut router = Router::new();
//!     router.on_message(|message: &Message| -> HandlerResult {
//!         println!("{}: {}", message.author.username, message.content);
//!         Ok(())
//!     });
//!
//!     Bot::builder()
//!         .token(std::env::var("DISCORD_TOKEN").unwrap())
//!         .intents(Intents::GUILDS | Intents::GUILD_MESSAGES | Intents::MESSAGE_CONTENT)
//!         .router(router)
//!         .run()
//!         .await
//! }
//! ```

use std::sync::Arc;

use crate::client::Client;
use crate::config::Config;
use crate::dispatcher::Dispatcher;
use crate::error::Error;
use crate::events::Event;
use crate::gateway::{GatewayClient, GatewayCloseAction, GatewayEvent, GatewayHandle, Intents};
use crate::router::{HandlerResult, Router};

type ErrorHook = Arc<dyn Fn(&Error) + Send + Sync>;

/// Builder for [`Bot`]. Construct via [`Bot::builder`].
pub struct BotBuilder {
    token: Option<String>,
    config: Option<Config>,
    intents: Intents,
    routers: Vec<Router>,
    on_error: ErrorHook,
}

impl BotBuilder {
    fn new() -> Self {
        Self {
            token: None,
            config: None,
            intents: Intents::none(),
            routers: Vec::new(),
            on_error: Arc::new(|error| eprintln!("vaidcord handler error: {error}")),
        }
    }

    /// Set the bot token (required unless a full [`Config`] is provided).
    pub fn token(mut self, token: impl Into<String>) -> Self {
        self.token = Some(token.into());
        self
    }

    /// Provide a full REST/gateway [`Config`] (overrides [`Self::token`]).
    pub fn config(mut self, config: Config) -> Self {
        self.config = Some(config);
        self
    }

    /// Set the gateway intents sent in IDENTIFY.
    pub fn intents(mut self, intents: Intents) -> Self {
        self.intents = intents;
        self
    }

    /// Attach a router (may be called multiple times; routers dispatch in
    /// the order attached).
    pub fn router(mut self, router: Router) -> Self {
        self.routers.push(router);
        self
    }

    /// Replace the default handler-error hook (default: log to stderr).
    pub fn on_error<F>(mut self, hook: F) -> Self
    where
        F: Fn(&Error) + Send + Sync + 'static,
    {
        self.on_error = Arc::new(hook);
        self
    }

    /// Build the bot (validates that a token/config was provided).
    pub fn build(self) -> Result<Bot, Error> {
        let config = match (self.config, self.token) {
            (Some(config), _) => config,
            (None, Some(token)) => Config::new(token),
            (None, None) => {
                return Err(Error::Other(
                    "Bot::builder() requires .token(..) or .config(..)".to_string(),
                ));
            }
        };
        let mut dispatcher = Dispatcher::new();
        for router in &self.routers {
            dispatcher.include(router);
        }
        Ok(Bot {
            client: Client::new(config),
            dispatcher,
            intents: self.intents,
            on_error: self.on_error,
        })
    }

    /// Build and run until the gateway shuts down fatally.
    pub async fn run(self) -> Result<(), Error> {
        self.build()?.run().await
    }
}

/// High-level facade owning the REST client, gateway connection and the
/// dispatcher (UNITED.md §1 layer 2).
pub struct Bot {
    client: Client,
    dispatcher: Dispatcher,
    intents: Intents,
    on_error: ErrorHook,
}

impl Bot {
    /// Start building a bot.
    pub fn builder() -> BotBuilder {
        BotBuilder::new()
    }

    /// The REST client (rate-limited, retrying).
    pub fn client(&self) -> &Client {
        &self.client
    }

    /// The composed dispatcher.
    pub fn dispatcher(&self) -> &Dispatcher {
        &self.dispatcher
    }

    /// Feed one already-parsed event through the dispatcher (useful for
    /// tests and mock servers).
    pub fn feed_event(&self, event: &Event) -> HandlerResult {
        self.dispatcher.dispatch(event)
    }

    /// Connect to the gateway and dispatch events until the connection ends
    /// fatally (bad token/intents) or is shut down via [`GatewayHandle`].
    ///
    /// Handler errors do not stop the loop; they are routed to the
    /// [`BotBuilder::on_error`] hook.
    pub async fn run(self) -> Result<(), Error> {
        let gateway = GatewayClient::new(self.client.clone());
        let mut connection = gateway.connect(self.intents).await?;
        while let Some(event) = connection.next_event().await {
            match event {
                GatewayEvent::Dispatch(dispatch) => {
                    let Some(name) = dispatch.t.as_deref() else {
                        continue;
                    };
                    let parsed = Event::parse(name, dispatch.d);
                    if let Err(error) = self.dispatcher.dispatch(&parsed) {
                        (self.on_error)(&error);
                    }
                }
                GatewayEvent::Disconnected {
                    close_code,
                    action: GatewayCloseAction::Fatal,
                } => {
                    return Err(Error::Other(format!(
                        "gateway closed fatally (close code {close_code:?})"
                    )));
                }
                GatewayEvent::Error(error) => (self.on_error)(&error),
                _ => {}
            }
        }
        Ok(())
    }

    /// Connect to the gateway and return a handle plus a background dispatch
    /// task, for programs that need to keep control of the main task.
    pub async fn spawn(self) -> Result<(GatewayHandle, tokio::task::JoinHandle<Result<(), Error>>), Error>
    {
        let gateway = GatewayClient::new(self.client.clone());
        let connection = gateway.connect(self.intents).await?;
        let handle = connection.handle();
        let mut connection = connection;
        let dispatcher = self.dispatcher;
        let on_error = self.on_error;
        let task = tokio::spawn(async move {
            while let Some(event) = connection.next_event().await {
                match event {
                    GatewayEvent::Dispatch(dispatch) => {
                        let Some(name) = dispatch.t.as_deref() else {
                            continue;
                        };
                        let parsed = Event::parse(name, dispatch.d);
                        if let Err(error) = dispatcher.dispatch(&parsed) {
                            (on_error)(&error);
                        }
                    }
                    GatewayEvent::Disconnected {
                        close_code,
                        action: GatewayCloseAction::Fatal,
                    } => {
                        return Err(Error::Other(format!(
                            "gateway closed fatally (close code {close_code:?})"
                        )));
                    }
                    GatewayEvent::Error(error) => (on_error)(&error),
                    _ => {}
                }
            }
            Ok(())
        });
        Ok((handle, task))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    #[test]
    fn builder_requires_a_token() {
        assert!(Bot::builder().build().is_err());
        assert!(Bot::builder().token("t").build().is_ok());
        assert!(Bot::builder().config(Config::new("t")).build().is_ok());
    }

    #[test]
    fn builder_composes_routers_into_the_dispatcher() {
        let mut router_a = Router::new();
        router_a.on_message(|_| Ok(()));
        let mut router_b = Router::new();
        router_b.on_message(|_| Ok(()));
        router_b.on_ready(|_| Ok(()));

        let bot = Bot::builder()
            .token("t")
            .router(router_a)
            .router(router_b)
            .build()
            .unwrap();
        assert_eq!(bot.dispatcher().route_count(), 3);
    }

    #[test]
    fn feed_event_dispatches_parsed_gateway_payloads() {
        let seen: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let mut router = Router::new();
        let sink = Arc::clone(&seen);
        router.on_message(move |message| {
            sink.lock().unwrap().push(message.content.clone());
            Ok(())
        });

        let bot = Bot::builder().token("t").router(router).build().unwrap();
        let event = Event::parse(
            "MESSAGE_CREATE",
            serde_json::json!({
                "id": "1", "channel_id": "2", "content": "hello",
                "author": {"id": "3", "username": "u"}
            }),
        );
        bot.feed_event(&event).unwrap();
        assert_eq!(*seen.lock().unwrap(), vec!["hello"]);
    }
}
