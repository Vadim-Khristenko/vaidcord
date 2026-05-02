package main

import (
	"context"
	"fmt"

	"github.com/Vadim-Khristenko/vaidcord/vaidcord-go"
)

func main() {
	router := vaidcord.NewRouter("with-middleware")
	router.Use(func(ctx context.Context, event vaidcord.Event, next vaidcord.Handler) error {
		fmt.Println("before", event.Type)
		err := next(ctx, event)
		fmt.Println("after", event.Type)
		return err
	})
	router.OnMessageCreate(vaidcord.ContentStartsWith("!ping")).Handle(func(_ context.Context, message vaidcord.Message) error {
		fmt.Println("handler", message.Content)
		return nil
	})

	dispatcher := vaidcord.NewDispatcher()
	dispatcher.Include(router)
	_ = dispatcher.Dispatch(context.Background(), vaidcord.Event{
		Type:    vaidcord.EventMessageCreate,
		Message: &vaidcord.Message{Content: "!ping"},
	})
}
