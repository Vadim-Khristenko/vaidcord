"""Route coverage tests for the Discord API v10 parity helpers on APIClient."""

from __future__ import annotations

from typing import Any

import pytest

from vaidcord.api_client import APIClient


@pytest.fixture()
def client_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[APIClient, list[tuple[str, str, dict[str, Any]]]]:
    client = APIClient("token")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_request(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((method, endpoint, kwargs))
        return {"ok": True}

    monkeypatch.setattr(client, "request", fake_request)
    return client, calls


def _reason(value: str) -> dict[str, dict[str, str]]:
    return {"headers": {"X-Audit-Log-Reason": value}}


@pytest.mark.asyncio
async def test_emoji_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.get_guild_emoji(9, 1)
    await client.create_guild_emoji(9, {"name": "wave"}, reason="new emoji")
    await client.modify_guild_emoji(9, 1, {"name": "waves"})
    await client.delete_guild_emoji(9, 1, reason="cleanup")
    await client.list_application_emojis(5)
    await client.get_application_emoji(5, 2)
    await client.create_application_emoji(5, {"name": "app"})
    await client.modify_application_emoji(5, 2, {"name": "app2"})
    await client.delete_application_emoji(5, 2)

    assert calls == [
        ("GET", "/guilds/9/emojis/1", {}),
        ("POST", "/guilds/9/emojis", {"json": {"name": "wave"}, **_reason("new emoji")}),
        ("PATCH", "/guilds/9/emojis/1", {"json": {"name": "waves"}}),
        ("DELETE", "/guilds/9/emojis/1", _reason("cleanup")),
        ("GET", "/applications/5/emojis", {}),
        ("GET", "/applications/5/emojis/2", {}),
        ("POST", "/applications/5/emojis", {"json": {"name": "app"}}),
        ("PATCH", "/applications/5/emojis/2", {"json": {"name": "app2"}}),
        ("DELETE", "/applications/5/emojis/2", {}),
    ]


@pytest.mark.asyncio
async def test_sticker_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.get_sticker(3)
    await client.list_sticker_packs()
    await client.get_sticker_pack(4)
    await client.get_guild_sticker(9, 3)
    await client.modify_guild_sticker(9, 3, {"name": "s"}, reason="rename")
    await client.delete_guild_sticker(9, 3)

    assert calls == [
        ("GET", "/stickers/3", {}),
        ("GET", "/sticker-packs", {}),
        ("GET", "/sticker-packs/4", {}),
        ("GET", "/guilds/9/stickers/3", {}),
        ("PATCH", "/guilds/9/stickers/3", {"json": {"name": "s"}, **_reason("rename")}),
        ("DELETE", "/guilds/9/stickers/3", {}),
    ]


@pytest.mark.asyncio
async def test_auto_moderation_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.list_auto_moderation_rules(9)
    await client.get_auto_moderation_rule(9, 2)
    await client.create_auto_moderation_rule(9, {"name": "no spam"}, reason="setup")
    await client.modify_auto_moderation_rule(9, 2, {"enabled": True})
    await client.delete_auto_moderation_rule(9, 2, reason="obsolete")

    assert calls == [
        ("GET", "/guilds/9/auto-moderation/rules", {}),
        ("GET", "/guilds/9/auto-moderation/rules/2", {}),
        (
            "POST",
            "/guilds/9/auto-moderation/rules",
            {"json": {"name": "no spam"}, **_reason("setup")},
        ),
        ("PATCH", "/guilds/9/auto-moderation/rules/2", {"json": {"enabled": True}}),
        ("DELETE", "/guilds/9/auto-moderation/rules/2", _reason("obsolete")),
    ]


@pytest.mark.asyncio
async def test_stage_instance_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.create_stage_instance({"channel_id": "1", "topic": "talk"}, reason="show")
    await client.get_stage_instance(1)
    await client.modify_stage_instance(1, {"topic": "talk 2"})
    await client.delete_stage_instance(1, reason="done")

    assert calls == [
        (
            "POST",
            "/stage-instances",
            {"json": {"channel_id": "1", "topic": "talk"}, **_reason("show")},
        ),
        ("GET", "/stage-instances/1", {}),
        ("PATCH", "/stage-instances/1", {"json": {"topic": "talk 2"}}),
        ("DELETE", "/stage-instances/1", _reason("done")),
    ]


@pytest.mark.asyncio
async def test_entitlement_and_monetization_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.list_entitlements(5, user_id=8, limit=3)
    await client.get_entitlement(5, 11)
    await client.consume_entitlement(5, 11)
    await client.create_test_entitlement(5, {"sku_id": "2", "owner_id": "8", "owner_type": 2})
    await client.delete_test_entitlement(5, 11)
    await client.list_skus(5)
    await client.list_sku_subscriptions(2, limit=3)
    await client.get_sku_subscription(2, 7)

    assert calls == [
        ("GET", "/applications/5/entitlements", {"params": {"user_id": 8, "limit": 3}}),
        ("GET", "/applications/5/entitlements/11", {}),
        ("POST", "/applications/5/entitlements/11/consume", {}),
        (
            "POST",
            "/applications/5/entitlements",
            {"json": {"sku_id": "2", "owner_id": "8", "owner_type": 2}},
        ),
        ("DELETE", "/applications/5/entitlements/11", {}),
        ("GET", "/applications/5/skus", {}),
        ("GET", "/skus/2/subscriptions", {"params": {"limit": 3}}),
        ("GET", "/skus/2/subscriptions/7", {}),
    ]


@pytest.mark.asyncio
async def test_soundboard_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.list_default_soundboard_sounds()
    await client.list_guild_soundboard_sounds(9)
    await client.get_guild_soundboard_sound(9, 4)
    await client.create_guild_soundboard_sound(9, {"name": "boing"}, reason="fun")
    await client.modify_guild_soundboard_sound(9, 4, {"volume": 0.5})
    await client.delete_guild_soundboard_sound(9, 4, reason="less fun")
    await client.send_soundboard_sound(1, 4, source_guild_id=9)
    await client.send_soundboard_sound(1, 4)

    assert calls == [
        ("GET", "/soundboard-default-sounds", {}),
        ("GET", "/guilds/9/soundboard-sounds", {}),
        ("GET", "/guilds/9/soundboard-sounds/4", {}),
        ("POST", "/guilds/9/soundboard-sounds", {"json": {"name": "boing"}, **_reason("fun")}),
        ("PATCH", "/guilds/9/soundboard-sounds/4", {"json": {"volume": 0.5}}),
        ("DELETE", "/guilds/9/soundboard-sounds/4", _reason("less fun")),
        (
            "POST",
            "/channels/1/send-soundboard-sound",
            {"json": {"sound_id": "4", "source_guild_id": "9"}},
        ),
        ("POST", "/channels/1/send-soundboard-sound", {"json": {"sound_id": "4"}}),
    ]


@pytest.mark.asyncio
async def test_guild_lifecycle_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.create_guild({"name": "New Guild"})
    await client.modify_guild(9, {"name": "Renamed"}, reason="rebrand")
    await client.delete_guild(9)
    await client.get_guild_prune_count(9, days=7)
    await client.begin_guild_prune(9, {"days": 7, "compute_prune_count": False}, reason="prune")
    await client.list_guild_voice_regions(9)
    await client.list_guild_integrations(9)
    await client.delete_guild_integration(9, 3, reason="bye")
    await client.get_guild_widget_settings(9)
    await client.modify_guild_widget(9, {"enabled": True})
    await client.get_guild_widget(9)
    await client.get_guild_vanity_url(9)
    await client.get_guild_welcome_screen(9)
    await client.modify_guild_welcome_screen(9, {"enabled": True})
    await client.get_guild_onboarding(9)
    await client.modify_guild_onboarding(9, {"enabled": False}, reason="off")
    await client.modify_guild_mfa_level(9, 1)
    await client.list_active_guild_threads(9)
    await client.bulk_guild_ban(9, [1, 2], delete_message_seconds=60, reason="raid")

    assert calls == [
        ("POST", "/guilds", {"json": {"name": "New Guild"}}),
        ("PATCH", "/guilds/9", {"json": {"name": "Renamed"}, **_reason("rebrand")}),
        ("DELETE", "/guilds/9", {}),
        ("GET", "/guilds/9/prune", {"params": {"days": 7}}),
        (
            "POST",
            "/guilds/9/prune",
            {"json": {"days": 7, "compute_prune_count": False}, **_reason("prune")},
        ),
        ("GET", "/guilds/9/regions", {}),
        ("GET", "/guilds/9/integrations", {}),
        ("DELETE", "/guilds/9/integrations/3", _reason("bye")),
        ("GET", "/guilds/9/widget", {}),
        ("PATCH", "/guilds/9/widget", {"json": {"enabled": True}}),
        ("GET", "/guilds/9/widget.json", {}),
        ("GET", "/guilds/9/vanity-url", {}),
        ("GET", "/guilds/9/welcome-screen", {}),
        ("PATCH", "/guilds/9/welcome-screen", {"json": {"enabled": True}}),
        ("GET", "/guilds/9/onboarding", {}),
        ("PUT", "/guilds/9/onboarding", {"json": {"enabled": False}, **_reason("off")}),
        ("POST", "/guilds/9/mfa", {"json": {"level": 1}}),
        ("GET", "/guilds/9/threads/active", {}),
        (
            "POST",
            "/guilds/9/bulk-ban",
            {
                "json": {"user_ids": ["1", "2"], "delete_message_seconds": 60},
                **_reason("raid"),
            },
        ),
    ]


@pytest.mark.asyncio
async def test_guild_audit_log_route_with_filters(client_calls: Any) -> None:
    client, calls = client_calls

    await client.get_guild_audit_log(9)
    await client.get_guild_audit_log(9, user_id=8, action_type=20, before=100, after=1, limit=5)

    assert calls == [
        ("GET", "/guilds/9/audit-logs", {"params": None}),
        (
            "GET",
            "/guilds/9/audit-logs",
            {
                "params": {
                    "user_id": "8",
                    "action_type": 20,
                    "before": "100",
                    "after": "1",
                    "limit": 5,
                }
            },
        ),
    ]


def test_guild_widget_image_url() -> None:
    client = APIClient("token")
    assert (
        client.guild_widget_image_url(9)
        == "https://discord.com/api/v10/guilds/9/widget.png"
    )
    assert (
        client.guild_widget_image_url(9, style="banner2")
        == "https://discord.com/api/v10/guilds/9/widget.png?style=banner2"
    )


@pytest.mark.asyncio
async def test_member_and_role_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.search_guild_members(9, "neo", limit=5)
    await client.modify_current_member(9, {"nick": "trinity"}, reason="nick")
    await client.add_guild_member_role(9, 8, 7, reason="promote")
    await client.remove_guild_member_role(9, 8, 7)
    await client.get_guild_role(9, 7)

    assert calls == [
        ("GET", "/guilds/9/members/search", {"params": {"query": "neo", "limit": 5}}),
        ("PATCH", "/guilds/9/members/@me", {"json": {"nick": "trinity"}, **_reason("nick")}),
        ("PUT", "/guilds/9/members/8/roles/7", _reason("promote")),
        ("DELETE", "/guilds/9/members/8/roles/7", {}),
        ("GET", "/guilds/9/roles/7", {}),
    ]


@pytest.mark.asyncio
async def test_application_command_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.fetch_guild_command(5, 9, 3)
    await client.edit_guild_command(5, 9, 3, {"description": "updated"})
    await client.delete_guild_command(5, 9, 3)
    await client.get_guild_command_permissions(5, 9)
    await client.get_application_command_permissions(5, 9, 3)
    await client.edit_application_command_permissions(5, 9, 3, [{"id": "7", "type": 1, "permission": True}])
    await client.batch_edit_application_command_permissions(5, 9, [{"id": "3", "permissions": []}])

    assert calls == [
        ("GET", "/applications/5/guilds/9/commands/3", {}),
        ("PATCH", "/applications/5/guilds/9/commands/3", {"json": {"description": "updated"}}),
        ("DELETE", "/applications/5/guilds/9/commands/3", {}),
        ("GET", "/applications/5/guilds/9/commands/permissions", {}),
        ("GET", "/applications/5/guilds/9/commands/3/permissions", {}),
        (
            "PUT",
            "/applications/5/guilds/9/commands/3/permissions",
            {"json": {"permissions": [{"id": "7", "type": 1, "permission": True}]}},
        ),
        (
            "PUT",
            "/applications/5/guilds/9/commands/permissions",
            {"json": [{"id": "3", "permissions": []}]},
        ),
    ]


@pytest.mark.asyncio
async def test_application_resource_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.get_current_application()
    await client.edit_current_application({"description": "bot"})
    await client.get_application_role_connection_metadata(5)
    await client.update_application_role_connection_metadata(5, [{"key": "level", "type": 2}])

    assert calls == [
        ("GET", "/applications/@me", {}),
        ("PATCH", "/applications/@me", {"json": {"description": "bot"}}),
        ("GET", "/applications/5/role-connections/metadata", {}),
        (
            "PUT",
            "/applications/5/role-connections/metadata",
            {"json": [{"key": "level", "type": 2}]},
        ),
    ]


@pytest.mark.asyncio
async def test_channel_extras_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.group_dm_add_recipient(1, 8, access_token="tok", nick="n")
    await client.group_dm_remove_recipient(1, 8)
    await client.modify_guild_channel_positions(9, [{"id": "1", "position": 2}])
    await client.get_thread_member(1, 8, with_member=True)
    await client.get_thread_member(1, 8)
    await client.list_thread_members(1, with_member=True, after=5, limit=10)
    await client.start_thread_in_forum(1, {"name": "post", "message": {"content": "hi"}}, reason="new post")

    assert calls == [
        (
            "PUT",
            "/channels/1/recipients/8",
            {"json": {"access_token": "tok", "nick": "n"}},
        ),
        ("DELETE", "/channels/1/recipients/8", {}),
        ("PATCH", "/guilds/9/channels", {"json": [{"id": "1", "position": 2}]}),
        ("GET", "/channels/1/thread-members/8", {"params": {"with_member": "true"}}),
        ("GET", "/channels/1/thread-members/8", {"params": None}),
        (
            "GET",
            "/channels/1/thread-members",
            {"params": {"with_member": "true", "after": "5", "limit": 10}},
        ),
        (
            "POST",
            "/channels/1/threads",
            {
                "json": {"name": "post", "message": {"content": "hi"}},
                **_reason("new post"),
            },
        ),
    ]


@pytest.mark.asyncio
async def test_voice_routes(client_calls: Any) -> None:
    client, calls = client_calls

    await client.list_voice_regions()
    await client.get_current_user_voice_state(9)
    await client.get_user_voice_state(9, 8)
    await client.modify_current_user_voice_state(9, {"suppress": False})
    await client.modify_user_voice_state(9, 8, {"suppress": True, "channel_id": "1"})

    assert calls == [
        ("GET", "/voice/regions", {}),
        ("GET", "/guilds/9/voice-states/@me", {}),
        ("GET", "/guilds/9/voice-states/8", {}),
        ("PATCH", "/guilds/9/voice-states/@me", {"json": {"suppress": False}}),
        (
            "PATCH",
            "/guilds/9/voice-states/8",
            {"json": {"suppress": True, "channel_id": "1"}},
        ),
    ]


@pytest.mark.asyncio
async def test_scheduled_event_users_route(client_calls: Any) -> None:
    client, calls = client_calls

    await client.get_scheduled_event_users(9, 3)
    await client.get_scheduled_event_users(9, 3, limit=5, with_member=True, before=100, after=2)

    assert calls == [
        ("GET", "/guilds/9/scheduled-events/3/users", {"params": None}),
        (
            "GET",
            "/guilds/9/scheduled-events/3/users",
            {
                "params": {
                    "limit": 5,
                    "with_member": "true",
                    "before": "100",
                    "after": "2",
                }
            },
        ),
    ]


@pytest.mark.asyncio
async def test_audit_log_reason_is_url_encoded(client_calls: Any) -> None:
    client, calls = client_calls

    await client.delete_guild_emoji(9, 1, reason="héllo world / cleanup")

    assert calls == [
        (
            "DELETE",
            "/guilds/9/emojis/1",
            {"headers": {"X-Audit-Log-Reason": "h%C3%A9llo world / cleanup"}},
        ),
    ]
