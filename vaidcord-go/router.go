package vaidcord

import (
	"context"
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

func NewRouter() *Router {
	return &Router{}
}

func (r *Router) OnMessage(handler MessageHandler, filters ...MessageFilter) {
	r.messageRoutes = append(r.messageRoutes, messageRoute{filters: filters, handler: handler})
}

func (r *Router) DispatchMessage(ctx context.Context, message Message) error {
	for _, route := range r.messageRoutes {
		if !messageFiltersPass(message, route.filters) {
			continue
		}
		if err := route.handler(ctx, message); err != nil {
			return err
		}
	}
	return nil
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
