package vaidcord

import (
	"context"
	"fmt"
	"reflect"
	"runtime"
	"strings"
)

type EventType string

const (
	EventReady         EventType = "READY"
	EventMessageCreate EventType = "MESSAGE_CREATE"
)

type Event struct {
	Type    EventType
	Ready   *ReadyEvent
	Message *Message
}

type ReadyEvent struct {
	User User
}

type EventMeta struct {
	Router string
	Route  string
	Type   EventType
}

type Handler func(context.Context, Event) error
type Middleware func(context.Context, Event, Handler) error
type Filter func(Event) bool

type MessageHandler func(context.Context, Message) error
type MessageFilter func(Message) bool
type ReadyHandler func(context.Context, ReadyEvent) error

type route struct {
	meta        EventMeta
	filters     []Filter
	middlewares []Middleware
	handler     Handler
}

type Router struct {
	name        string
	routes      []route
	children    []*Router
	middlewares []Middleware
}

type RouteBuilder struct {
	router  *Router
	event   EventType
	name    string
	filters []Filter
}

type MessageRouteBuilder struct {
	route *RouteBuilder
}

type ReadyRouteBuilder struct {
	route *RouteBuilder
}

func NewRouter(name ...string) *Router {
	routerName := ""
	if len(name) > 0 {
		routerName = name[0]
	}
	return &Router{name: routerName}
}

func (r *Router) Name() string {
	return r.name
}

func (r *Router) Include(children ...*Router) {
	r.children = append(r.children, children...)
}

func (r *Router) Use(middlewares ...Middleware) {
	r.middlewares = append(r.middlewares, middlewares...)
}

func (r *Router) OnReady(filters ...Filter) *ReadyRouteBuilder {
	return &ReadyRouteBuilder{route: &RouteBuilder{router: r, event: EventReady, filters: filters}}
}

func (r *Router) OnMessageCreate(filters ...MessageFilter) *MessageRouteBuilder {
	return &MessageRouteBuilder{route: &RouteBuilder{
		router:  r,
		event:   EventMessageCreate,
		filters: wrapMessageFilters(filters),
	}}
}

func (r *Router) Message(filters ...MessageFilter) *MessageRouteBuilder {
	return r.OnMessageCreate(filters...)
}

func (r *Router) OnMessage(handler MessageHandler, filters ...MessageFilter) {
	r.OnMessageCreate(filters...).Handle(handler)
}

func (b *RouteBuilder) Name(name string) *RouteBuilder {
	b.name = name
	return b
}

func (b *RouteBuilder) Use(filters ...Filter) *RouteBuilder {
	b.filters = append(b.filters, filters...)
	return b
}

func (b *RouteBuilder) Handle(handler Handler) {
	b.router.routes = append(b.router.routes, route{
		meta: EventMeta{
			Router: b.router.name,
			Route:  routeName(b.name, handler),
			Type:   b.event,
		},
		filters:     b.filters,
		middlewares: append([]Middleware(nil), b.router.middlewares...),
		handler:     handler,
	})
}

func (b *MessageRouteBuilder) Name(name string) *MessageRouteBuilder {
	b.route.Name(name)
	return b
}

func (b *MessageRouteBuilder) Use(filters ...MessageFilter) *MessageRouteBuilder {
	b.route.filters = append(b.route.filters, wrapMessageFilters(filters)...)
	return b
}

func (b *MessageRouteBuilder) Handle(handler MessageHandler) {
	b.route.Handle(func(ctx context.Context, event Event) error {
		if event.Message == nil {
			return nil
		}
		return handler(ctx, *event.Message)
	})
}

func (b *ReadyRouteBuilder) Name(name string) *ReadyRouteBuilder {
	b.route.Name(name)
	return b
}

func (b *ReadyRouteBuilder) Handle(handler ReadyHandler) {
	b.route.Handle(func(ctx context.Context, event Event) error {
		if event.Ready == nil {
			return nil
		}
		return handler(ctx, *event.Ready)
	})
}

func (r *Router) routesWithMiddleware(parent []Middleware) []route {
	chain := append(append([]Middleware(nil), parent...), r.middlewares...)
	out := make([]route, 0, len(r.routes))
	for _, item := range r.routes {
		item.middlewares = append(append([]Middleware(nil), chain...), item.middlewares...)
		out = append(out, item)
	}
	for _, child := range r.children {
		out = append(out, child.routesWithMiddleware(chain)...)
	}
	return out
}

func (r *Router) DispatchMessage(ctx context.Context, message Message) error {
	dispatcher := NewDispatcher()
	dispatcher.Include(r)
	return dispatcher.Dispatch(ctx, Event{Type: EventMessageCreate, Message: &message})
}

func (r *Router) DispatchMessageAsync(ctx context.Context, message Message) <-chan error {
	result := make(chan error, 1)
	go func() {
		defer close(result)
		result <- r.DispatchMessage(ctx, message)
	}()
	return result
}

func callHandler(ctx context.Context, handler Handler, event Event) (err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("vaidcord handler panic: %v", recovered)
		}
	}()
	if err := ctx.Err(); err != nil {
		return err
	}
	return handler(ctx, event)
}

func wrapMessageFilters(filters []MessageFilter) []Filter {
	wrapped := make([]Filter, 0, len(filters))
	for _, filter := range filters {
		filter := filter
		wrapped = append(wrapped, func(event Event) bool {
			return event.Message != nil && filter(*event.Message)
		})
	}
	return wrapped
}

func filtersPass(event Event, filters []Filter) bool {
	for _, filter := range filters {
		if !filter(event) {
			return false
		}
	}
	return true
}

func routeName(name string, handler any) string {
	if name != "" {
		return name
	}
	value := runtime.FuncForPC(reflect.ValueOf(handler).Pointer())
	if value == nil {
		return ""
	}
	return value.Name()
}

func ContentStartsWith(prefix string) MessageFilter {
	return func(message Message) bool {
		return strings.HasPrefix(message.Content, prefix)
	}
}

func Command(name string) MessageFilter {
	return CommandWithPrefixes(name)
}

func CommandWithPrefixes(name string, prefixes ...string) MessageFilter {
	needle := strings.ToLower(strings.TrimSpace(name))
	resolvedPrefixes := resolveCommandPrefixes(prefixes)
	return func(message Message) bool {
		text := strings.TrimSpace(message.Content)
		if text == "" {
			return false
		}
		token := text
		if index := strings.IndexByte(text, ' '); index >= 0 {
			token = text[:index]
		}
		for _, prefix := range resolvedPrefixes {
			if strings.HasPrefix(token, prefix) {
				namePart := strings.TrimPrefix(token, prefix)
				if at := strings.IndexByte(namePart, '@'); at >= 0 {
					namePart = namePart[:at]
				}
				return strings.EqualFold(namePart, needle)
			}
		}
		return false
	}
}

func CommandStart(prefixes ...string) MessageFilter {
	return CommandWithPrefixes("start", prefixes...)
}

func CommandHelp(prefixes ...string) MessageFilter {
	return CommandWithPrefixes("help", prefixes...)
}

func CommandSettings(prefixes ...string) MessageFilter {
	return CommandWithPrefixes("settings", prefixes...)
}

func resolveCommandPrefixes(prefixes []string) []string {
	if len(prefixes) == 0 {
		return []string{"/", "!", "."}
	}
	out := make([]string, 0, len(prefixes))
	for _, prefix := range prefixes {
		if prefix == "" {
			continue
		}
		out = append(out, prefix)
	}
	if len(out) == 0 {
		return []string{"/", "!", "."}
	}
	return out
}

func AuthorID(userID string) MessageFilter {
	return func(message Message) bool {
		return message.Author.ID == userID
	}
}
