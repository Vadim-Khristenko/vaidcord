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

func (d *Dispatcher) Include(routers ...*Router) {
	d.routers = append(d.routers, routers...)
	d.routes = d.routes[:0]
	for _, router := range d.routers {
		d.routes = append(d.routes, router.routesWithMiddleware(nil)...)
	}
}

func (d *Dispatcher) Dispatch(ctx context.Context, event Event) error {
	for _, item := range d.routes {
		if err := ctx.Err(); err != nil {
			return err
		}
		if item.meta.Type != event.Type || !filtersPass(event, item.filters) {
			continue
		}
		handler := item.handler
		for index := len(item.middlewares) - 1; index >= 0; index-- {
			middleware := item.middlewares[index]
			next := handler
			handler = func(ctx context.Context, event Event) error {
				return middleware(ctx, event, next)
			}
		}
		if err := callHandler(ctx, handler, event); err != nil {
			d.errorHandler(ctx, item.meta, err)
			return err
		}
	}
	return nil
}

func (d *Dispatcher) StartPolling(ctx context.Context, bot *Client, options ...PollingOption) error {
	config := pollingConfig{}
	for _, option := range options {
		option(&config)
	}
	_ = bot
	_ = config
	<-ctx.Done()
	return ctx.Err()
}

func defaultErrorHandler(_ context.Context, meta EventMeta, err error) {
	log.Printf("vaidcord handler error router=%s route=%s event=%s error=%v", meta.Router, meta.Route, meta.Type, err)
}
