package vaidcord

import (
	"context"
	"testing"
)

func TestFSMMemoryStorageStateAndData(t *testing.T) {
	ctx := context.Background()
	manager := NewFSMManager(nil)

	alice := manager.User("alice")
	bob := manager.User("bob")

	if err := alice.SetState(ctx, "ordering:waiting_for_address"); err != nil {
		t.Fatal(err)
	}
	state, err := alice.GetState(ctx)
	if err != nil || state != "ordering:waiting_for_address" {
		t.Fatalf("unexpected state: %q %v", state, err)
	}
	// Keys are isolated.
	if state, _ := bob.GetState(ctx); state != "" {
		t.Fatalf("bob should have no state, got %q", state)
	}

	if _, err := alice.UpdateData(ctx, map[string]any{"item": "pizza"}); err != nil {
		t.Fatal(err)
	}
	data, err := alice.UpdateData(ctx, map[string]any{"count": 2})
	if err != nil {
		t.Fatal(err)
	}
	if data["item"] != "pizza" || data["count"] != 2 {
		t.Fatalf("unexpected merged data: %v", data)
	}

	// GetData returns a copy: mutating it must not affect storage.
	copied, _ := alice.GetData(ctx)
	copied["item"] = "tampered"
	fresh, _ := alice.GetData(ctx)
	if fresh["item"] != "pizza" {
		t.Fatalf("storage data was mutated through a copy: %v", fresh)
	}

	if err := alice.Clear(ctx); err != nil {
		t.Fatal(err)
	}
	if state, _ := alice.GetState(ctx); state != "" {
		t.Fatalf("state should be cleared, got %q", state)
	}
	if data, _ := alice.GetData(ctx); len(data) != 0 {
		t.Fatalf("data should be cleared, got %v", data)
	}
}

func TestFSMScopedKeysAreDistinct(t *testing.T) {
	ctx := context.Background()
	manager := NewFSMManager(NewMemoryFSMStorage())

	if err := manager.Member("g1", "u1").SetState(ctx, "member-state"); err != nil {
		t.Fatal(err)
	}
	if err := manager.Guild("g1").SetState(ctx, "guild-state"); err != nil {
		t.Fatal(err)
	}
	if err := manager.Channel("c1").SetState(ctx, "channel-state"); err != nil {
		t.Fatal(err)
	}
	if err := manager.Custom("wizard-7").SetState(ctx, "custom-state"); err != nil {
		t.Fatal(err)
	}

	member, _ := manager.Member("g1", "u1").GetState(ctx)
	guild, _ := manager.Guild("g1").GetState(ctx)
	channel, _ := manager.Channel("c1").GetState(ctx)
	custom, _ := manager.Custom("wizard-7").GetState(ctx)
	if member != "member-state" || guild != "guild-state" || channel != "channel-state" || custom != "custom-state" {
		t.Fatalf("scoped states collided: %q %q %q %q", member, guild, channel, custom)
	}
	// Same user in a different guild is a different member key.
	other, _ := manager.Member("g2", "u1").GetState(ctx)
	if other != "" {
		t.Fatalf("member keys must be guild-scoped, got %q", other)
	}
}

func TestFSMSetStateEmptyClears(t *testing.T) {
	ctx := context.Background()
	fsm := NewFSMManager(nil).User("u")
	if err := fsm.SetState(ctx, "some-state"); err != nil {
		t.Fatal(err)
	}
	if err := fsm.SetState(ctx, ""); err != nil {
		t.Fatal(err)
	}
	if state, _ := fsm.GetState(ctx); state != "" {
		t.Fatalf("empty SetState should clear, got %q", state)
	}
}
