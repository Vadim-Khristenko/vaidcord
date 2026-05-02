package main

import (
	"context"
	"fmt"
	"os"

	"github.com/Vadim-Khristenko/vaidcord/vaidcord-go"
)

func main() {
	client := vaidcord.NewClient(vaidcord.Config{Token: os.Getenv("DISCORD_TOKEN")}, nil)
	user, err := client.GetCurrentUser(context.Background())
	if err != nil {
		panic(err)
	}
	fmt.Println(vaidcord.Bold(user.Username))
}
