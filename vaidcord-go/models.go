package vaidcord

type User struct {
	ID            string `json:"id"`
	Username      string `json:"username"`
	Discriminator string `json:"discriminator,omitempty"`
	GlobalName    string `json:"global_name,omitempty"`
	Bot           bool   `json:"bot,omitempty"`
	System        bool   `json:"system,omitempty"`
	Avatar        string `json:"avatar,omitempty"`
	Banner        string `json:"banner,omitempty"`
	PublicFlags   int    `json:"public_flags,omitempty"`
}

type Channel struct {
	ID                         string           `json:"id"`
	Type                       int              `json:"type"`
	GuildID                    string           `json:"guild_id,omitempty"`
	Name                       string           `json:"name,omitempty"`
	Topic                      string           `json:"topic,omitempty"`
	Position                   int              `json:"position,omitempty"`
	NSFW                       bool             `json:"nsfw,omitempty"`
	ParentID                   string           `json:"parent_id,omitempty"`
	LastMessageID              string           `json:"last_message_id,omitempty"`
	RateLimitPerUser           int              `json:"rate_limit_per_user,omitempty"`
	PermissionOverwrites       []map[string]any `json:"permission_overwrites,omitempty"`
	DefaultAutoArchiveDuration int              `json:"default_auto_archive_duration,omitempty"`
}

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

type MessagePayload struct {
	Content         string           `json:"content,omitempty"`
	TTS             bool             `json:"tts,omitempty"`
	Embeds          []map[string]any `json:"embeds,omitempty"`
	Components      []map[string]any `json:"components,omitempty"`
	AllowedMentions map[string]any   `json:"allowed_mentions,omitempty"`
}
