package vaidcord

type Guild struct {
	ID                          string   `json:"id"`
	Name                        string   `json:"name"`
	Icon                        string   `json:"icon,omitempty"`
	Splash                      string   `json:"splash,omitempty"`
	Description                 string   `json:"description,omitempty"`
	OwnerID                     string   `json:"owner_id,omitempty"`
	AFKChannelID                string   `json:"afk_channel_id,omitempty"`
	AFKTimeout                  int      `json:"afk_timeout,omitempty"`
	VerificationLevel           int      `json:"verification_level,omitempty"`
	DefaultMessageNotifications int      `json:"default_message_notifications,omitempty"`
	ExplicitContentFilter       int      `json:"explicit_content_filter,omitempty"`
	Roles                       []Role   `json:"roles,omitempty"`
	Features                    []string `json:"features,omitempty"`
	MFALevel                    int      `json:"mfa_level,omitempty"`
	ApplicationID               string   `json:"application_id,omitempty"`
	SystemChannelID             string   `json:"system_channel_id,omitempty"`
	RulesChannelID              string   `json:"rules_channel_id,omitempty"`
	MaxMembers                  int      `json:"max_members,omitempty"`
	VanityURLCode               string   `json:"vanity_url_code,omitempty"`
	Banner                      string   `json:"banner,omitempty"`
	PremiumTier                 int      `json:"premium_tier,omitempty"`
	PreferredLocale             string   `json:"preferred_locale,omitempty"`
	NSFWLevel                   int      `json:"nsfw_level,omitempty"`
	// Extra fields present on the GUILD_CREATE gateway payload.
	JoinedAt    string    `json:"joined_at,omitempty"`
	Large       bool      `json:"large,omitempty"`
	Unavailable bool      `json:"unavailable,omitempty"`
	MemberCount int       `json:"member_count,omitempty"`
	Members     []Member  `json:"members,omitempty"`
	Channels    []Channel `json:"channels,omitempty"`
	Threads     []Channel `json:"threads,omitempty"`
}

type Role struct {
	ID           string    `json:"id"`
	Name         string    `json:"name"`
	Color        int       `json:"color,omitempty"`
	Hoist        bool      `json:"hoist,omitempty"`
	Icon         string    `json:"icon,omitempty"`
	UnicodeEmoji string    `json:"unicode_emoji,omitempty"`
	Position     int       `json:"position,omitempty"`
	Permissions  string    `json:"permissions,omitempty"`
	Managed      bool      `json:"managed,omitempty"`
	Mentionable  bool      `json:"mentionable,omitempty"`
	Tags         *RoleTags `json:"tags,omitempty"`
	Flags        int       `json:"flags,omitempty"`
}

type RoleTags struct {
	BotID         string `json:"bot_id,omitempty"`
	IntegrationID string `json:"integration_id,omitempty"`
}

type Member struct {
	User                       *User    `json:"user,omitempty"`
	Nick                       string   `json:"nick,omitempty"`
	Avatar                     string   `json:"avatar,omitempty"`
	Roles                      []string `json:"roles,omitempty"`
	JoinedAt                   string   `json:"joined_at,omitempty"`
	PremiumSince               string   `json:"premium_since,omitempty"`
	Deaf                       bool     `json:"deaf,omitempty"`
	Mute                       bool     `json:"mute,omitempty"`
	Flags                      int      `json:"flags,omitempty"`
	Pending                    bool     `json:"pending,omitempty"`
	Permissions                string   `json:"permissions,omitempty"`
	CommunicationDisabledUntil string   `json:"communication_disabled_until,omitempty"`
}
