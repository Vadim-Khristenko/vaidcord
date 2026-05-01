# VaidCord Go

Early Go SDK scaffold for VaidCord.

Status: **scaffold only**. The first committed surface is intentionally small:

- module metadata
- package constants
- config defaults for Discord API v10

```go
cfg := vaidcord.Config{Token: "BOT_TOKEN"}.WithDefaults()
```

Next steps:

- HTTP client with Discord-aware headers and error mapping
- gateway identify/heartbeat loop
- message/channel/user models
- router and filter primitives compatible with the Python SDK mental model
