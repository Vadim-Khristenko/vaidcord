package vaidcord

type MessagePayload struct {
	Content         string           `json:"content,omitempty"`
	TTS             bool             `json:"tts,omitempty"`
	Embeds          []map[string]any `json:"embeds,omitempty"`
	Components      []map[string]any `json:"components,omitempty"`
	AllowedMentions map[string]any   `json:"allowed_mentions,omitempty"`
}
