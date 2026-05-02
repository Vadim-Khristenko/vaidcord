package vaidcord

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
