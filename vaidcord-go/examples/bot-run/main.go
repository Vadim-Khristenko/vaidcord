// Example bot-run: the high-level Bot facade.
//
// The Bot owns the gateway connection (heartbeats, RESUME, reconnect with
// backoff) and the rate-limited REST client. Routers plug in exactly like
// they do with the bare Dispatcher.
//
//	DISCORD_TOKEN=... go run ./examples/bot-run
package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	vaidcord "github.com/Vadim-Khristenko/vaidcord/vaidcord-go"
)

func main() {
	token := os.Getenv("DISCORD_TOKEN")
	if token == "" {
		log.Fatal("set DISCORD_TOKEN")
	}

	bot := vaidcord.NewBot(vaidcord.BotConfig{
		Config:  vaidcord.Config{Token: token},
		Intents: vaidcord.IntentsDefault | vaidcord.IntentMessageContent,
		Presence: &vaidcord.PresenceUpdate{
			Status:     "online",
			Activities: []vaidcord.Activity{{Name: "vaidcord-go", Type: 0}},
		},
	})

	router := vaidcord.NewRouter("hello")

	router.OnReady().Handle(func(ctx context.Context, ready vaidcord.ReadyEvent) error {
		log.Printf("logged in as %s (session %s)", ready.User.Username, ready.SessionID)
		return nil
	})

	router.
		OnMessageCreate(vaidcord.Command("ping")).
		Handle(func(ctx context.Context, msg vaidcord.Message) error {
			_, err := bot.API().SendMessage(ctx, msg.ChannelID, vaidcord.MessagePayload{
				Content:    "pong!",
				MessageRef: &vaidcord.MessageReference{MessageID: msg.ID},
			})
			return err
		})

	router.
		OnInteractionCreate(vaidcord.SlashCommand("ping")).
		Handle(func(ctx context.Context, interaction vaidcord.Interaction) error {
			return bot.API().CreateInteractionResponse(ctx, interaction.ID, interaction.Token,
				vaidcord.InteractionResponse{
					Type: vaidcord.InteractionResponseChannelMessageWithSource,
					Data: &vaidcord.InteractionResponseData{Content: "pong (slash)!"},
				})
		})

	bot.Include(router)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	if err := bot.Run(ctx); err != nil && ctx.Err() == nil {
		log.Fatalf("bot stopped: %v", err)
	}
}
