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
        // Reuse a single empty bag for unfiltered handlers to avoid the
        // per-route HashMap allocation that ExtractBag::new() incurs. Routes
        // that *do* have filters still get a private bag because filters can
        // contribute extracted values via FilterOutcome::Pass.
        let empty_bag = ExtractBag::new();
        for route in &self.message_routes {
            if route.filters.is_empty() {
                (route.handler)(message, &empty_bag)?;
                continue;
            }
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

/// Register a handler with the router using a fluent multi-filter syntax.
///
/// Three forms are supported. The multi-filter form is the recommended
/// mainstream pattern; the macro-attribute equivalent is `#[on_message(...)]`.
///
/// ```ignore
/// use vaidcord::{command, content_starts_with, register_on_message, Router};
///
/// let mut router = Router::new();
///
/// // No filters — runs for every message.
/// register_on_message!(router, |_| Ok(()));
///
/// // Multiple filters AND'd together (mainstream style).
/// register_on_message!(
///     router,
///     |_| Ok(()),
///     filters = [content_starts_with("!"), command("ping")]
/// );
///
/// // OR composition: any of these may match.
/// register_on_message!(
///     router,
///     |_| Ok(()),
///     any = [command("ping"), command("pong")]
/// );
/// ```
#[macro_export]
macro_rules! register_on_message {
    ($router:expr, $handler:expr) => {
        $router.on_message($handler)
    };
    ($router:expr, $handler:expr, filters = [$($filter:expr),* $(,)?]) => {
        $router.on_message_filtered($handler, vec![$($filter),*])
    };
    ($router:expr, $handler:expr, any = [$($filter:expr),+ $(,)?]) => {{
        let mut __any: ::std::vec::Vec<$crate::MessageFilter> = vec![$($filter),+];
        let mut __iter = __any.drain(..);
        let mut __acc = __iter.next().expect("`any` requires at least one filter");
        for __f in __iter {
            __acc = $crate::or(__acc, __f);
        }
        $router.on_message_filtered($handler, vec![__acc])
    }};
    (
        $router:expr,
        $handler:expr,
        filters = [$($filter:expr),* $(,)?],
        any = [$($any_filter:expr),+ $(,)?]
    ) => {{
        let mut __any: ::std::vec::Vec<$crate::MessageFilter> = vec![$($any_filter),+];
        let mut __iter = __any.drain(..);
        let mut __acc = __iter.next().expect("`any` requires at least one filter");
        for __f in __iter {
            __acc = $crate::or(__acc, __f);
        }
        let mut __all: ::std::vec::Vec<$crate::MessageFilter> = vec![$($filter),*];
        __all.push(__acc);
        $router.on_message_filtered($handler, __all)
    }};
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
    fn router_runs_handler_only_when_all_filters_pass() {
        let mut router = Router::new();
        let calls = Arc::new(AtomicUsize::new(0));
        let handler_calls = Arc::clone(&calls);

        register_on_message!(
            router,
            move |_message: &Message| {
                handler_calls.fetch_add(1, Ordering::SeqCst);
                Ok(())
            },
            filters = [
                content_starts_with("!"),
                crate::command("ping")
            ]
        );

        router.dispatch_message(&message("hello")).unwrap();   // neither
        router.dispatch_message(&message("!hello")).unwrap();  // first only
        router.dispatch_message(&message("/ping")).unwrap();   // second only
        router.dispatch_message(&message("!ping")).unwrap();   // both
        assert_eq!(calls.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn router_any_macro_matches_when_either_filter_passes() {
        let mut router = Router::new();
        let calls = Arc::new(AtomicUsize::new(0));
        let handler_calls = Arc::clone(&calls);

        register_on_message!(
            router,
            move |_message: &Message| {
                handler_calls.fetch_add(1, Ordering::SeqCst);
                Ok(())
            },
            any = [crate::command("ping"), crate::command("pong")]
        );

        router.dispatch_message(&message("/ping")).unwrap();
        router.dispatch_message(&message("/pong")).unwrap();
        router.dispatch_message(&message("/foo")).unwrap();
        assert_eq!(calls.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn router_combines_filters_and_any_branches() {
        let mut router = Router::new();
        let calls = Arc::new(AtomicUsize::new(0));
        let handler_calls = Arc::clone(&calls);

        register_on_message!(
            router,
            move |_message: &Message| {
                handler_calls.fetch_add(1, Ordering::SeqCst);
                Ok(())
            },
            filters = [content_starts_with("/")],
            any = [crate::command("ping"), crate::command("pong")]
        );

        router.dispatch_message(&message("/ping")).unwrap();   // both
        router.dispatch_message(&message("!ping")).unwrap();   // any only
        router.dispatch_message(&message("/foo")).unwrap();    // filters only
        assert_eq!(calls.load(Ordering::SeqCst), 1);
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
