package vaidcord

import (
	"context"
	"encoding/json"
	"net/http"
)

// BotConfig configures the high-level Bot facade.
type BotConfig struct {
	Config
	// Intents defaults to IntentsDefault | IntentMessageContent.
	Intents Intents
	// Presence, when set, is embedded into the IDENTIFY payload.
	Presence *PresenceUpdate
}

// BotOption customises a Bot at construction time.
type BotOption func(*Bot)

// WithHTTPClient injects a custom *http.Client for the REST layer.
func WithHTTPClient(httpClient *http.Client) BotOption {
	return func(b *Bot) { b.httpClient = httpClient }
}

// WithDispatcher replaces the internally-created Dispatcher.
func WithDispatcher(dispatcher *Dispatcher) BotOption {
	return func(b *Bot) {
		if dispatcher != nil {
			b.dispatcher = dispatcher
		}
	}
}

// WithBotErrorHandler installs the handler-error callback on the internal
// dispatcher.
func WithBotErrorHandler(handler ErrorHandler) BotOption {
	return func(b *Bot) { b.errorHandler = handler }
}

// Bot is the high-level facade: it owns the gateway connection and the REST
// client, parses gateway dispatches into typed events, and feeds them to the
// Dispatcher.
//
//	bot := vaidcord.NewBot(vaidcord.BotConfig{Config: vaidcord.Config{Token: token}})
//	bot.Include(router)
//	if err := bot.Run(ctx); err != nil { ... }
type Bot struct {
	config       BotConfig
	httpClient   *http.Client
	errorHandler ErrorHandler
	client       *Client
	gateway      *Gateway
	dispatcher   *Dispatcher
}

// NewBot builds a Bot from config; zero-value fields fall back to defaults.
func NewBot(config BotConfig, options ...BotOption) *Bot {
	if config.Intents == 0 {
		config.Intents = IntentsDefault | IntentMessageContent
	}
	bot := &Bot{config: config}
	for _, option := range options {
		option(bot)
	}
	if bot.dispatcher == nil {
		if bot.errorHandler != nil {
			bot.dispatcher = NewDispatcher(WithErrorHandler(bot.errorHandler))
		} else {
			bot.dispatcher = NewDispatcher()
		}
	} else if bot.errorHandler != nil {
		bot.dispatcher.errorHandler = bot.errorHandler
	}
	bot.client = NewClient(config.Config, bot.httpClient)
	gatewayOptions := []GatewayOption{}
	if config.Presence != nil {
		gatewayOptions = append(gatewayOptions, WithGatewayPresence(*config.Presence))
	}
	bot.gateway = NewGateway(bot.client, config.Intents, gatewayOptions...)
	return bot
}

// API exposes the REST client.
func (b *Bot) API() *Client { return b.client }

// Gateway exposes the underlying gateway (presence updates, member requests,
// voice state updates).
func (b *Bot) Gateway() *Gateway { return b.gateway }

// Dispatcher exposes the underlying dispatcher.
func (b *Bot) Dispatcher() *Dispatcher { return b.dispatcher }

// Include registers routers on the internal dispatcher.
func (b *Bot) Include(routers ...*Router) {
	b.dispatcher.Include(routers...)
}

// Run connects to the gateway and dispatches events until ctx is cancelled
// or the connection fails fatally.
func (b *Bot) Run(ctx context.Context) error {
	return b.gateway.Run(ctx, func(ctx context.Context, dispatch GatewayDispatch) {
		event, ok := ParseDispatch(dispatch)
		if !ok {
			return
		}
		// Handler errors are already routed through the dispatcher's error
		// handler; a single failing handler must not kill the connection.
		_ = b.dispatcher.Dispatch(ctx, event)
	})
}

// ParseDispatch converts a raw op 0 gateway frame into a typed Event. The
// second return value is false when the payload could not be decoded.
func ParseDispatch(dispatch GatewayDispatch) (Event, bool) {
	event := Event{Type: EventType(dispatch.Type), Raw: dispatch.Data}
	switch event.Type {
	case EventReady:
		var ready ReadyEvent
		if err := json.Unmarshal(dispatch.Data, &ready); err != nil {
			return event, false
		}
		var application struct {
			Application struct {
				ID string `json:"id"`
			} `json:"application"`
		}
		if json.Unmarshal(dispatch.Data, &application) == nil {
			ready.ApplicationID = application.Application.ID
		}
		event.Ready = &ready
	case EventMessageCreate, EventMessageUpdate:
		var message Message
		if err := json.Unmarshal(dispatch.Data, &message); err != nil {
			return event, false
		}
		event.Message = &message
	case EventMessageDelete:
		var deleted DeletedMessage
		if err := json.Unmarshal(dispatch.Data, &deleted); err != nil {
			return event, false
		}
		event.Deleted = &deleted
	case EventGuildCreate:
		var guild Guild
		if err := json.Unmarshal(dispatch.Data, &guild); err != nil {
			return event, false
		}
		event.Guild = &guild
	case EventInteractionCreate:
		var interaction Interaction
		if err := json.Unmarshal(dispatch.Data, &interaction); err != nil {
			return event, false
		}
		event.Interaction = &interaction
	}
	return event, true
}
