# VaidCord Go

Early Go SDK scaffold for VaidCord.

Status: **scaffold only**. The first committed surface is intentionally small:

- module metadata
- package constants
- config defaults for Discord API v10
- minimal `net/http` client for JSON GET requests

```go
client := vaidcord.NewClient(vaidcord.Config{Token: "BOT_TOKEN"}, nil)
user, err := client.GetCurrentUser(context.Background())
```

Next steps:

- richer REST resources and typed models
- Discord-aware error mapping
- gateway identify/heartbeat loop
- message/channel/user models
- router and filter primitives compatible with the Python SDK mental model
