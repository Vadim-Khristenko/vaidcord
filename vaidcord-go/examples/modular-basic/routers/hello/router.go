package hello

import (
	"context"
	"fmt"

	"github.com/Vadim-Khristenko/vaidcord/vaidcord-go"
)

func Router() *vaidcord.Router {
	router := vaidcord.NewRouter("hello")

	router.OnReady().Handle(func(_ context.Context, ready vaidcord.ReadyEvent) error {
		fmt.Println("ready as", ready.User.Username)
		return nil
	})
	router.OnMessageCreate(vaidcord.ContentStartsWith("!start")).Handle(start)

	return router
}

func start(_ context.Context, message vaidcord.Message) error {
	fmt.Println("start from", message.Author.Username)
	return nil
}
