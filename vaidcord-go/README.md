# VaidCord Go

Early Go SDK scaffold for VaidCord.

Status: **scaffold only**. The first committed surface is intentionally small:

- module metadata
- package constants
- config defaults for Discord API v10
- `net/http` client with JSON request/response handling
- typed Discord API errors
- first REST helpers: `GetCurrentUser`, `FetchChannel`, `SendMessage`

```go
client := vaidcord.NewClient(vaidcord.Config{Token: "BOT_TOKEN"}, nil)
user, err := client.GetCurrentUser(context.Background())
message, err := client.SendMessage(
    context.Background(),
    "123456789012345678",
    vaidcord.MessagePayload{Content: "pong"},
)
```

Next steps:

- richer REST resources and typed models
- gateway identify/heartbeat loop
- message/channel/user models
- router and filter primitives compatible with the Python SDK mental model
