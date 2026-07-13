# REST API Reference (Discord API v10)

`vaidcord.api_client.APIClient` is a typed facade over the internal
`HTTPClient`. Every helper returns the decoded JSON payload as a plain
`dict` (or `list`) for maximum forward compatibility; optional typed models
in `vaidcord.types` can upgrade payloads with `Model.from_payload(data)`.

```python
from vaidcord.api_client import APIClient

client = APIClient("BOT_TOKEN")
guild = await client.fetch_guild(1234)
await client.close()
```

Generic escape hatches are always available: `request`, `get`, `post`,
`patch`, `put`, `delete` accept any endpoint plus aiohttp kwargs
(`json=`, `params=`, `data=`, `headers=`).

## Audit log reasons

Helpers for endpoints that accept `X-Audit-Log-Reason` take a keyword-only
`reason: str | None = None`. The reason is URL-encoded automatically:

```python
await client.delete_guild_emoji(guild_id, emoji_id, reason="cleanup")
```

## File uploads (multipart/form-data)

`vaidcord.types.AttachmentFile` describes one upload (`filename`, `data`
as bytes or a binary file object, optional `description`, `spoiler`,
`content_type`). Pass `files=[...]` to any message-producing helper:

```python
from vaidcord.types import AttachmentFile

await client.send_message(
    channel_id,
    {"content": "look at this"},
    files=[AttachmentFile(filename="cat.png", data=png_bytes, content_type="image/png")],
)
```

The client builds an aiohttp `FormData` with a `payload_json` part and one
`files[n]` part per attachment, and extends the payload's `attachments`
array with descriptors (id, filename, description). Spoiler files get the
`SPOILER_` filename prefix. `files=` is supported on: `send_message`,
`edit_message`, `execute_webhook`, `edit_webhook_message`,
`create_interaction_response`, `create_followup_message`,
`edit_original_interaction_response`, `edit_followup_message`,
`start_thread_in_forum`. `create_guild_sticker` always uploads multipart.
The JSON-only path is unchanged when `files` is omitted.

## Resource coverage

### Messages
`send_message`, `list_messages`, `fetch_message`, `edit_message`,
`delete_message`, `bulk_delete_messages`, `crosspost_message`,
`add_reaction`, `delete_own_reaction`, `delete_user_reaction`,
`list_reactions`, `clear_reactions`, `clear_reaction`,
`get_poll_answer_voters`, `end_poll`.

### Pins & typing
`list_pins`, `get_channel_pins`, `pin_message`, `unpin_message`,
`pin_channel_message`, `unpin_channel_message`, `trigger_typing`.

### Channels
`fetch_channel`, `modify_channel`, `delete_channel`,
`list_channel_invites`, `create_channel_invite`,
`edit_channel_permissions`, `delete_channel_permission`,
`follow_news_channel`, `group_dm_add_recipient`,
`group_dm_remove_recipient`, `modify_guild_channel_positions`.

### Threads
`start_thread_from_message`, `start_thread_without_message`,
`start_thread_in_forum` (forum/media channels, message payload + files),
`join_thread`, `leave_thread`, `add_thread_member`, `remove_thread_member`,
`get_thread_member` (`with_member` support), `list_thread_members`
(`with_member`, `after`, `limit`), `list_public_archived_threads`,
`list_private_archived_threads`, `list_joined_private_archived_threads`,
`list_active_guild_threads` (GET /guilds/{id}/threads/active).

### Guilds
`create_guild`, `fetch_guild`, `fetch_guild_preview`, `modify_guild`,
`delete_guild`, `list_guild_channels`, `get_guild_prune_count`,
`begin_guild_prune`, `list_guild_voice_regions`,
`list_guild_integrations`, `delete_guild_integration`,
`get_guild_widget_settings`, `modify_guild_widget`, `get_guild_widget`
(widget.json), `guild_widget_image_url` (widget.png URL helper),
`get_guild_vanity_url`, `get_guild_welcome_screen`,
`modify_guild_welcome_screen`, `get_guild_onboarding`,
`modify_guild_onboarding`, `modify_guild_mfa_level`,
`get_guild_audit_log` (user_id/action_type/before/after/limit filters),
`bulk_guild_ban`.

### Members, roles & bans
`get_guild_member`, `list_guild_members`, `search_guild_members`,
`add_guild_member`, `modify_guild_member`, `modify_current_member`,
`remove_guild_member`, `add_guild_member_role`,
`remove_guild_member_role`, `ban_guild_member`, `unban_guild_member`,
`list_guild_bans`, `get_guild_ban`, `list_guild_roles`, `get_guild_role`,
`create_guild_role`, `modify_guild_role`, `modify_guild_role_positions`,
`delete_guild_role`.

### Emojis
Guild: `list_guild_emojis`, `get_guild_emoji`, `create_guild_emoji`,
`modify_guild_emoji`, `delete_guild_emoji`.
Application: `list_application_emojis`, `get_application_emoji`,
`create_application_emoji`, `modify_application_emoji`,
`delete_application_emoji`.

### Stickers
`get_sticker`, `list_sticker_packs`, `get_sticker_pack`,
`list_guild_stickers`, `get_guild_sticker`, `create_guild_sticker`
(multipart: name/description/tags/file), `modify_guild_sticker`,
`delete_guild_sticker`.

### Auto Moderation
`list_auto_moderation_rules`, `get_auto_moderation_rule`,
`create_auto_moderation_rule`, `modify_auto_moderation_rule`,
`delete_auto_moderation_rule`.

### Stage instances
`create_stage_instance`, `get_stage_instance`, `modify_stage_instance`,
`delete_stage_instance`.

### Scheduled events
`list_scheduled_events`, `create_scheduled_event`,
`fetch_scheduled_event`, `modify_scheduled_event`,
`delete_scheduled_event`, `get_scheduled_event_users`
(limit/with_member/before/after pagination).

### Entitlements & monetization
`list_entitlements`, `get_entitlement`, `consume_entitlement`,
`create_test_entitlement`, `delete_test_entitlement`, `list_skus`,
`list_sku_subscriptions`, `get_sku_subscription`.

### Soundboard
`list_default_soundboard_sounds`, `list_guild_soundboard_sounds`,
`get_guild_soundboard_sound`, `create_guild_soundboard_sound`,
`modify_guild_soundboard_sound`, `delete_guild_soundboard_sound`,
`send_soundboard_sound` (POST /channels/{id}/send-soundboard-sound).

### Voice
`list_voice_regions` (GET /voice/regions),
`get_current_user_voice_state`, `get_user_voice_state`,
`modify_current_user_voice_state`, `modify_user_voice_state`.

### Users & DMs
`fetch_user`, `get_current_user`, `modify_current_user`,
`get_current_user_guilds`, `get_current_user_guild_member`, `leave_guild`,
`create_dm`, `create_group_dm`, `get_current_user_connections`,
`get_current_user_application_role_connection`,
`update_current_user_application_role_connection`.

### Invites
`fetch_invite`, `delete_invite`.

### Webhooks
`create_webhook`, `list_channel_webhooks`, `list_guild_webhooks`,
`fetch_webhook`, `modify_webhook`, `delete_webhook_resource`,
`execute_webhook`, `fetch_webhook_message`, `edit_webhook_message`,
`delete_webhook_message`.

### Application commands
Global: `list_global_commands`, `create_global_command`,
`fetch_global_command`, `edit_global_command`, `delete_global_command`,
`bulk_overwrite_global_commands`.
Guild: `list_guild_commands`, `create_guild_command`,
`fetch_guild_command`, `edit_guild_command`, `delete_guild_command`,
`bulk_overwrite_guild_commands`.
Permissions: `get_guild_command_permissions`,
`get_application_command_permissions`,
`edit_application_command_permissions`,
`batch_edit_application_command_permissions`.

### Interactions
`create_interaction_response`, `get_original_interaction_response`,
`edit_original_interaction_response`,
`delete_original_interaction_response`, `create_followup_message`,
`edit_followup_message`, `delete_followup_message`.

### Application resource
`get_current_application`, `edit_current_application`,
`get_application_role_connection_metadata`,
`update_application_role_connection_metadata`.

## Typed models (`vaidcord.types`)

Frozen, slotted dataclasses with a `raw_data` field and a tolerant
`from_payload(data)` classmethod:

`Role`, `Member`, `Emoji`, `Sticker`, `StickerPack`, `Attachment`,
`Embed` (+ mutable fluent `EmbedBuilder`), `Webhook`, `Invite`,
`ThreadMember`, `StageInstance`, `AutoModerationRule`,
`GuildScheduledEvent`, `Entitlement`, `SKU`, `Subscription`,
`SoundboardSound`, `AuditLogEntry`, `AuditLog`, `VoiceRegion`,
`Application`, `Integration`, `WelcomeScreen`, `Poll`, `PollAnswer`,
and the upload helper `AttachmentFile`.

```python
from vaidcord.types import Role

payload = await client.get_guild_role(guild_id, role_id)
role = Role.from_payload(payload)
print(role.mention)
```

Snowflake fields are coerced to `int`; unknown/extra keys remain available
via `model.raw_data`.
