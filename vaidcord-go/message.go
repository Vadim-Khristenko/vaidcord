package vaidcord

type Message struct {
	ID              string           `json:"id"`
	ChannelID       string           `json:"channel_id"`
	GuildID         string           `json:"guild_id,omitempty"`
	Author          User             `json:"author"`
	Content         string           `json:"content"`
	Timestamp       string           `json:"timestamp,omitempty"`
	EditedTimestamp string           `json:"edited_timestamp,omitempty"`
	TTS             bool             `json:"tts,omitempty"`
	MentionEveryone bool             `json:"mention_everyone,omitempty"`
	Mentions        []User           `json:"mentions,omitempty"`
	Embeds          []map[string]any `json:"embeds,omitempty"`
	Attachments     []map[string]any `json:"attachments,omitempty"`
	Components      []map[string]any `json:"components,omitempty"`
	Flags           int              `json:"flags,omitempty"`
}

type EditedMessage struct {
	Message
	Before *Message `json:"-"`
}

type DeletedMessage struct {
	ID        string `json:"id"`
	ChannelID string `json:"channel_id"`
	GuildID   string `json:"guild_id,omitempty"`
}

type BulkDeletedMessages struct {
	IDs       []string `json:"ids"`
	ChannelID string   `json:"channel_id"`
	GuildID   string   `json:"guild_id,omitempty"`
}

type MessagePayload struct {
	Content         string           `json:"content,omitempty"`
	TTS             bool             `json:"tts,omitempty"`
	Embeds          []map[string]any `json:"embeds,omitempty"`
	Components      []map[string]any `json:"components,omitempty"`
	AllowedMentions map[string]any   `json:"allowed_mentions,omitempty"`
}
