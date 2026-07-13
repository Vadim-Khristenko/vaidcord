package vaidcord

// Intents is the bit set sent in the IDENTIFY payload that controls which
// gateway events Discord delivers to the shard.
type Intents int

const (
	IntentGuilds                      Intents = 1 << 0
	IntentGuildMembers                Intents = 1 << 1
	IntentGuildModeration             Intents = 1 << 2
	IntentGuildExpressions            Intents = 1 << 3
	IntentGuildIntegrations           Intents = 1 << 4
	IntentGuildWebhooks               Intents = 1 << 5
	IntentGuildInvites                Intents = 1 << 6
	IntentGuildVoiceStates            Intents = 1 << 7
	IntentGuildPresences              Intents = 1 << 8
	IntentGuildMessages               Intents = 1 << 9
	IntentGuildMessageReactions       Intents = 1 << 10
	IntentGuildMessageTyping          Intents = 1 << 11
	IntentDirectMessages              Intents = 1 << 12
	IntentDirectMessageReactions      Intents = 1 << 13
	IntentDirectMessageTyping         Intents = 1 << 14
	IntentMessageContent              Intents = 1 << 15
	IntentGuildScheduledEvents        Intents = 1 << 16
	IntentAutoModerationConfiguration Intents = 1 << 20
	IntentAutoModerationExecution     Intents = 1 << 21
	IntentGuildMessagePolls           Intents = 1 << 24
	IntentDirectMessagePolls          Intents = 1 << 25
)

// IntentsDefault covers the unprivileged intents most bots need.
const IntentsDefault = IntentGuilds | IntentGuildMessages | IntentDirectMessages

// IntentsAllUnprivileged is every intent that does not require special
// approval in the Discord developer portal.
const IntentsAllUnprivileged = IntentGuilds |
	IntentGuildModeration |
	IntentGuildExpressions |
	IntentGuildIntegrations |
	IntentGuildWebhooks |
	IntentGuildInvites |
	IntentGuildVoiceStates |
	IntentGuildMessages |
	IntentGuildMessageReactions |
	IntentGuildMessageTyping |
	IntentDirectMessages |
	IntentDirectMessageReactions |
	IntentDirectMessageTyping |
	IntentGuildScheduledEvents |
	IntentAutoModerationConfiguration |
	IntentAutoModerationExecution |
	IntentGuildMessagePolls |
	IntentDirectMessagePolls

// IntentsAll is every documented intent including the privileged ones
// (guild members, presences, message content).
const IntentsAll = IntentsAllUnprivileged |
	IntentGuildMembers |
	IntentGuildPresences |
	IntentMessageContent

// Has reports whether every bit in other is set on i.
func (i Intents) Has(other Intents) bool {
	return i&other == other
}
