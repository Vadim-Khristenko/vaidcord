//! Handler registry with filters, middleware and nesting.
//!
//! A [`Router`] owns routes (handler + filters), router-level middleware and
//! child routers. Routers are composed into a [`Dispatcher`](crate::Dispatcher)
//! which precomputes each route's middleware chain at include-time so the
//! dispatch hot path is O(1) in allocations (UNITED.md §7).

use std::sync::Arc;

use crate::error::Error;
use crate::events::{Event, EventKind};
use crate::extract::ExtractBag;
use crate::filters::{FilterOutcome, MessageFilter};
use crate::middleware::Middleware;
use crate::models::{Interaction, Message, Ready};

/// Result type returned by every handler and middleware.
pub type HandlerResult = Result<(), Error>;

/// Boxed message handler used by [`MessageHandlerDef`].
pub type MessageHandler = Box<dyn Fn(&Message, &ExtractBag) -> HandlerResult + Send + Sync>;

pub(crate) type SharedMessageFilter =
    Arc<dyn Fn(&Message, &ExtractBag) -> Result<FilterOutcome, Error> + Send + Sync>;
pub(crate) type SharedEventHandler =
    Arc<dyn Fn(&Event, &ExtractBag) -> HandlerResult + Send + Sync>;
type SharedMessageHandler = Arc<dyn Fn(&Message, &ExtractBag) -> HandlerResult + Send + Sync>;

/// A named message-handler definition, typically produced by the
/// `#[vaidcord::on_message]` proc-macro.
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

/// One registered route: event kind + filters + handler.
pub(crate) struct Route {
    pub(crate) kind: EventKind,
    pub(crate) filters: Vec<SharedMessageFilter>,
    pub(crate) handler: SharedEventHandler,
}

/// A route flattened out of a router tree together with the middleware chain
/// (outermost first) that must wrap its handler.
pub(crate) struct CollectedRoute {
    pub(crate) kind: EventKind,
    pub(crate) filters: Vec<SharedMessageFilter>,
    pub(crate) middlewares: Vec<Middleware>,
    pub(crate) handler: SharedEventHandler,
}

/// Handler registry + filter pipeline with middleware and nesting.
#[derive(Default)]
pub struct Router {
    name: &'static str,
    routes: Vec<Route>,
    children: Vec<Router>,
    middlewares: Vec<Middleware>,
}

impl Router {
    /// Create an empty router.
    pub fn new() -> Self {
        Self::default()
    }

    /// Create an empty router with a diagnostic name.
    pub fn named(name: &'static str) -> Self {
        Self {
            name,
            ..Self::default()
        }
    }

    /// The router's diagnostic name (empty if unnamed).
    pub fn name(&self) -> &'static str {
        self.name
    }

    /// Attach a middleware to this router.
    ///
    /// The middleware wraps every route registered on this router *and* on
    /// any router later nested via [`Router::include`]. Middleware added on a
    /// parent runs outside middleware added on a child; the innermost
    /// middleware wraps the handler itself.
    pub fn use_middleware<F>(&mut self, middleware: F)
    where
        F: for<'a> Fn(&Event, &ExtractBag, crate::middleware::Next<'a>) -> HandlerResult
            + Send
            + Sync
            + 'static,
    {
        self.middlewares.push(Arc::new(middleware));
    }

    /// Nest a child router. The child keeps its own filters and middleware;
    /// this router's middleware wraps around them.
    pub fn include(&mut self, child: Router) {
        self.children.push(child);
    }

    /// Register a handler for every `MESSAGE_CREATE` event.
    pub fn on_message<F>(&mut self, handler: F)
    where
        F: Fn(&Message) -> HandlerResult + Send + Sync + 'static,
    {
        self.on_message_filtered(handler, Vec::new());
    }

    /// Register a `MESSAGE_CREATE` handler guarded by filters (AND'd).
    pub fn on_message_filtered<F>(&mut self, handler: F, filters: Vec<MessageFilter>)
    where
        F: Fn(&Message) -> HandlerResult + Send + Sync + 'static,
    {
        self.push_message_route(
            filters,
            Box::new(move |message, _bag| handler(message)),
        );
    }

    /// Register a handler definition produced by `#[vaidcord::on_message]`.
    pub fn add_message_handler(&mut self, definition: MessageHandlerDef) {
        self.push_message_route(definition.filters, definition.handler);
    }

    fn push_message_route(&mut self, filters: Vec<MessageFilter>, handler: MessageHandler) {
        let handler: SharedMessageHandler = Arc::from(handler);
        self.routes.push(Route {
            kind: EventKind::MessageCreate,
            filters: filters.into_iter().map(SharedMessageFilter::from).collect(),
            handler: Arc::new(move |event: &Event, bag: &ExtractBag| match event.message() {
                Some(message) => handler(message, bag),
                None => Ok(()),
            }),
        });
    }

    /// Register a handler for an arbitrary event kind.
    pub fn on_event<F>(&mut self, kind: EventKind, handler: F)
    where
        F: Fn(&Event) -> HandlerResult + Send + Sync + 'static,
    {
        self.routes.push(Route {
            kind,
            filters: Vec::new(),
            handler: Arc::new(move |event: &Event, _bag: &ExtractBag| handler(event)),
        });
    }

    /// Register a handler for the gateway `READY` event.
    pub fn on_ready<F>(&mut self, handler: F)
    where
        F: Fn(&Ready) -> HandlerResult + Send + Sync + 'static,
    {
        self.on_event(EventKind::Ready, move |event| match event {
            Event::Ready(ready) => handler(ready),
            _ => Ok(()),
        });
    }

    /// Register a handler for `INTERACTION_CREATE` events.
    pub fn on_interaction<F>(&mut self, handler: F)
    where
        F: Fn(&Interaction) -> HandlerResult + Send + Sync + 'static,
    {
        self.on_event(EventKind::InteractionCreate, move |event| match event {
            Event::InteractionCreate(interaction) => handler(interaction.as_ref()),
            _ => Ok(()),
        });
    }

    /// Flatten this router tree into routes carrying their full middleware
    /// chain (`parent` middleware outermost, then this router's, then any
    /// child's). Shared handlers/filters are reference-counted so the router
    /// remains usable afterwards.
    pub(crate) fn collect_routes(&self, parent: &[Middleware]) -> Vec<CollectedRoute> {
        let chain: Vec<Middleware> = parent
            .iter()
            .cloned()
            .chain(self.middlewares.iter().cloned())
            .collect();
        let mut out = Vec::with_capacity(self.routes.len());
        for route in &self.routes {
            out.push(CollectedRoute {
                kind: route.kind,
                filters: route.filters.clone(),
                middlewares: chain.clone(),
                handler: Arc::clone(&route.handler),
            });
        }
        for child in &self.children {
            out.extend(child.collect_routes(&chain));
        }
        out
    }

    /// Dispatch a message through this router tree (filters + middleware).
    ///
    /// Convenience wrapper that builds a one-shot [`Dispatcher`]; for the hot
    /// path build a `Dispatcher` once and reuse it so middleware chains stay
    /// precomposed.
    ///
    /// [`Dispatcher`]: crate::Dispatcher
    pub fn dispatch_message(&self, message: &Message) -> HandlerResult {
        let mut dispatcher = crate::dispatcher::Dispatcher::new();
        dispatcher.include(self);
        dispatcher.dispatch(&Event::MessageCreate(message.clone()))
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

    #[test]
    fn nested_router_middleware_wraps_child_routes() {
        let log: Arc<std::sync::Mutex<Vec<String>>> = Arc::new(std::sync::Mutex::new(Vec::new()));

        let mut child = Router::named("child");
        let child_log = Arc::clone(&log);
        child.use_middleware(move |event, bag, next| {
            child_log.lock().unwrap().push("child:in".into());
            let result = next.run(event, bag);
            child_log.lock().unwrap().push("child:out".into());
            result
        });
        let handler_log = Arc::clone(&log);
        child.on_message(move |_message| {
            handler_log.lock().unwrap().push("handler".into());
            Ok(())
        });

        let mut parent = Router::named("parent");
        let parent_log = Arc::clone(&log);
        parent.use_middleware(move |event, bag, next| {
            parent_log.lock().unwrap().push("parent:in".into());
            let result = next.run(event, bag);
            parent_log.lock().unwrap().push("parent:out".into());
            result
        });
        parent.include(child);

        parent.dispatch_message(&message("hi")).unwrap();
        assert_eq!(
            *log.lock().unwrap(),
            vec!["parent:in", "child:in", "handler", "child:out", "parent:out"]
        );
    }
}
