package main

import (
	"context"
	"fmt"

	"github.com/Vadim-Khristenko/vaidcord/vaidcord-go"
)

func main() {
	router := vaidcord.NewRouter()

	router.OnMessage(func(_ context.Context, message vaidcord.Message) error {
		fmt.Println(vaidcord.InlineCode(message.Content))
		return nil
	}, vaidcord.ContentStartsWith("!ping"))

	_ = router.DispatchMessage(context.Background(), vaidcord.Message{
		Content: "!ping",
		Author:  vaidcord.User{ID: "42", Username: "tester"},
	})
}
