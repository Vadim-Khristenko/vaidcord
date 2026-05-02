package main

import (
	"context"

	"github.com/Vadim-Khristenko/vaidcord/vaidcord-go"
	"github.com/Vadim-Khristenko/vaidcord/vaidcord-go/examples/modular-with-deps/routers/admin"
)

func main() {
	dispatcher := vaidcord.NewDispatcher()
	dispatcher.Include(admin.Router(admin.Deps{OwnerID: "42"}))

	_ = dispatcher.Dispatch(context.Background(), vaidcord.Event{
		Type:    vaidcord.EventMessageCreate,
		Message: &vaidcord.Message{Content: "!admin", Author: vaidcord.User{ID: "42"}},
	})
}
