//! Standalone dispatcher with precomputed middleware chains.
//!
//! [`Dispatcher::include`] flattens a router tree into routes and composes
//! each route's middleware chain exactly once. [`Dispatcher::dispatch`] then
//! walks the prepared routes: kind match -> filters -> composed chain — with
//! no per-event closure allocation (UNITED.md §7).

use crate::events::{Event, EventKind};
use crate::extract::ExtractBag;
use crate::filters::FilterOutcome;
use crate::middleware::{ChainFn, Middleware, compose};
use crate::models::Message;
use crate::router::{CollectedRoute, HandlerResult, Router, SharedMessageFilter};

struct PreparedRoute {
    kind: EventKind,
    filters: Vec<SharedMessageFilter>,
    chain: ChainFn,
}

/// Composes routers + middleware into a flat, precompiled dispatch table.
#[derive(Default)]
pub struct Dispatcher {
    middlewares: Vec<Middleware>,
    collected: Vec<CollectedRoute>,
    prepared: Vec<PreparedRoute>,
}

impl Dispatcher {
    /// Create an empty dispatcher.
    pub fn new() -> Self {
        Self::default()
    }

    /// Attach a dispatcher-level middleware. It wraps *outside* every router
    /// middleware, for all routes (including routers included later).
    pub fn use_middleware<F>(&mut self, middleware: F)
    where
        F: for<'a> Fn(&Event, &ExtractBag, crate::middleware::Next<'a>) -> HandlerResult
            + Send
            + Sync
            + 'static,
    {
        self.middlewares.push(std::sync::Arc::new(middleware));
        self.recompose();
    }

    /// Include a router tree. Middleware chains for every flattened route are
    /// composed here, once, so dispatching stays allocation-free.
    pub fn include(&mut self, router: &Router) {
        self.collected.extend(router.collect_routes(&[]));
        self.recompose();
    }

    fn recompose(&mut self) {
        self.prepared = self
            .collected
            .iter()
            .map(|route| {
                let mut chain: Vec<Middleware> = self.middlewares.clone();
                chain.extend(route.middlewares.iter().cloned());
                PreparedRoute {
                    kind: route.kind,
                    filters: route.filters.clone(),
                    chain: compose(std::sync::Arc::clone(&route.handler), &chain),
                }
            })
            .collect();
    }

    /// Number of prepared routes.
    pub fn route_count(&self) -> usize {
        self.prepared.len()
    }

    /// Dispatch one event through every matching route, in registration
    /// order. Filters run first; the first rejecting filter short-circuits
    /// the route. The first handler/middleware error aborts the dispatch.
    pub fn dispatch(&self, event: &Event) -> HandlerResult {
        let kind = event.kind();
        // Shared empty bag for filter-less routes: avoids the per-route
        // HashMap allocation. Routes with filters get a private bag because
        // filters can contribute extracted values.
        let empty_bag = ExtractBag::new();
        for route in &self.prepared {
            if route.kind != kind {
                continue;
            }
            if route.filters.is_empty() {
                (route.chain)(event, &empty_bag)?;
                continue;
            }
            // Filters are message filters; a filtered route can only match
            // message-shaped events.
            let Some(message) = event.message() else {
                continue;
            };
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
                (route.chain)(event, &bag)?;
            }
        }
        Ok(())
    }

    /// Convenience wrapper: dispatch a `MESSAGE_CREATE` event.
    pub fn dispatch_message(&self, message: &Message) -> HandlerResult {
        self.dispatch(&Event::MessageCreate(message.clone()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::User;
    use std::sync::{Arc, Mutex};

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

    fn logging_middleware(
        log: &Arc<Mutex<Vec<String>>>,
        label: &'static str,
    ) -> impl for<'a> Fn(&Event, &ExtractBag, crate::middleware::Next<'a>) -> HandlerResult
    + Send
    + Sync
    + 'static {
        let log = Arc::clone(log);
        move |event, bag, next| {
            log.lock().unwrap().push(format!("{label}:in"));
            let result = next.run(event, bag);
            log.lock().unwrap().push(format!("{label}:out"));
            result
        }
    }

    #[test]
    fn dispatcher_composes_outer_router_handler_order() {
        let log: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));

        let mut inner = Router::named("inner");
        inner.use_middleware(logging_middleware(&log, "inner"));
        let handler_log = Arc::clone(&log);
        inner.on_message(move |_message| {
            handler_log.lock().unwrap().push("handler".into());
            Ok(())
        });

        let mut outer = Router::named("outer");
        outer.use_middleware(logging_middleware(&log, "outer"));
        outer.include(inner);

        let mut dispatcher = Dispatcher::new();
        dispatcher.use_middleware(logging_middleware(&log, "dispatcher"));
        dispatcher.include(&outer);

        dispatcher.dispatch_message(&message("hi")).unwrap();
        assert_eq!(
            *log.lock().unwrap(),
            vec![
                "dispatcher:in",
                "outer:in",
                "inner:in",
                "handler",
                "inner:out",
                "outer:out",
                "dispatcher:out"
            ]
        );
    }

    #[test]
    fn dispatcher_middleware_added_after_include_still_wraps() {
        let log: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let mut router = Router::new();
        let handler_log = Arc::clone(&log);
        router.on_message(move |_| {
            handler_log.lock().unwrap().push("handler".into());
            Ok(())
        });

        let mut dispatcher = Dispatcher::new();
        dispatcher.include(&router);
        dispatcher.use_middleware(logging_middleware(&log, "late"));

        dispatcher.dispatch_message(&message("x")).unwrap();
        assert_eq!(
            *log.lock().unwrap(),
            vec!["late:in", "handler", "late:out"]
        );
    }

    #[test]
    fn middleware_does_not_run_when_filters_reject() {
        let log: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let mut router = Router::new();
        router.use_middleware(logging_middleware(&log, "mw"));
        let handler_log = Arc::clone(&log);
        router.on_message_filtered(
            move |_| {
                handler_log.lock().unwrap().push("handler".into());
                Ok(())
            },
            vec![crate::content_starts_with("!")],
        );

        let mut dispatcher = Dispatcher::new();
        dispatcher.include(&router);

        dispatcher.dispatch_message(&message("plain")).unwrap();
        assert!(log.lock().unwrap().is_empty());
        dispatcher.dispatch_message(&message("!go")).unwrap();
        assert_eq!(*log.lock().unwrap(), vec!["mw:in", "handler", "mw:out"]);
    }

    #[test]
    fn middleware_short_circuit_skips_handler() {
        let calls: Arc<Mutex<Vec<&'static str>>> = Arc::new(Mutex::new(Vec::new()));
        let mut router = Router::new();
        let gate = Arc::clone(&calls);
        router.use_middleware(move |event: &Event, bag: &ExtractBag, next| {
            gate.lock().unwrap().push("gate");
            if event.message().map(|m| m.content.as_str()) == Some("blocked") {
                return Ok(());
            }
            next.run(event, bag)
        });
        let handler_calls = Arc::clone(&calls);
        router.on_message(move |_| {
            handler_calls.lock().unwrap().push("handler");
            Ok(())
        });

        let mut dispatcher = Dispatcher::new();
        dispatcher.include(&router);

        dispatcher.dispatch_message(&message("blocked")).unwrap();
        assert_eq!(*calls.lock().unwrap(), vec!["gate"]);
        dispatcher.dispatch_message(&message("open")).unwrap();
        assert_eq!(*calls.lock().unwrap(), vec!["gate", "gate", "handler"]);
    }

    #[test]
    fn dispatcher_routes_events_by_kind() {
        let hits: Arc<Mutex<Vec<&'static str>>> = Arc::new(Mutex::new(Vec::new()));
        let mut router = Router::new();
        let ready_hits = Arc::clone(&hits);
        router.on_ready(move |ready| {
            assert_eq!(ready.session_id, "s1");
            ready_hits.lock().unwrap().push("ready");
            Ok(())
        });
        let message_hits = Arc::clone(&hits);
        router.on_message(move |_| {
            message_hits.lock().unwrap().push("message");
            Ok(())
        });

        let mut dispatcher = Dispatcher::new();
        dispatcher.include(&router);
        assert_eq!(dispatcher.route_count(), 2);

        let ready = Event::parse(
            "READY",
            serde_json::json!({"user": {"id": "1", "username": "b"}, "session_id": "s1"}),
        );
        dispatcher.dispatch(&ready).unwrap();
        dispatcher.dispatch_message(&message("hello")).unwrap();
        assert_eq!(*hits.lock().unwrap(), vec!["ready", "message"]);
    }
}
