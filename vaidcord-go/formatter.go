package vaidcord

import "strings"

var markdownEscaper = strings.NewReplacer(
	"\\", "\\\\",
	"*", "\\*",
	"_", "\\_",
	"`", "\\`",
	"~", "\\~",
	"|", "\\|",
	">", "\\>",
)

func EscapeMarkdown(text string) string {
	return markdownEscaper.Replace(text)
}

func Bold(text string) string {
	return "**" + text + "**"
}

func Italic(text string) string {
	return "*" + text + "*"
}

func InlineCode(text string) string {
	return "`" + strings.ReplaceAll(text, "`", "\\`") + "`"
}

func CodeBlock(code string, language string) string {
	if language != "" {
		return "```" + language + "\n" + strings.ReplaceAll(code, "```", "\\`\\`\\`") + "\n```"
	}
	return "```\n" + strings.ReplaceAll(code, "```", "\\`\\`\\`") + "\n```"
}

func MentionUser(userID string) string {
	return "<@" + userID + ">"
}

func MentionChannel(channelID string) string {
	return "<#" + channelID + ">"
}

func MentionRole(roleID string) string {
	return "<@&" + roleID + ">"
}
