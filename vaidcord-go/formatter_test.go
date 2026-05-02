package vaidcord

import "testing"

func TestFormatterHelpers(t *testing.T) {
	if got := Bold("ok"); got != "**ok**" {
		t.Fatalf("unexpected bold: %s", got)
	}
	if got := MentionChannel("123"); got != "<#123>" {
		t.Fatalf("unexpected channel mention: %s", got)
	}
	if got := EscapeMarkdown("*hi*"); got != "\\*hi\\*" {
		t.Fatalf("unexpected escaped markdown: %s", got)
	}
}
