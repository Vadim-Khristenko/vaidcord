package main

import (
	"context"

	"github.com/Vadim-Khristenko/vaidcord/vaidcord-go"
	"github.com/Vadim-Khristenko/vaidcord/vaidcord-go/examples/modular-basic/routers/hello"
)

func main() {
	dispatcher := vaidcord.NewDispatcher()
	dispatcher.Include(hello.Router())

	_ = dispatcher.Dispatch(context.Background(), vaidcord.Event{
		Type:    vaidcord.EventMessageCreate,
		Message: &vaidcord.Message{Content: "!start", Author: vaidcord.User{Username: "tester"}},
	})
}
