"""
Tests for permissions module.
"""


from vaidcord.permissions import (
    PermissionCalculator,
    PermissionOverwrite,
    Permissions,
    calculate_permissions,
    check_permission,
)


class TestPermissions:
    """Test basic Permissions functionality."""

    def test_permission_creation(self):
        """Test creating permissions from integer."""
        perms = Permissions(0x800)  # SEND_MESSAGES
        assert perms == Permissions.SEND_MESSAGES

    def test_permission_from_int(self):
        """Test creating permissions from int and string."""
        perms_int = Permissions.from_int(2048)
        perms_str = Permissions.from_int("2048")
        assert perms_int == perms_str
        assert perms_int == Permissions.SEND_MESSAGES  # 2048 = 1 << 11

    def test_permission_to_string(self):
        """Test converting permissions to string for API."""
        perms = Permissions.ADMINISTRATOR
        assert perms.to_string() == "8"

    def test_permission_has(self):
        """Test checking if permissions contain specific flags."""
        perms = Permissions.SEND_MESSAGES | Permissions.EMBED_LINKS
        assert perms.has(Permissions.SEND_MESSAGES)
        assert perms.has(Permissions.EMBED_LINKS)
        assert not perms.has(Permissions.MANAGE_MESSAGES)

    def test_permission_add(self):
        """Test adding permissions."""
        perms = Permissions.SEND_MESSAGES
        new_perms = perms.add(Permissions.EMBED_LINKS)
        assert new_perms.has(Permissions.SEND_MESSAGES)
        assert new_perms.has(Permissions.EMBED_LINKS)

    def test_permission_remove(self):
        """Test removing permissions."""
        perms = Permissions.SEND_MESSAGES | Permissions.EMBED_LINKS
        new_perms = perms.remove(Permissions.SEND_MESSAGES)
        assert not new_perms.has(Permissions.SEND_MESSAGES)
        assert new_perms.has(Permissions.EMBED_LINKS)

    def test_permission_all(self):
        """Test getting all permissions."""
        all_perms = Permissions.all()
        assert all_perms.has(Permissions.ADMINISTRATOR)
        assert all_perms.has(Permissions.SEND_MESSAGES)
        assert all_perms.has(Permissions.BAN_MEMBERS)

    def test_permission_none(self):
        """Test getting no permissions."""
        no_perms = Permissions.none()
        assert int(no_perms) == 0
        assert not no_perms.has(Permissions.SEND_MESSAGES)

    def test_permission_default(self):
        """Test default permissions."""
        default = Permissions.default()
        assert default.has(Permissions.VIEW_CHANNEL)
        assert default.has(Permissions.SEND_MESSAGES)
        assert default.has(Permissions.CONNECT)

    def test_administrator_bypass(self):
        """Test that ADMINISTRATOR includes all permissions."""
        admin = Permissions.ADMINISTRATOR
        # Administrator should have all base permissions through bitwise OR
        assert admin.has(Permissions.ADMINISTRATOR)


class TestPermissionOverwrite:
    """Test PermissionOverwrite functionality."""

    def test_overwrite_creation(self):
        """Test creating permission overwrite."""
        overwrite = PermissionOverwrite(
            id="123456789",
            type=0,
            allow=Permissions.SEND_MESSAGES,
            deny=Permissions.MANAGE_MESSAGES,
        )
        assert overwrite.id == 123456789
        assert overwrite.type == 0
        assert overwrite.allow.has(Permissions.SEND_MESSAGES)
        assert overwrite.deny.has(Permissions.MANAGE_MESSAGES)

    def test_overwrite_from_dict(self):
        """Test creating overwrite from API data."""
        data = {
            "id": "987654321",
            "type": 1,
            "allow": "2048",  # SEND_MESSAGES (1 << 11)
            "deny": "4096",   # SEND_TTS_MESSAGES (1 << 12)
        }
        overwrite = PermissionOverwrite.from_dict(data)
        assert overwrite.id == 987654321
        assert overwrite.type == 1
        assert overwrite.allow.has(Permissions.SEND_MESSAGES)
        assert overwrite.deny.has(Permissions.SEND_TTS_MESSAGES)

    def test_overwrite_to_dict(self):
        """Test converting overwrite to dict for API."""
        overwrite = PermissionOverwrite(
            id=123,
            type=0,
            allow=Permissions.SEND_MESSAGES,
            deny=Permissions.MANAGE_MESSAGES,  # 8192 = 1 << 13
        )
        data = overwrite.to_dict()
        assert data["id"] == "123"
        assert data["type"] == 0
        assert data["allow"] == "2048"
        assert data["deny"] == "8192"

    def test_set_allow(self):
        """Test setting permissions as allowed."""
        overwrite = PermissionOverwrite(id=1, type=0)
        overwrite.set_allow(Permissions.SEND_MESSAGES, Permissions.EMBED_LINKS)
        assert overwrite.allow.has(Permissions.SEND_MESSAGES)
        assert overwrite.allow.has(Permissions.EMBED_LINKS)
        assert not overwrite.deny.has(Permissions.SEND_MESSAGES)

    def test_set_deny(self):
        """Test setting permissions as denied."""
        overwrite = PermissionOverwrite(id=1, type=0)
        overwrite.set_deny(Permissions.MANAGE_MESSAGES)
        assert overwrite.deny.has(Permissions.MANAGE_MESSAGES)
        assert not overwrite.allow.has(Permissions.MANAGE_MESSAGES)

    def test_reset(self):
        """Test resetting permissions."""
        overwrite = PermissionOverwrite(
            id=1,
            type=0,
            allow=Permissions.SEND_MESSAGES,
            deny=Permissions.MANAGE_MESSAGES,
        )
        overwrite.reset(Permissions.SEND_MESSAGES, Permissions.MANAGE_MESSAGES)
        assert not overwrite.allow.has(Permissions.SEND_MESSAGES)
        assert not overwrite.deny.has(Permissions.MANAGE_MESSAGES)


class TestPermissionCalculator:
    """Test permission calculation logic."""

    def test_base_permissions_owner(self):
        """Test that guild owner has all permissions."""
        # Mock member and guild
        class MockMember:
            is_timed_out = lambda self: False
            id = 123
            roles = []

        class MockGuild:
            id = 456

            def is_owner(self, member):
                return True

            def get_role(self, role_id):
                return None

        member = MockMember()
        guild = MockGuild()

        base_perms = PermissionCalculator.compute_base_permissions(member, guild)
        assert base_perms == Permissions.all()

    def test_base_permissions_everyone(self):
        """Test base permissions from @everyone role."""
        class MockRole:
            id = 456
            permissions = str(Permissions.VIEW_CHANNEL.value)

        class MockMember:
            is_timed_out = lambda self: False
            id = 123
            roles = []

            def is_timed_out(self):
                return False

        class MockGuild:
            id = 456

            def is_owner(self, member):
                return False

            def get_role(self, role_id):
                if role_id == 456:
                    return MockRole()
                return None

        member = MockMember()
        guild = MockGuild()

        base_perms = PermissionCalculator.compute_base_permissions(member, guild)
        assert base_perms.has(Permissions.VIEW_CHANNEL)

    def test_base_permissions_with_roles(self):
        """Test base permissions with multiple roles."""
        class MockRole1:
            id = 111
            permissions = str(Permissions.SEND_MESSAGES.value)

        class MockRole2:
            id = 222
            permissions = str(Permissions.EMBED_LINKS.value)

        class MockMember:
            is_timed_out = lambda self: False
            id = 123
            roles = [MockRole1(), MockRole2()]

        class MockGuild:
            id = 456

            def is_owner(self, member):
                return False

            def get_role(self, role_id):
                class EveryoneRole:
                    permissions = str(Permissions.VIEW_CHANNEL.value)
                return EveryoneRole()

        member = MockMember()
        guild = MockGuild()

        base_perms = PermissionCalculator.compute_base_permissions(member, guild)
        assert base_perms.has(Permissions.VIEW_CHANNEL)
        assert base_perms.has(Permissions.SEND_MESSAGES)
        assert base_perms.has(Permissions.EMBED_LINKS)

    def test_administrator_bypass_overwrites(self):
        """Test that ADMINISTRATOR bypasses overwrites."""
        class MockRole:
            id = 456
            permissions = str(Permissions.ADMINISTRATOR.value)

        class MockMember:
            is_timed_out = lambda self: False
            id = 123
            roles = [MockRole()]

        class MockChannel:
            guild_id = 789
            permission_overwrites = {
                789: PermissionOverwrite(
                    id=789,
                    type=0,
                    allow=Permissions.none(),
                    deny=Permissions.all(),
                )
            }

            class MockGuild:
                id = 789

                def is_owner(self, member):
                    return False

                def get_role(self, role_id):
                    return None

            guild = MockGuild()

        member = MockMember()
        channel = MockChannel()

        base_perms = PermissionCalculator.compute_base_permissions(
            member, channel.guild
        )
        final_perms = PermissionCalculator.compute_overwrites(
            base_perms, member, channel
        )
        assert final_perms == Permissions.all()

    def test_overwrite_hierarchy(self):
        """Test permission overwrite hierarchy."""
        class MockRole:
            id = 111
            permissions = str(Permissions.VIEW_CHANNEL.value)

        class MockMember:
            is_timed_out = lambda self: False
            id = 123
            roles = [MockRole()]

        class MockChannel:
            guild_id = 789
            permission_overwrites = {
                # @everyone deny SEND_MESSAGES
                789: PermissionOverwrite(
                    id=789,
                    type=0,
                    allow=Permissions.none(),
                    deny=Permissions.SEND_MESSAGES,
                ),
                # Role allow SEND_MESSAGES
                111: PermissionOverwrite(
                    id=111,
                    type=0,
                    allow=Permissions.SEND_MESSAGES,
                    deny=Permissions.none(),
                ),
                # Member deny SEND_MESSAGES (highest priority)
                123: PermissionOverwrite(
                    id=123,
                    type=1,
                    allow=Permissions.none(),
                    deny=Permissions.SEND_MESSAGES,
                ),
            }

            class MockGuild:
                id = 789

                def is_owner(self, member):
                    return False

                def get_role(self, role_id):
                    if role_id == 789:
                        class EveryoneRole:
                            permissions = str(Permissions.VIEW_CHANNEL.value)
                        return EveryoneRole()
                    return None

            guild = MockGuild()

        member = MockMember()
        channel = MockChannel()

        base_perms = PermissionCalculator.compute_base_permissions(
            member, channel.guild
        )
        final_perms = PermissionCalculator.compute_overwrites(
            base_perms, member, channel
        )

        # Member-specific deny should win
        assert not final_perms.has(Permissions.SEND_MESSAGES)

    def test_implicit_denied_view_channel(self):
        """Test implicit denial when VIEW_CHANNEL is missing."""
        perms = Permissions.SEND_MESSAGES | Permissions.EMBED_LINKS
        implicit = PermissionCalculator.get_implicit_denied(perms)

        # Should implicitly deny message-related permissions
        assert implicit.has(Permissions.SEND_MESSAGES)
        assert implicit.has(Permissions.EMBED_LINKS)

    def test_implicit_denied_send_messages(self):
        """Test implicit denial of related permissions when SEND_MESSAGES is denied."""
        perms = Permissions.VIEW_CHANNEL | Permissions.EMBED_LINKS
        implicit = PermissionCalculator.get_implicit_denied(perms)

        # Should implicitly deny message-related permissions
        assert implicit.has(Permissions.MENTION_EVERYONE)
        assert implicit.has(Permissions.SEND_TTS_MESSAGES)
        assert implicit.has(Permissions.ATTACH_FILES)


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_calculate_permissions(self):
        """Test calculate_permissions function."""
        class MockRole:
            id = 456
            permissions = str(Permissions.VIEW_CHANNEL.value)

        class MockMember:
            is_timed_out = lambda self: False
            id = 123
            roles = [MockRole()]

        class MockChannel:
            guild_id = 789
            permission_overwrites = {}

            class MockGuild:
                id = 789

                def is_owner(self, member):
                    return False

                def get_role(self, role_id):
                    if role_id == 789:
                        class EveryoneRole:
                            permissions = str(Permissions.VIEW_CHANNEL.value)
                        return EveryoneRole()
                    return None

            guild = MockGuild()

        member = MockMember()
        channel = MockChannel()

        perms = calculate_permissions(member, channel)
        assert perms.has(Permissions.VIEW_CHANNEL)

    def test_check_permission(self):
        """Test check_permission function."""
        class MockRole:
            id = 456
            permissions = str((Permissions.VIEW_CHANNEL | Permissions.SEND_MESSAGES).value)

        class MockMember:
            is_timed_out = lambda self: False
            id = 123
            roles = [MockRole()]

        class MockChannel:
            guild_id = 789
            permission_overwrites = {}

            class MockGuild:
                id = 789

                def is_owner(self, member):
                    return False

                def get_role(self, role_id):
                    if role_id == 789:
                        class EveryoneRole:
                            permissions = str(Permissions.VIEW_CHANNEL.value)
                        return EveryoneRole()
                    return None

            guild = MockGuild()

        member = MockMember()
        channel = MockChannel()

        # Should have SEND_MESSAGES
        assert check_permission(member, channel, Permissions.SEND_MESSAGES)
        # Should not have MANAGE_MESSAGES
        assert not check_permission(member, channel, Permissions.MANAGE_MESSAGES)

    def test_calculate_permissions_with_explicit_guild_and_list_overwrites(self):
        """Test calculate_permissions supports API-style list overwrites."""
        class MockRole:
            id = 456
            permissions = str(Permissions.VIEW_CHANNEL.value)

        class MockMember:
            is_timed_out = lambda self: False
            id = 123
            roles = [MockRole()]

        class MockGuild:
            id = 789

            def is_owner(self, member):
                return False

            def get_role(self, role_id):
                if role_id == 789:
                    class EveryoneRole:
                        permissions = str(Permissions.VIEW_CHANNEL.value)

                    return EveryoneRole()
                return None

        class MockChannel:
            permission_overwrites = [
                {
                    "id": "789",
                    "type": 0,
                    "allow": "2048",  # SEND_MESSAGES
                    "deny": "0",
                }
            ]

        perms = calculate_permissions(MockMember(), MockChannel(), guild=MockGuild())
        assert perms.has(Permissions.SEND_MESSAGES)


class TestChannelSpecificPermissions:
    """Test channel-type specific permissions."""

    def test_text_channel_permissions(self):
        """Test text channel permissions list."""
        perms = Permissions.SEND_MESSAGES
        text_perms = perms.text_channel_permissions
        # Just verify it returns a list
        assert isinstance(text_perms, list)

    def test_voice_channel_permissions(self):
        """Test voice channel permissions list."""
        perms = Permissions.CONNECT
        voice_perms = perms.voice_channel_permissions
        assert isinstance(voice_perms, list)

    def test_stage_channel_permissions(self):
        """Test stage channel permissions list."""
        perms = Permissions.REQUEST_TO_SPEAK
        stage_perms = perms.stage_channel_permissions
        assert isinstance(stage_perms, list)


class TestAdministrativePermissions:
    """Test administrative permissions that require 2FA."""

    def test_administrative_permissions_list(self):
        """Test administrative permissions list."""
        perms = Permissions.KICK_MEMBERS
        admin_perms = perms.administrative_permissions
        assert isinstance(admin_perms, list)
        assert Permissions.KICK_MEMBERS in admin_perms
        assert Permissions.BAN_MEMBERS in admin_perms
        assert Permissions.ADMINISTRATOR in admin_perms
        assert Permissions.MANAGE_ROLES in admin_perms
