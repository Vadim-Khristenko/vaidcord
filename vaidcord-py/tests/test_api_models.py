"""Parsing tests for the typed REST resource models."""

from __future__ import annotations

from vaidcord.types import (
    SKU,
    Application,
    Attachment,
    AuditLog,
    AutoModerationRule,
    Embed,
    EmbedBuilder,
    Emoji,
    Entitlement,
    GuildScheduledEvent,
    Integration,
    Invite,
    Member,
    Poll,
    Role,
    SoundboardSound,
    StageInstance,
    Sticker,
    StickerPack,
    Subscription,
    ThreadMember,
    VoiceRegion,
    Webhook,
    WelcomeScreen,
)


def test_role_from_payload() -> None:
    payload = {
        "id": "41771983423143936",
        "name": "WE DEM BOYZZ",
        "color": 3447003,
        "hoist": True,
        "position": 1,
        "permissions": "66321471",
        "managed": False,
        "mentionable": False,
        "flags": 0,
    }
    role = Role.from_payload(payload)

    assert role.id == 41771983423143936
    assert role.name == "WE DEM BOYZZ"
    assert role.mention == "<@&41771983423143936>"
    assert role.raw_data is payload
    assert not hasattr(role, "__dict__")


def test_member_from_payload_parses_role_ids() -> None:
    payload = {
        "user": {"id": "80351110224678912", "username": "neo"},
        "nick": "the one",
        "roles": ["1", "2"],
        "joined_at": "2015-04-26T06:26:56.936000+00:00",
        "deaf": False,
        "mute": False,
    }
    member = Member.from_payload(payload)

    assert member.roles == [1, 2]
    assert member.user_id == 80351110224678912
    assert member.nick == "the one"
    assert member.raw_data is payload


def test_emoji_from_payload_and_mention() -> None:
    custom = Emoji.from_payload({"id": "41771983429993937", "name": "LUL", "animated": True})
    unicode_emoji = Emoji.from_payload({"id": None, "name": "🔥"})

    assert custom.mention == "<a:LUL:41771983429993937>"
    assert unicode_emoji.id is None
    assert unicode_emoji.mention == "🔥"


def test_sticker_pack_parses_nested_stickers() -> None:
    pack = StickerPack.from_payload(
        {
            "id": "847199849233514549",
            "name": "Wumpus Beyond",
            "sku_id": "847199849233514547",
            "stickers": [{"id": "749054660769218631", "name": "Wave", "tags": "wumpus"}],
        }
    )

    assert pack.id == 847199849233514549
    assert pack.sku_id == 847199849233514547
    assert len(pack.stickers) == 1
    assert isinstance(pack.stickers[0], Sticker)
    assert pack.stickers[0].name == "Wave"


def test_attachment_from_payload() -> None:
    attachment = Attachment.from_payload(
        {
            "id": "5",
            "filename": "cat.png",
            "size": 1024,
            "url": "https://cdn.example/cat.png",
            "proxy_url": "https://proxy.example/cat.png",
            "content_type": "image/png",
            "height": 5,
            "width": 5,
        }
    )

    assert attachment.id == 5
    assert attachment.filename == "cat.png"
    assert attachment.content_type == "image/png"


def test_embed_round_trip_and_builder() -> None:
    embed_payload = (
        EmbedBuilder()
        .set_title("Release")
        .set_description("notes")
        .set_url("https://example.com")
        .set_color(0x5865F2)
        .set_timestamp("2026-01-01T00:00:00+00:00")
        .set_footer("footer", icon_url="https://example.com/f.png")
        .set_image("https://example.com/i.png")
        .set_thumbnail("https://example.com/t.png")
        .set_author("author", url="https://example.com/a", icon_url="https://example.com/a.png")
        .add_field("k1", "v1", inline=True)
        .add_field("k2", "v2")
        .to_dict()
    )

    assert embed_payload["title"] == "Release"
    assert embed_payload["footer"] == {"text": "footer", "icon_url": "https://example.com/f.png"}
    assert embed_payload["fields"] == [
        {"name": "k1", "value": "v1", "inline": True},
        {"name": "k2", "value": "v2", "inline": False},
    ]

    embed = Embed.from_payload(embed_payload)
    assert embed.title == "Release"
    assert embed.color == 0x5865F2
    # to_dict on the frozen model round-trips the builder output.
    assert embed.to_dict() == embed_payload


def test_embed_builder_build_returns_frozen_embed() -> None:
    embed = EmbedBuilder().set_title("T").build()
    assert isinstance(embed, Embed)
    assert embed.title == "T"


def test_webhook_and_invite_from_payload() -> None:
    webhook = Webhook.from_payload(
        {
            "id": "223704706495545344",
            "type": 1,
            "guild_id": "199737254929760256",
            "channel_id": "199737254929760256",
            "name": "test webhook",
            "application_id": None,
        }
    )
    invite = Invite.from_payload(
        {
            "code": "0vCdhLbwjZZTWZLD",
            "type": 0,
            "guild": {"id": "165176875973476352"},
            "channel": {"id": "165176875973476352"},
            "uses": 3,
            "max_uses": 10,
            "temporary": False,
        }
    )

    assert webhook.id == 223704706495545344
    assert webhook.guild_id == 199737254929760256
    assert webhook.application_id is None
    assert invite.code == "0vCdhLbwjZZTWZLD"
    assert invite.uses == 3


def test_thread_member_parses_nested_member() -> None:
    thread_member = ThreadMember.from_payload(
        {
            "id": "1",
            "user_id": "2",
            "join_timestamp": "2026-01-01T00:00:00+00:00",
            "flags": 0,
            "member": {"user": {"id": "2", "username": "x"}, "roles": ["3"]},
        }
    )

    assert thread_member.id == 1
    assert thread_member.user_id == 2
    assert isinstance(thread_member.member, Member)
    assert thread_member.member.roles == [3]


def test_stage_instance_and_automod_rule_from_payload() -> None:
    stage = StageInstance.from_payload(
        {
            "id": "840647391636226060",
            "guild_id": "197038439483310086",
            "channel_id": "733488538393510049",
            "topic": "Testing Testing, 123",
            "privacy_level": 2,
            "discoverable_disabled": False,
            "guild_scheduled_event_id": "947656305244532806",
        }
    )
    rule = AutoModerationRule.from_payload(
        {
            "id": "969707018069872670",
            "guild_id": "613425648685547541",
            "name": "Keyword Filter 1",
            "creator_id": "423457898095789043",
            "trigger_type": 1,
            "event_type": 1,
            "actions": [{"type": 1}],
            "trigger_metadata": {"keyword_filter": ["cat*"]},
            "enabled": True,
            "exempt_roles": ["323456789123456789"],
            "exempt_channels": ["423456789123456789"],
        }
    )

    assert stage.id == 840647391636226060
    assert stage.guild_scheduled_event_id == 947656305244532806
    assert rule.exempt_roles == [323456789123456789]
    assert rule.exempt_channels == [423456789123456789]
    assert rule.enabled is True


def test_scheduled_event_and_soundboard_from_payload() -> None:
    event = GuildScheduledEvent.from_payload(
        {
            "id": "1",
            "guild_id": "2",
            "channel_id": None,
            "creator_id": "3",
            "name": "party",
            "scheduled_start_time": "2026-03-30T15:00:00+00:00",
            "privacy_level": 2,
            "status": 1,
            "entity_type": 3,
            "entity_id": None,
            "entity_metadata": {"location": "town square"},
        }
    )
    sound = SoundboardSound.from_payload(
        {
            "sound_id": "12345",
            "name": "quack",
            "volume": 1.0,
            "emoji_id": None,
            "emoji_name": "🦆",
            "guild_id": "2",
            "available": True,
        }
    )

    assert event.id == 1
    assert event.channel_id is None
    assert event.entity_metadata == {"location": "town square"}
    assert sound.sound_id == 12345
    assert sound.emoji_name == "🦆"
    assert sound.guild_id == 2


def test_monetization_models_from_payload() -> None:
    entitlement = Entitlement.from_payload(
        {
            "id": "1",
            "sku_id": "2",
            "application_id": "3",
            "user_id": "4",
            "type": 8,
            "deleted": False,
            "starts_at": "2026-01-01T00:00:00+00:00",
            "ends_at": None,
        }
    )
    sku = SKU.from_payload(
        {"id": "2", "type": 5, "application_id": "3", "name": "Premium", "slug": "premium", "flags": 4}
    )
    subscription = Subscription.from_payload(
        {
            "id": "10",
            "user_id": "4",
            "sku_ids": ["2"],
            "entitlement_ids": [],
            "renewal_sku_ids": None,
            "status": 0,
            "country": "US",
        }
    )

    assert entitlement.sku_id == 2
    assert entitlement.user_id == 4
    assert sku.name == "Premium"
    assert subscription.sku_ids == [2]
    assert subscription.renewal_sku_ids is None


def test_audit_log_parses_nested_entries() -> None:
    audit_log = AuditLog.from_payload(
        {
            "audit_log_entries": [
                {
                    "id": "100",
                    "action_type": 20,
                    "target_id": "8",
                    "user_id": "9",
                    "reason": "spam",
                    "changes": [{"key": "nick", "new_value": "x"}],
                }
            ],
            "auto_moderation_rules": [{"id": "1", "name": "rule"}],
            "guild_scheduled_events": [{"id": "2", "name": "event"}],
            "users": [{"id": "9"}],
            "webhooks": [],
        }
    )

    entry = audit_log.audit_log_entries[0]
    assert entry.id == 100
    assert entry.target_id == 8
    assert entry.reason == "spam"
    assert audit_log.auto_moderation_rules[0].name == "rule"
    assert audit_log.guild_scheduled_events[0].name == "event"


def test_misc_models_from_payload() -> None:
    region = VoiceRegion.from_payload({"id": "us-west", "name": "US West", "optimal": True})
    application = Application.from_payload(
        {"id": "5", "name": "My App", "description": "d", "guild_id": "9", "flags": 0}
    )
    integration = Integration.from_payload(
        {"id": "3", "name": "twitch", "type": "twitch", "enabled": True, "role_id": "7"}
    )
    welcome = WelcomeScreen.from_payload(
        {"description": "hi", "welcome_channels": [{"channel_id": "1", "description": "rules"}]}
    )
    poll = Poll.from_payload(
        {
            "question": {"text": "best?"},
            "answers": [{"answer_id": 1, "poll_media": {"text": "yes"}}],
            "allow_multiselect": False,
        }
    )

    assert region.optimal is True
    assert application.id == 5
    assert application.guild_id == 9
    assert integration.role_id == 7
    assert welcome.welcome_channels[0]["channel_id"] == "1"
    assert poll.answers[0].answer_id == 1
    assert poll.answers[0].poll_media == {"text": "yes"}


def test_resource_models_are_slotted() -> None:
    role = Role.from_payload({"id": "1", "name": "r"})
    emoji = Emoji.from_payload({"id": "2", "name": "e"})
    sticker = Sticker.from_payload({"id": "3", "name": "s"})

    assert not hasattr(role, "__dict__")
    assert not hasattr(emoji, "__dict__")
    assert not hasattr(sticker, "__dict__")
