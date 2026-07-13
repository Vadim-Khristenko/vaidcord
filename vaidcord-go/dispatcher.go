package vaidcord

import (
	"context"
	"log"
)

type ErrorHandler func(context.Context, EventMeta, error)

type Dispatcher struct {
	routers      []*Router
	routes       []route
	errorHandler ErrorHandler
}

type DispatcherOption func(*Dispatcher)

type PollingOption func(*pollingConfig)

type pollingConfig struct {
	dropPendingUpdates bool
	intents            Intents
	gatewayOptions     []GatewayOption
}

func NewDispatcher(options ...DispatcherOption) *Dispatcher {
	dispatcher := &Dispatcher{errorHandler: defaultErrorHandler}
	for _, option := range options {
		option(dispatcher)
	}
	return dispatcher
}

func WithErrorHandler(handler ErrorHandler) DispatcherOption {
	return func(dispatcher *Dispatcher) {
		if handler != nil {
			dispatcher.errorHandler = handler
		}
	}
}

func WithDropPendingUpdates(enabled bool) PollingOption {
	return func(config *pollingConfig) {
		config.dropPendingUpdates = enabled
	}
}

// WithIntents selects the gateway intents used by StartPolling.
func WithIntents(intents Intents) PollingOption {
	return func(config *pollingConfig) {
		config.intents = intents
	}
}

// WithGatewayOptions forwards options to the gateway created by StartPolling.
func WithGatewayOptions(options ...GatewayOption) PollingOption {
	return func(config *pollingConfig) {
		config.gatewayOptions = append(config.gatewayOptions, options...)
	}
}

func (d *Dispatcher) Include(routers ...*Router) {
	d.routers = append(d.routers, routers...)
	d.routes = d.routes[:0]
	for _, router := range d.routers {
		d.routes = append(d.routes, router.routesWithMiddleware(nil)...)
	}
	for index := range d.routes {
		d.routes[index].wrapped = composeMiddleware(d.routes[index].handler, d.routes[index].middlewares)
	}
}

// composeMiddleware folds the middleware stack around the handler once. The
// result is identical to the per-dispatch loop that used to live in Dispatch
// but it pays the closure-allocation cost a single time instead of per event.
func composeMiddleware(handler Handler, middlewares []Middleware) Handler {
	for index := len(middlewares) - 1; index >= 0; index-- {
		middleware := middlewares[index]
		next := handler
		handler = func(ctx context.Context, event Event) error {
			return middleware(ctx, event, next)
		}
	}
	return handler
}

func (d *Dispatcher) Dispatch(ctx context.Context, event Event) error {
	for _, item := range d.routes {
		if err := ctx.Err(); err != nil {
			return err
		}
		if item.meta.Type != event.Type || !filtersPass(event, item.filters) {
			continue
		}
		handler := item.wrapped
		if handler == nil {
			// Fallback for routes that bypassed Dispatcher.Include (e.g.
			// Router.DispatchMessage internal wiring).
			handler = composeMiddleware(item.handler, item.middlewares)
		}
		if err := callHandler(ctx, handler, event); err != nil {
			d.errorHandler(ctx, item.meta, err)
			return err
		}
	}
	return nil
}

// StartPolling connects the client to the Discord gateway and dispatches
// every typed event into the registered routers until ctx is cancelled or a
// fatal gateway close code is received. It is the low-level equivalent of
// Bot.Run for callers who already own a *Client.
func (d *Dispatcher) StartPolling(ctx context.Context, bot *Client, options ...PollingOption) error {
	config := pollingConfig{intents: IntentsDefault | IntentMessageContent}
	for _, option := range options {
		option(&config)
	}
	gateway := NewGateway(bot, config.intents, config.gatewayOptions...)
	return gateway.Run(ctx, func(ctx context.Context, dispatch GatewayDispatch) {
		event, ok := ParseDispatch(dispatch)
		if !ok {
			return
		}
		_ = d.Dispatch(ctx, event)
	})
}

func defaultErrorHandler(_ context.Context, meta EventMeta, err error) {
	log.Printf("vaidcord handler error router=%s route=%s event=%s error=%v", meta.Router, meta.Route, meta.Type, err)
}
