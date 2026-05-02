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

func TestDispatcherIncludesMultipleRouters(t *testing.T) {
	hello := NewRouter("hello")
	admin := NewRouter("admin")
	calls := []string{}

	hello.OnMessageCreate(ContentStartsWith("hello")).Handle(func(context.Context, Message) error {
		calls = append(calls, "hello")
		return nil
	})
	admin.OnMessageCreate(ContentStartsWith("admin")).Handle(func(context.Context, Message) error {
		calls = append(calls, "admin")
		return nil
	})

	dispatcher := NewDispatcher()
	dispatcher.Include(hello, admin)

	if err := dispatcher.Dispatch(context.Background(), Event{Type: EventMessageCreate, Message: &Message{Content: "admin now"}}); err != nil {
		t.Fatal(err)
	}
	if len(calls) != 1 || calls[0] != "admin" {
		t.Fatalf("unexpected calls: %#v", calls)
	}
}

func TestDispatcherIncludesNestedRoutersAndMiddleware(t *testing.T) {
	parent := NewRouter("parent")
	child := NewRouter("child")
	calls := []string{}

	parent.Use(func(ctx context.Context, event Event, next Handler) error {
		calls = append(calls, "mw")
		return next(ctx, event)
	})
	child.OnMessageCreate(ContentStartsWith("!")).Handle(func(context.Context, Message) error {
		calls = append(calls, "handler")
		return nil
	})
	parent.Include(child)

	dispatcher := NewDispatcher()
	dispatcher.Include(parent)

	if err := dispatcher.Dispatch(context.Background(), Event{Type: EventMessageCreate, Message: &Message{Content: "!ping"}}); err != nil {
		t.Fatal(err)
	}
	if len(calls) != 2 || calls[0] != "mw" || calls[1] != "handler" {
		t.Fatalf("unexpected calls: %#v", calls)
	}
}

func TestDispatcherErrorHandlerReceivesHandlerErrors(t *testing.T) {
	router := NewRouter("errors")
	expected := errors.New("failed")
	var got error
	var gotMeta EventMeta

	router.OnMessageCreate().Name("broken").Handle(func(context.Context, Message) error {
		return expected
	})
	dispatcher := NewDispatcher(WithErrorHandler(func(_ context.Context, meta EventMeta, err error) {
		gotMeta = meta
		got = err
	}))
	dispatcher.Include(router)

	err := dispatcher.Dispatch(context.Background(), Event{Type: EventMessageCreate, Message: &Message{}})
	if !errors.Is(err, expected) || !errors.Is(got, expected) {
		t.Fatalf("expected propagated error, got dispatch=%v handler=%v", err, got)
	}
	if gotMeta.Router != "errors" || gotMeta.Route != "broken" {
		t.Fatalf("unexpected meta: %#v", gotMeta)
	}
}
