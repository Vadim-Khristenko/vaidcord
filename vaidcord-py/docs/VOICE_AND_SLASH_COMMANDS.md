# Voice API and Slash Commands

This guide covers:

1. What the new Voice API provides
2. How to stream/play audio
3. How slash commands work
4. Difference between slash commands and `on_message`
5. What `command_dev_guild_id` is and when to use it

## Voice API: what is implemented

VaidCord now includes a practical voice connection layer:

- voice join coordination (`VOICE_STATE_UPDATE` + `VOICE_SERVER_UPDATE`)
- voice websocket identify/resume
- UDP IP discovery
- protocol selection
- speaking state control
- RTP packet builder
- frame streaming helpers
- dependency diagnostics for audio/encryption backends
- DAVE/E2EE controller integration with pluggable crypto backend hooks

Voice gateway version:

- VaidCord uses Voice Gateway **v8** (`?v=8`) and sends `seq_ack` in heartbeats/resume payloads.

Main types:

- `VoiceManager`
- `VoiceConnection`
- `VoiceUDPClient`
- `VoiceGatewayConfig`
- `AudioBackendStatus`
- `DaveProtocolController`
- `DaveCryptoBackend`

## Voice connection flow

Typical flow:

1. `await bot.join_voice_channel(...)`
2. Wait for voice state/server events
3. Voice WS identify
4. Receive `READY`
5. UDP connect + IP discovery
6. `Select Protocol`
7. Receive session description
8. Start sending frames (`stream_audio` / `play_file`)

## Audio streaming and file playback

`VoiceConnection` has high-level helpers:

- `start_speaking()`
- `stop_speaking()`
- `send_audio_frame(payload: bytes, ...)`
- `stream_audio(frames: AsyncIterator[bytes], ...)`
- `play_file(path: str, ...)`
- `send_silence_frames(...)`

`play_file(...)` decodes common file formats through `ffmpeg`, encodes PCM into Opus frames with `opuslib`, sends encrypted RTP packets, and returns the number of Opus frames sent. If a file produces zero frames, it raises an explicit audio backend error.

For real playback install voice extras:

```bash
uv add "vaidcord[voice]"
```

This enables:

- Opus encoding pipeline (`ffmpeg` PCM decode -> Opus frames)
- transport encryption (`aead_xchacha20_poly1305_rtpsize` / `aead_aes256_gcm_rtpsize`)

Important:

- `ffmpeg` must be available in `PATH`
- voice extras require `PyNaCl`, `cryptography`, and `opuslib`

Before joining voice you can check the local stack:

```python
from vaidcord.voice import check_voice_dependencies

status = check_voice_dependencies()
status.raise_for_playback()
print(status)
```

## Full example: play file in a voice channel

See runnable example:

- [examples/voice_showcase.py](../examples/voice_showcase.py)

Key pattern:

```python
connection = await bot.join_voice_channel(guild_id=..., channel_id=...)
await connection.play_file("examples/assets/Anamanaguchi_Miku-Ft_Hatsune_Miku.mp3", chunk_size=3840, frame_duration_ms=20)
```

Recommended lifecycle:

- join voice
- play stream/file
- optionally send a silence tail (`send_silence_frames`) before stop
- `await connection.close()`

Included demo asset:

- `examples/assets/Anamanaguchi_Miku-Ft_Hatsune_Miku.mp3`

## Slash commands: how they work

VaidCord provides decorator-based registration:

- `@bot.slash_command(...)`
- `@bot.user_command(...)`
- `@bot.message_command(...)`

Handlers for slash commands receive `CommandContext` with helpers:

- `ctx.options`
- `ctx.option_str/int/float/bool(...)`
- `ctx.require_str/int/float/bool(...)`

Example:

```python
@bot.slash_command(
    name="echo",
    description="Echo text back",
    options=[{"name": "text", "description": "Message", "type": 3, "required": True}],
)
async def echo(ctx) -> None:
    text = ctx.require_str("text")
    await bot.create_interaction_response(
        int(ctx["id"]),
        ctx["token"],
        type=4,
        data={"content": text},
    )
```

See runnable example:

- [examples/slash_commands.py](../examples/slash_commands.py)

## Slash commands vs `on_message`

`on_message`:

- reacts to plain text messages
- depends on gateway message events and intents
- command parsing is your responsibility (or message filters)

Slash commands:

- are explicit Discord application commands
- appear in Discord UI command picker
- arguments arrive as structured options
- better UX and clearer permissions/discovery

Use `on_message` for free-form chat flows.
Use slash commands for stable, discoverable command interfaces.

## `command_dev_guild_id` (dev guild sync)

`BotConfig.command_dev_guild_id` lets you sync otherwise-global commands into one guild for fast iteration:

- faster propagation than global command rollout
- safer for staging/testing
- avoids noisy global updates while developing

Example:

```python
bot = Bot(config=BotConfig(token="...", command_dev_guild_id=123456789012345678))
```

When set, commands without explicit `guild_id` are synced to that guild during command sync.

Related sync controls in `BotConfig`:

- `command_sync_mode="replace"` (default): overwrite list in target scope
- `command_sync_mode="merge"`: keep existing commands and upsert only VaidCord-registered ones
- `command_sync_guild_ids=(...)`: explicit guild scopes that should be synced (and cleaned in replace mode)

The decorators also expose modern Discord command fields:

- `name_localizations`
- `description_localizations`
- `integration_types`
- `contexts`
- `nsfw`

User and message commands intentionally do not send a `description` field.

## Components V2

VaidCord includes native builders for Discord Components V2:

```python
from vaidcord import (
    ButtonStyle,
    action_row,
    button,
    components_v2_message,
    text_display,
)

payload = components_v2_message(
    [
        text_display("# Playback ready"),
        action_row([button(style=ButtonStyle.PRIMARY, custom_id="play", label="Play")]),
    ]
)
await bot.send_message(channel_id=123, components=payload["components"], flags=payload["flags"])
```

Available builders cover message layout/content components (`container`, `section`, `separator`, `thumbnail`, `media_gallery`, `file_component`) and modal/input components (`label`, `text_input`, `select_menu`, `checkbox`).

## Recommended production strategy

1. Develop with `command_dev_guild_id`
2. Validate command behavior in dev guild
3. Move stable commands to global scope (or explicit guild scopes)
4. Keep voice playback logic separated from command handlers (service layer)

## Current limits (important)

Current voice helpers provide handshake, RTP transport, file decoding, Opus encoding, AEAD transport encryption, and a DAVE controller that can drive a configured `DaveCryptoBackend`. Channels that require Discord DAVE/E2EE still need a production MLS/libdave-compatible backend implementation; without one, VaidCord detects the DAVE path and fails fast with actionable diagnostics instead of silently closing.
