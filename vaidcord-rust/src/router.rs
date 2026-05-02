use crate::error::Error;
use crate::extract::ExtractBag;
use crate::filters::{FilterOutcome, MessageFilter};
use crate::models::Message;

pub type HandlerResult = Result<(), Error>;
pub type MessageHandler = Box<dyn Fn(&Message, &ExtractBag) -> HandlerResult + Send + Sync>;

pub struct MessageHandlerDef {
    name: &'static str,
    filters: Vec<MessageFilter>,
    handler: MessageHandler,
}

impl MessageHandlerDef {
    pub fn new<F>(name: &'static str, handler: F, filters: Vec<MessageFilter>) -> Self
    where
        F: Fn(&Message) -> HandlerResult + Send + Sync + 'static,
    {
        Self {
            name,
            filters,
            handler: Box::new(move |message, _bag| handler(message)),
        }
    }

    pub fn name(&self) -> &'static str {
        self.name
    }
}

pub struct Router {
    message_routes: Vec<MessageRoute>,
}

struct MessageRoute {
    filters: Vec<MessageFilter>,
    handler: MessageHandler,
}

impl Router {
    pub fn new() -> Self {
        Self {
            message_routes: Vec::new(),
        }
    }

    pub fn on_message<F>(&mut self, handler: F)
    where
        F: Fn(&Message) -> HandlerResult + Send + Sync + 'static,
    {
        self.on_message_filtered(handler, Vec::new());
    }

    pub fn on_message_filtered<F>(&mut self, handler: F, filters: Vec<MessageFilter>)
    where
        F: Fn(&Message) -> HandlerResult + Send + Sync + 'static,
    {
        self.message_routes.push(MessageRoute {
            filters,
            handler: Box::new(move |message, _bag| handler(message)),
        });
    }

    pub fn add_message_handler(&mut self, definition: MessageHandlerDef) {
        self.message_routes.push(MessageRoute {
            filters: definition.filters,
            handler: definition.handler,
        });
    }

    pub fn dispatch_message(&self, message: &Message) -> HandlerResult {
        for route in &self.message_routes {
            let mut bag = ExtractBag::new();
            let mut rejected = false;
            for filter in &route.filters {
                match filter(message, &bag)? {
                    FilterOutcome::Pass(extracted) => bag.merge(extracted),
                    FilterOutcome::Reject => {
                        rejected = true;
                        break;
                    }
                }
            }
            if !rejected {
                (route.handler)(message, &bag)?;
            }
        }
        Ok(())
    }
}

impl Default for Router {
    fn default() -> Self {
        Self::new()
    }
}

pub use crate::filters::{author_id, content_starts_with};

#[macro_export]
macro_rules! register_on_message {
    ($router:expr, $handler:expr) => {
        $router.on_message($handler)
    };
    ($router:expr, $handler:expr, filters = [$($filter:expr),* $(,)?]) => {
        $router.on_message_filtered($handler, vec![$($filter),*])
    };
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::User;
    use std::sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    };

    fn message(content: &str) -> Message {
        Message {
            id: "1".to_string(),
            channel_id: "2".to_string(),
            guild_id: None,
            author: User {
                id: "42".to_string(),
                username: "tester".to_string(),
                discriminator: None,
                global_name: None,
                bot: false,
                system: false,
                avatar: None,
                banner: None,
                public_flags: None,
            },
            content: content.to_string(),
            timestamp: None,
            edited_timestamp: None,
            tts: false,
            mention_everyone: false,
            mentions: Vec::new(),
            embeds: Vec::new(),
            attachments: Vec::new(),
            components: Vec::new(),
            flags: None,
        }
    }

    #[test]
    fn router_dispatches_filtered_messages() {
        let mut router = Router::new();
        let calls = Arc::new(AtomicUsize::new(0));
        let handler_calls = Arc::clone(&calls);

        register_on_message!(
            router,
            move |message: &Message| {
                handler_calls.fetch_add(1, Ordering::SeqCst);
                assert_eq!(message.content, "!ping");
                Ok(())
            },
            filters = [content_starts_with("!")]
        );

        router.dispatch_message(&message("plain")).unwrap();
        router.dispatch_message(&message("!ping")).unwrap();
        assert_eq!(calls.load(Ordering::SeqCst), 1);
    }

    fn ping(message: &Message) -> HandlerResult {
        assert_eq!(message.content, "!ping");
        Ok(())
    }

    #[test]
    fn router_accepts_handler_definitions() {
        let mut router = Router::new();
        let definition = MessageHandlerDef::new("ping", ping, vec![content_starts_with("!")]);

        assert_eq!(definition.name(), "ping");
        router.add_message_handler(definition);

        router.dispatch_message(&message("plain")).unwrap();
        router.dispatch_message(&message("!ping")).unwrap();
    }

    #[test]
    fn command_filter_extracts_args_for_handler() {
        let mut router = Router::new();
        let calls = Arc::new(AtomicUsize::new(0));
        let handler_calls = Arc::clone(&calls);

        router.on_message_filtered(
            move |_message: &Message| {
                handler_calls.fetch_add(1, Ordering::SeqCst);
                Ok(())
            },
            vec![crate::command("echo")],
        );

        router.dispatch_message(&message("plain")).unwrap();
        router.dispatch_message(&message("!echo hello")).unwrap();
        assert_eq!(calls.load(Ordering::SeqCst), 1);
    }
}
