package vaidcord

import (
	"context"
	"testing"
)

func TestRouterDispatchMessage(t *testing.T) {
	router := NewRouter()
	calls := 0

	router.OnMessage(func(_ context.Context, message Message) error {
		calls++
		if message.Content != "!ping" {
			t.Fatalf("unexpected message: %#v", message)
		}
		return nil
	}, ContentStartsWith("!"))

	err := router.DispatchMessage(context.Background(), Message{Content: "!ping"})
	if err != nil {
		t.Fatal(err)
	}
	err = router.DispatchMessage(context.Background(), Message{Content: "plain"})
	if err != nil {
		t.Fatal(err)
	}
	if calls != 1 {
		t.Fatalf("unexpected handler calls: %d", calls)
	}
}
