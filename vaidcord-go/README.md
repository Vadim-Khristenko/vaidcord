# VaidCord Go

Early Go SDK scaffold for VaidCord.

Status: **scaffold only**. The first committed surface is intentionally small:

- module metadata
- package constants
- config defaults for Discord API v10
- optional HTTP proxy configuration
- `net/http` client with JSON request/response handling
- typed Discord API errors
- typed `User`, `Channel`, and `Message` response models
- first REST helpers: `GetCurrentUser`, `FetchChannel`, `SendMessage`
- formatter helpers for Discord markdown and mentions
- first router primitives: `NewRouter`, `OnMessage`, message filters

```go
client := vaidcord.NewClient(vaidcord.Config{Token: "BOT_TOKEN"}, nil)
user, err := client.GetCurrentUser(context.Background())
message, err := client.SendMessage(
    context.Background(),
    "123456789012345678",
    vaidcord.MessagePayload{Content: "pong"},
)
```

```go
client := vaidcord.NewClient(vaidcord.Config{
    Token: "BOT_TOKEN",
    ProxyURL: "http://127.0.0.1:8080",
}, nil)
```

```go
router := vaidcord.NewRouter()
router.Message(vaidcord.ContentStartsWith("!ping")).Handle(func(ctx context.Context, message vaidcord.Message) error {
    fmt.Println(vaidcord.Bold(message.Content))
    return nil
})

if err := <-router.DispatchMessageAsync(context.Background(), message); err != nil {
    panic(err)
}
```

Runnable examples live in `examples/basic` and `examples/router`.

Next steps:

- richer REST resources
- gateway identify/heartbeat loop
- richer router and filter primitives compatible with the Python SDK mental model
