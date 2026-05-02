package vaidcord

import (
	"context"
	"fmt"
	"strings"
)

type MessageHandler func(context.Context, Message) error
type MessageFilter func(Message) bool

type messageRoute struct {
	filters []MessageFilter
	handler MessageHandler
}

type Router struct {
	messageRoutes []messageRoute
}

type MessageRouteBuilder struct {
	router  *Router
	filters []MessageFilter
}

func NewRouter() *Router {
	return &Router{}
}

func (r *Router) OnMessage(handler MessageHandler, filters ...MessageFilter) {
	r.messageRoutes = append(r.messageRoutes, messageRoute{filters: filters, handler: handler})
}

func (r *Router) Message(filters ...MessageFilter) *MessageRouteBuilder {
	return &MessageRouteBuilder{router: r, filters: filters}
}

func (b *MessageRouteBuilder) Use(filters ...MessageFilter) *MessageRouteBuilder {
	b.filters = append(b.filters, filters...)
	return b
}

func (b *MessageRouteBuilder) Handle(handler MessageHandler) {
	b.router.OnMessage(handler, b.filters...)
}

func (r *Router) DispatchMessage(ctx context.Context, message Message) error {
	for _, route := range r.messageRoutes {
		if err := ctx.Err(); err != nil {
			return err
		}
		if !messageFiltersPass(message, route.filters) {
			continue
		}
		if err := callMessageHandler(ctx, route.handler, message); err != nil {
			return err
		}
	}
	return nil
}

func (r *Router) DispatchMessageAsync(ctx context.Context, message Message) <-chan error {
	result := make(chan error, 1)
	go func() {
		defer close(result)
		result <- r.DispatchMessage(ctx, message)
	}()
	return result
}

func callMessageHandler(ctx context.Context, handler MessageHandler, message Message) (err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("vaidcord message handler panic: %v", recovered)
		}
	}()
	if err := ctx.Err(); err != nil {
		return err
	}
	return handler(ctx, message)
}

func messageFiltersPass(message Message, filters []MessageFilter) bool {
	for _, filter := range filters {
		if !filter(message) {
			return false
		}
	}
	return true
}

func ContentStartsWith(prefix string) MessageFilter {
	return func(message Message) bool {
		return strings.HasPrefix(message.Content, prefix)
	}
}

func AuthorID(userID string) MessageFilter {
	return func(message Message) bool {
		return message.Author.ID == userID
	}
}
