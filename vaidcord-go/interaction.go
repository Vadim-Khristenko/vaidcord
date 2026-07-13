package vaidcord

// Interaction types.
const (
	InteractionTypePing                           = 1
	InteractionTypeApplicationCommand             = 2
	InteractionTypeMessageComponent               = 3
	InteractionTypeApplicationCommandAutocomplete = 4
	InteractionTypeModalSubmit                    = 5
)

// Interaction response callback types.
const (
	InteractionResponsePong                             = 1
	InteractionResponseChannelMessageWithSource         = 4
	InteractionResponseDeferredChannelMessageWithSource = 5
	InteractionResponseDeferredUpdateMessage            = 6
	InteractionResponseUpdateMessage                    = 7
	InteractionResponseAutocompleteResult               = 8
	InteractionResponseModal                            = 9
)

type Interaction struct {
	ID            string           `json:"id"`
	ApplicationID string           `json:"application_id"`
	Type          int              `json:"type"`
	Data          *InteractionData `json:"data,omitempty"`
	GuildID       string           `json:"guild_id,omitempty"`
	ChannelID     string           `json:"channel_id,omitempty"`
	Channel       *Channel         `json:"channel,omitempty"`
	Member        *Member          `json:"member,omitempty"`
	User          *User            `json:"user,omitempty"`
	Token         string           `json:"token"`
	Version       int              `json:"version,omitempty"`
	Message       *Message         `json:"message,omitempty"`
	Locale        string           `json:"locale,omitempty"`
	GuildLocale   string           `json:"guild_locale,omitempty"`
}

type InteractionData struct {
	ID            string                  `json:"id,omitempty"`
	Name          string                  `json:"name,omitempty"`
	Type          int                     `json:"type,omitempty"`
	Options       []InteractionDataOption `json:"options,omitempty"`
	CustomID      string                  `json:"custom_id,omitempty"`
	ComponentType int                     `json:"component_type,omitempty"`
	Values        []string                `json:"values,omitempty"`
	TargetID      string                  `json:"target_id,omitempty"`
}

type InteractionDataOption struct {
	Name    string                  `json:"name"`
	Type    int                     `json:"type"`
	Value   any                     `json:"value,omitempty"`
	Options []InteractionDataOption `json:"options,omitempty"`
	Focused bool                    `json:"focused,omitempty"`
}

type InteractionResponse struct {
	Type int                      `json:"type"`
	Data *InteractionResponseData `json:"data,omitempty"`
}

type InteractionResponseData struct {
	TTS             bool             `json:"tts,omitempty"`
	Content         string           `json:"content,omitempty"`
	Embeds          []Embed          `json:"embeds,omitempty"`
	AllowedMentions map[string]any   `json:"allowed_mentions,omitempty"`
	Flags           int              `json:"flags,omitempty"`
	Components      []map[string]any `json:"components,omitempty"`
	CustomID        string           `json:"custom_id,omitempty"`
	Title           string           `json:"title,omitempty"`
}
