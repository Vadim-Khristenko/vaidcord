package vaidcord

import (
	"context"
	"errors"
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

func TestRouterFluentMessageBuilder(t *testing.T) {
	router := NewRouter()
	calls := 0

	router.Message(ContentStartsWith("!")).Use(AuthorID("42")).Handle(
		func(_ context.Context, message Message) error {
			calls++
			if message.Content != "!ping" {
				t.Fatalf("unexpected message: %#v", message)
			}
			return nil
		},
	)

	err := router.DispatchMessage(context.Background(), Message{
		Content: "!ping",
		Author:  User{ID: "42"},
	})
	if err != nil {
		t.Fatal(err)
	}
	err = router.DispatchMessage(context.Background(), Message{
		Content: "!ping",
		Author:  User{ID: "7"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if calls != 1 {
		t.Fatalf("unexpected handler calls: %d", calls)
	}
}

func TestRouterDispatchMessageAsyncReturnsErrors(t *testing.T) {
	router := NewRouter()
	expected := errors.New("handler failed")
	router.Message().Handle(func(context.Context, Message) error {
		return expected
	})

	err := <-router.DispatchMessageAsync(context.Background(), Message{})
	if !errors.Is(err, expected) {
		t.Fatalf("unexpected async error: %v", err)
	}
}

func TestRouterRecoversHandlerPanic(t *testing.T) {
	router := NewRouter()
	router.Message().Handle(func(context.Context, Message) error {
		panic("boom")
	})

	err := router.DispatchMessage(context.Background(), Message{})
	if err == nil {
		t.Fatal("expected recovered panic error")
	}
}
