//! Middleware with `(event, next)` semantics.
//!
//! Middleware run *around* the matched handler: outer middleware wraps inner
//! middleware and the innermost middleware wraps the handler itself
//! (UNITED.md §7). Chains are composed once at include-time by the
//! [`Dispatcher`](crate::Dispatcher) so the per-event hot path is a plain
//! nested function call — no per-dispatch allocation.
//!
//! ```
//! use vaidcord::{Dispatcher, Event, Router};
//!
//! let mut router = Router::new();
//! router.use_middleware(|event: &vaidcord::Event, bag: &vaidcord::ExtractBag, next: vaidcord::Next<'_>| {
//!     // before handler
//!     let result = next.run(event, bag);
//!     // after handler
//!     result
//! });
//! ```

use std::sync::Arc;

use crate::extract::ExtractBag;
use crate::events::Event;
use crate::router::HandlerResult;

/// The composed continuation a middleware calls to keep the chain going.
///
/// Calling [`Next::run`] invokes the rest of the middleware chain and,
/// finally, the route handler. Not calling it short-circuits the route.
#[derive(Clone, Copy)]
pub struct Next<'a> {
    inner: &'a (dyn Fn(&Event, &ExtractBag) -> HandlerResult + Send + Sync),
}

impl Next<'_> {
    /// Continue with the remaining middleware chain and handler.
    pub fn run(&self, event: &Event, bag: &ExtractBag) -> HandlerResult {
        (self.inner)(event, bag)
    }
}

/// A shareable middleware: `(event, bag, next) -> result`.
pub type Middleware =
    Arc<dyn for<'a> Fn(&Event, &ExtractBag, Next<'a>) -> HandlerResult + Send + Sync>;

/// Wrap a closure into a [`Middleware`].
pub fn middleware<F>(function: F) -> Middleware
where
    F: for<'a> Fn(&Event, &ExtractBag, Next<'a>) -> HandlerResult + Send + Sync + 'static,
{
    Arc::new(function)
}

/// The fully-composed handler chain stored on a prepared route.
pub(crate) type ChainFn = Arc<dyn Fn(&Event, &ExtractBag) -> HandlerResult + Send + Sync>;

/// Fold the middleware stack around `handler` once.
///
/// `middlewares[0]` becomes the outermost layer; the last middleware wraps
/// the handler directly. This pays the closure-allocation cost a single time
/// (at include-time) instead of on every dispatched event.
pub(crate) fn compose(handler: ChainFn, middlewares: &[Middleware]) -> ChainFn {
    let mut chain = handler;
    for entry in middlewares.iter().rev() {
        let layer = Arc::clone(entry);
        let inner = chain;
        chain = Arc::new(move |event: &Event, bag: &ExtractBag| {
            layer(event, bag, Next { inner: &*inner })
        });
    }
    chain
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    fn probe_event() -> Event {
        Event::Unknown {
            name: "TEST".to_string(),
            data: serde_json::Value::Null,
        }
    }

    #[test]
    fn compose_orders_outer_before_inner_before_handler() {
        let log: Arc<Mutex<Vec<&'static str>>> = Arc::new(Mutex::new(Vec::new()));
        let handler_log = Arc::clone(&log);
        let handler: ChainFn = Arc::new(move |_event, _bag| {
            handler_log.lock().unwrap().push("handler");
            Ok(())
        });

        let make = |label_in: &'static str, label_out: &'static str| {
            let log = Arc::clone(&log);
            middleware(move |event: &Event, bag: &ExtractBag, next: Next<'_>| {
                log.lock().unwrap().push(label_in);
                let result = next.run(event, bag);
                log.lock().unwrap().push(label_out);
                result
            })
        };

        let chain = compose(handler, &[make("outer:in", "outer:out"), make("inner:in", "inner:out")]);
        chain(&probe_event(), &ExtractBag::new()).unwrap();
        assert_eq!(
            *log.lock().unwrap(),
            vec!["outer:in", "inner:in", "handler", "inner:out", "outer:out"]
        );
    }

    #[test]
    fn middleware_can_short_circuit_by_not_calling_next() {
        let called = Arc::new(Mutex::new(false));
        let handler_called = Arc::clone(&called);
        let handler: ChainFn = Arc::new(move |_event, _bag| {
            *handler_called.lock().unwrap() = true;
            Ok(())
        });
        let blocker = middleware(|_event: &Event, _bag: &ExtractBag, _next: Next<'_>| Ok(()));
        let chain = compose(handler, &[blocker]);
        chain(&probe_event(), &ExtractBag::new()).unwrap();
        assert!(!*called.lock().unwrap());
    }
}
