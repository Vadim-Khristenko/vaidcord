# VaidCord Go

The Go SDK for VaidCord. Single package `vaidcord`, two external
dependencies (`gorilla/websocket`, `golang.org/x/crypto`).

Feature surface:

- **Bot facade** — `NewBot` owns the gateway + REST client, parses dispatches
  into typed events and feeds the router pipeline.
- **Robust gateway** — heartbeats on their own goroutine (interval from
  HELLO), heartbeat-ACK tracking with automatic reconnect on missed ACKs,
  session RESUME (`session_id` + `resume_gateway_url` + `seq`), exponential
  backoff, close-code policy (fatal vs resumable vs re-identify per the
  Discord docs), typed `Intents` constants, op 3 presence updates, op 8
  guild-member requests, op 4 voice state updates.
- **Rate-limited REST client** — per-route buckets from `X-RateLimit-*`
  headers, sleep-and-retry on 429 (`retry_after`, global windows), retries
  with backoff on 5xx/network errors, context support on every method.
  Endpoints: messages (send/edit/delete/reactions), channels
  (get/modify/delete), guilds (get/channels/roles/members), interactions
  (responses/followups), webhooks (execute), threads (create/join/leave),
  application commands (list/bulk overwrite).
- **Voice transport** — voice gateway v8 client (identify/resume with
  `seq_ack`, READY, session description, heartbeat ACK tracking), UDP socket
  with 74-byte IP discovery, RTP packet builder/parser, transport encryption
  for `aead_aes256_gcm_rtpsize`, `aead_xchacha20_poly1305_rtpsize` and
  `xsalsa20_poly1305_lite_rtpsize` in both directions (wire-compatible with
  the Python SDK, verified by shared known-answer vectors), drift-corrected
  20 ms pacing, speaking payloads, SSRC→user mapping from op 5/12/13, an
  `AudioSource` interface for opus passthrough, an ffmpeg-pipe source with a
  pure-Go Ogg demuxer, and a receive path decrypting inbound RTP to
  `(userID, opusPacket)`.
- **Routers, filters, middleware** — nested routers, AND-composed filters,
  precomputed middleware chains, fluent builders, typed handlers for
  messages, ready, interactions.
- **Models** — `User`, `Channel`, `Message`, `Guild`, `Role`, `Member`,
  `Embed`, `Interaction` (+ responses), with `Event.Raw` as the escape hatch.
- **FSM** — minimal finite-state machine (`FSMManager`, `FSMContext`,
  `MemoryFSMStorage`) with user/channel/guild/member/custom scopes,
  mirroring the Python `fsm` package concepts.

## Quick start

```go
bot := vaidcord.NewBot(vaidcord.BotConfig{
    Config:  vaidcord.Config{Token: os.Getenv("DISCORD_TOKEN")},
    Intents: vaidcord.IntentsDefault | vaidcord.IntentMessageContent,
})

router := vaidcord.NewRouter("hello")
router.
    OnMessageCreate(vaidcord.ContentStartsWith("!"), vaidcord.Command("ping")).
    Handle(func(ctx context.Context, msg vaidcord.Message) error {
        _, err := bot.API().SendMessage(ctx, msg.ChannelID, vaidcord.MessagePayload{Content: "pong"})
        return err
    })

bot.Include(router)
if err := bot.Run(ctx); err != nil {
    log.Fatal(err)
}
```

The lower-level pieces remain available — `NewClient` for bare REST,
`NewGateway` for a raw dispatch stream, and
`Dispatcher.StartPolling(ctx, client, vaidcord.WithIntents(...))` when you
already own a `*Client`.

## REST client

```go
client := vaidcord.NewClient(vaidcord.Config{Token: "BOT_TOKEN"}, nil)
msg, err := client.SendMessage(ctx, channelID, vaidcord.MessagePayload{Content: "pong"})
err = client.CreateReaction(ctx, channelID, msg.ID, "👍")
thread, err := client.StartThreadWithMessage(ctx, channelID, msg.ID, vaidcord.ThreadPayload{Name: "discussion"})
err = client.CreateInteractionResponse(ctx, interaction.ID, interaction.Token, vaidcord.InteractionResponse{
    Type: vaidcord.InteractionResponseChannelMessageWithSource,
    Data: &vaidcord.InteractionResponseData{Content: "hi"},
})
```

429s, 5xx responses and transient network errors are retried automatically
(`Config.MaxRetries`, default 3); per-route buckets from `X-RateLimit-*`
headers keep the client from hitting limits in the first place.

## Voice

```go
conn := vaidcord.NewVoiceConnection(vaidcord.VoiceServerInfo{
    GuildID:   guildID,
    UserID:    botUserID,
    SessionID: voiceStateSessionID, // from VOICE_STATE_UPDATE
    Token:     voiceServerToken,    // from VOICE_SERVER_UPDATE
    Endpoint:  voiceServerEndpoint, // from VOICE_SERVER_UPDATE
}, vaidcord.VoiceGatewayConfig{})

if err := conn.Connect(ctx); err != nil { ... }

// Play: ffmpeg decodes/encodes, Go demuxes Ogg pages and paces 20ms frames.
source, _ := vaidcord.NewFFmpegOpusSource(ctx, "song.mp3")
_ = conn.Play(ctx, source)

// Listen: decrypted inbound RTP as (userID, opus).
_ = conn.Listen(ctx, func(frame vaidcord.VoiceFrame) {
    fmt.Println(frame.UserID, len(frame.Opus))
})
```

Use `bot.Gateway().UpdateVoiceState(guildID, channelID, false, false)` to
request the join and collect `VOICE_STATE_UPDATE`/`VOICE_SERVER_UPDATE` from
the dispatch stream.

The wire format is identical across the Python/Rust/Go SDKs:
`RTP prefix || ciphertext || 4-byte big-endian nonce counter`, AEAD nonce =
counter zero-padded, AAD = unencrypted RTP prefix. `go test` pins
known-answer vectors generated by `vaidcord-py` to keep the SDKs
byte-compatible. DAVE/E2EE opcode + close-code constants are exposed
(`VoiceOpDave*`, close 4017 is fatal); a Go MLS backend is not shipped yet.

## Examples

| Example | Shows |
|---|---|
| `examples/bot-run` | `Bot` facade: gateway + REST + routers |
| `examples/voice-transport` | offline voice packet seal/open, IP discovery |
| `examples/basic` | bare REST client |
| `examples/router` | router + filters |
| `examples/router-middleware` | middleware composition |
| `examples/modular-basic`, `examples/modular-with-deps` | multi-router apps |

## Testing

```bash
go test ./...
```

The suite covers gateway close-code policy, RESUME/IDENTIFY flows and
heartbeat behaviour against a scripted websocket server; rate-limit buckets
against a mock `RoundTripper`; voice crypto seal/open round-trips, tamper
rejection and Python wire-compat vectors; RTP parsing; IP discovery; the
full voice handshake against a scripted voice gateway + local UDP socket;
Ogg demuxing (plus live ffmpeg tests when `ffmpeg` is on `PATH`); and the
FSM storage.
