use crate::error::Error;
use crate::models::Message;

pub type HandlerResult = Result<(), Error>;
pub type MessageHandler = Box<dyn Fn(&Message) -> HandlerResult + Send + Sync>;
pub type MessageFilter = Box<dyn Fn(&Message) -> bool + Send + Sync>;

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
            handler: Box::new(handler),
        });
    }

    pub fn dispatch_message(&self, message: &Message) -> HandlerResult {
        for route in &self.message_routes {
            if !route.filters.iter().all(|filter| filter(message)) {
                continue;
            }
            (route.handler)(message)?;
        }
        Ok(())
    }
}

impl Default for Router {
    fn default() -> Self {
        Self::new()
    }
}

pub fn content_starts_with(prefix: impl Into<String>) -> MessageFilter {
    let prefix = prefix.into();
    Box::new(move |message: &Message| message.content.starts_with(&prefix))
}

pub fn author_id(user_id: impl Into<String>) -> MessageFilter {
    let user_id = user_id.into();
    Box::new(move |message: &Message| message.author.id == user_id)
}

#[macro_export]
macro_rules! on_message {
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

        on_message!(
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
}
