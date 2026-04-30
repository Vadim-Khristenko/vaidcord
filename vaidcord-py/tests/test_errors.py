"""
Tests for error handling module.

Covers:
- Gateway opcodes and close codes
- Voice gateway opcodes and close codes
- Discord JSON error codes
- HTTP status codes
- Error exception classes
- Error factory functions
- Nested error parsing from Discord API
"""

from __future__ import annotations

import pytest

from vaidcord.errors import (
    AuthenticationError,
    DiscordAPIError,
    DiscordErrorCode,
    ErrorDetails,
    ForbiddenError,
    GatewayCloseCode,
    GatewayError,
    # Enums
    GatewayOpcode,
    HTTPStatus,
    NotFoundError,
    RateLimitError,
    VaidCordError,
    ValidationError,
    VoiceGatewayCloseCode,
    VoiceGatewayError,
    VoiceGatewayOpcode,
    # Factory functions
    create_discord_error,
    create_gateway_error,
    create_voice_gateway_error,
)

# ============================================================================
# Gateway Opcode Tests
# ============================================================================


class TestGatewayOpcodes:
    """Test Gateway Opcodes enum."""

    def test_common_opcodes(self):
        """Test common gateway opcodes."""
        assert GatewayOpcode.DISPATCH.value == 0
        assert GatewayOpcode.HEARTBEAT.value == 1
        assert GatewayOpcode.IDENTIFY.value == 2
        assert GatewayOpcode.PRESENCE_UPDATE.value == 3
        assert GatewayOpcode.VOICE_STATE_UPDATE.value == 4
        assert GatewayOpcode.RESUME.value == 6
        assert GatewayOpcode.RECONNECT.value == 7
        assert GatewayOpcode.REQUEST_GUILD_MEMBERS.value == 8
        assert GatewayOpcode.INVALID_SESSION.value == 9
        assert GatewayOpcode.HELLO.value == 10
        assert GatewayOpcode.HEARTBEAT_ACK.value == 11

    def test_advanced_opcodes(self):
        """Test advanced gateway opcodes."""
        assert GatewayOpcode.REQUEST_SOUNDBOARD_SOUNDS.value == 31
        assert GatewayOpcode.REQUEST_CHANNEL_INFO.value == 43


class TestGatewayCloseCodes:
    """Test Gateway Close Codes enum."""

    def test_close_code_values(self):
        """Test close code values match Discord spec."""
        assert GatewayCloseCode.UNKNOWN_ERROR.value == 4000
        assert GatewayCloseCode.UNKNOWN_OPCODE.value == 4001
        assert GatewayCloseCode.DECODE_ERROR.value == 4002
        assert GatewayCloseCode.NOT_AUTHENTICATED.value == 4003
        assert GatewayCloseCode.AUTHENTICATION_FAILED.value == 4004
        assert GatewayCloseCode.ALREADY_AUTHENTICATED.value == 4005
        assert GatewayCloseCode.INVALID_SEQ.value == 4007
        assert GatewayCloseCode.RATE_LIMITED.value == 4008
        assert GatewayCloseCode.SESSION_TIMED_OUT.value == 4009
        assert GatewayCloseCode.INVALID_SHARD.value == 4010
        assert GatewayCloseCode.SHARDING_REQUIRED.value == 4011
        assert GatewayCloseCode.INVALID_API_VERSION.value == 4012
        assert GatewayCloseCode.INVALID_INTENT.value == 4013
        assert GatewayCloseCode.DISALLOWED_INTENT.value == 4014

    def test_should_reconnect_true(self):
        """Test close codes that should reconnect."""
        assert GatewayCloseCode.UNKNOWN_ERROR.should_reconnect is True
        assert GatewayCloseCode.UNKNOWN_OPCODE.should_reconnect is True
        assert GatewayCloseCode.SESSION_TIMED_OUT.should_reconnect is True
        assert GatewayCloseCode.RATE_LIMITED.should_reconnect is True

    def test_should_reconnect_false(self):
        """Test close codes that should NOT reconnect."""
        assert GatewayCloseCode.AUTHENTICATION_FAILED.should_reconnect is False
        assert GatewayCloseCode.INVALID_SHARD.should_reconnect is False
        assert GatewayCloseCode.SHARDING_REQUIRED.should_reconnect is False
        assert GatewayCloseCode.INVALID_API_VERSION.should_reconnect is False
        assert GatewayCloseCode.INVALID_INTENT.should_reconnect is False
        assert GatewayCloseCode.DISALLOWED_INTENT.should_reconnect is False

    def test_close_code_descriptions(self):
        """Test close code descriptions are present."""
        for code in GatewayCloseCode:
            assert code.description
            assert len(code.description) > 0


# ============================================================================
# Voice Gateway Tests
# ============================================================================


class TestVoiceGatewayOpcodes:
    """Test Voice Gateway Opcodes enum."""

    def test_common_opcodes(self):
        """Test common voice gateway opcodes."""
        assert VoiceGatewayOpcode.IDENTIFY.value == 0
        assert VoiceGatewayOpcode.SELECT_PROTOCOL.value == 1
        assert VoiceGatewayOpcode.READY.value == 2
        assert VoiceGatewayOpcode.HEARTBEAT.value == 3
        assert VoiceGatewayOpcode.SESSION_DESCRIPTION.value == 4
        assert VoiceGatewayOpcode.SPEAKING.value == 5
        assert VoiceGatewayOpcode.HEARTBEAT_ACK.value == 6
        assert VoiceGatewayOpcode.RESUME.value == 7
        assert VoiceGatewayOpcode.HELLO.value == 8
        assert VoiceGatewayOpcode.RESUMED.value == 9

    def test_dave_opcodes(self):
        """Test DAVE protocol opcodes."""
        assert VoiceGatewayOpcode.DAVE_PREPARE_TRANSITION.value == 21
        assert VoiceGatewayOpcode.DAVE_EXECUTE_TRANSITION.value == 22
        assert VoiceGatewayOpcode.DAVE_MLS_WELCOME.value == 30


class TestVoiceGatewayCloseCodes:
    """Test Voice Gateway Close Codes enum."""

    def test_close_code_values(self):
        """Test voice close code values."""
        assert VoiceGatewayCloseCode.UNKNOWN_OPCODE.value == 4001
        assert VoiceGatewayCloseCode.AUTHENTICATION_FAILED.value == 4004
        assert VoiceGatewayCloseCode.DISCONNECTED.value == 4014
        assert VoiceGatewayCloseCode.E2EE_DAVE_REQUIRED.value == 4017
        assert VoiceGatewayCloseCode.DISCONNECTED_RATE_LIMITED.value == 4021
        assert VoiceGatewayCloseCode.DISCONNECTED_CALL_TERMINATED.value == 4022

    def test_should_reconnect(self):
        """Test voice close code reconnection logic."""
        assert VoiceGatewayCloseCode.VOICE_SERVER_CRASHED.should_reconnect is True
        assert VoiceGatewayCloseCode.DISCONNECTED.should_reconnect is False
        assert VoiceGatewayCloseCode.DISCONNECTED_RATE_LIMITED.should_reconnect is False
        assert (
            VoiceGatewayCloseCode.DISCONNECTED_CALL_TERMINATED.should_reconnect is False
        )

    def test_close_code_descriptions(self):
        """Test voice close code descriptions."""
        for code in VoiceGatewayCloseCode:
            assert code.description
            assert len(code.description) > 0


# ============================================================================
# HTTP Status Tests
# ============================================================================


class TestHTTPStatus:
    """Test HTTP Status codes enum."""

    def test_success_codes(self):
        """Test success status codes."""
        assert HTTPStatus.OK.value == 200
        assert HTTPStatus.CREATED.value == 201
        assert HTTPStatus.NO_CONTENT.value == 204
        assert HTTPStatus.NOT_MODIFIED.value == 304

    def test_client_error_codes(self):
        """Test client error status codes."""
        assert HTTPStatus.BAD_REQUEST.value == 400
        assert HTTPStatus.UNAUTHORIZED.value == 401
        assert HTTPStatus.FORBIDDEN.value == 403
        assert HTTPStatus.NOT_FOUND.value == 404
        assert HTTPStatus.METHOD_NOT_ALLOWED.value == 405
        assert HTTPStatus.TOO_MANY_REQUESTS.value == 429

    def test_server_error_codes(self):
        """Test server error status codes."""
        assert HTTPStatus.GATEWAY_UNAVAILABLE.value == 502
        assert HTTPStatus.SERVER_ERROR.value == 500


# ============================================================================
# Discord Error Code Tests
# ============================================================================


class TestDiscordErrorCode:
    """Test Discord JSON Error Codes enum."""

    def test_unknown_resource_codes(self):
        """Test unknown resource error codes."""
        assert DiscordErrorCode.UNKNOWN_ACCOUNT.value == 10001
        assert DiscordErrorCode.UNKNOWN_CHANNEL.value == 10003
        assert DiscordErrorCode.UNKNOWN_GUILD.value == 10004
        assert DiscordErrorCode.UNKNOWN_MESSAGE.value == 10008
        assert DiscordErrorCode.UNKNOWN_USER.value == 10013

    def test_bot_codes(self):
        """Test bot-related error codes."""
        assert DiscordErrorCode.BOTS_CANNOT_USE_ENDPOINT.value == 20001
        assert DiscordErrorCode.BOT_ONLY_ENDPOINT.value == 20002

    def test_limit_codes(self):
        """Test limit-related error codes."""
        assert DiscordErrorCode.MAX_GUILDS_REACHED.value == 30001
        assert DiscordErrorCode.MAX_FRIENDS_REACHED.value == 30002
        assert DiscordErrorCode.MAX_CHANNELS_REACHED.value == 30013

    def test_permission_codes(self):
        """Test permission-related error codes."""
        assert DiscordErrorCode.MISSING_ACCESS.value == 50001
        assert DiscordErrorCode.MISSING_PERMISSIONS.value == 50013
        assert DiscordErrorCode.INVALID_AUTH_TOKEN.value == 50014

    def test_error_code_category(self):
        """Test error code categorization."""
        assert DiscordErrorCode.GENERAL_ERROR.category == "General"
        assert DiscordErrorCode.UNKNOWN_USER.category == "Unknown Resource"
        assert DiscordErrorCode.BOTS_CANNOT_USE_ENDPOINT.category == "Bot/User Action"
        assert DiscordErrorCode.MAX_GUILDS_REACHED.category == "Limit Reached"
        assert DiscordErrorCode.MISSING_PERMISSIONS.category == "Permissions"
        assert (
            DiscordErrorCode.TWO_FACTOR_REQUIRED.category == "Two-Factor Authentication"
        )

    def test_error_code_description(self):
        """Test error code descriptions exist."""
        for code in list(DiscordErrorCode)[:20]:  # Test first 20 codes
            assert code.description
            assert len(code.description) > 0


# ============================================================================
# Exception Class Tests
# ============================================================================


class TestVaidCordError:
    """Test base VaidCordError class."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = VaidCordError("Something went wrong")
        assert error.message == "Something went wrong"
        assert error.code is None
        assert error.status is None
        assert error.details == []
        assert error.raw_data == {}

    def test_error_with_code_and_status(self):
        """Test error with code and status."""
        error = VaidCordError("Error", code=50035, status=400)
        assert error.code == 50035
        assert error.status == 400

    def test_error_string_representation(self):
        """Test error string representation."""
        error = VaidCordError("Test error", code=123, status=400)
        str_repr = str(error)
        assert "Test error" in str_repr
        assert "Code: 123" in str_repr
        assert "Status: 400" in str_repr

    def test_error_to_dict(self):
        """Test converting error to dictionary."""
        error = VaidCordError("Test", code=123)
        data = error.to_dict()
        assert data["type"] == "VaidCordError"
        assert data["message"] == "Test"
        assert data["code"] == 123


class TestDiscordAPIError:
    """Test DiscordAPIError class."""

    def test_basic_api_error(self):
        """Test basic API error."""
        error = DiscordAPIError(
            "Invalid Form Body",
            code=50035,
            status=400,
        )
        assert error.message == "Invalid Form Body"
        assert error.code == 50035
        assert error.status == 400
        assert error.errors is None

    def test_api_error_with_nested_errors(self):
        """Test API error with nested error structure."""
        errors_data = {
            "activities": {
                "0": {
                    "platform": {
                        "_errors": [
                            {
                                "code": "BASE_TYPE_CHOICES",
                                "message": "Value must be one of ('desktop', 'android', 'ios').",
                            }
                        ]
                    }
                }
            }
        }
        error = DiscordAPIError(
            "Invalid Form Body",
            code=50035,
            status=400,
            errors=errors_data,
        )

        assert len(error.details) == 1
        detail = error.details[0]
        assert detail.code == "BASE_TYPE_CHOICES"
        assert "platform" in detail.path
        assert "activities" in detail.path

    def test_api_error_formatted_details(self):
        """Test formatted error details output."""
        errors_data = {
            "username": {
                "_errors": [{"code": "REQUIRED", "message": "This field is required"}]
            }
        }
        error = DiscordAPIError(
            "Validation failed",
            code=50035,
            errors=errors_data,
        )

        formatted = error.formatted_details
        assert "Error Details:" in formatted
        assert "username" in formatted
        assert "REQUIRED" in formatted

    def test_api_error_code_enum(self):
        """Test getting error code enum."""
        error = DiscordAPIError("Missing access", code=50001)
        assert error.error_code_enum == DiscordErrorCode.MISSING_ACCESS

    def test_api_error_invalid_code_enum(self):
        """Test error code enum with invalid code."""
        error = DiscordAPIError("Custom error", code=99999)
        assert error.error_code_enum is None


class TestGatewayError:
    """Test GatewayError class."""

    def test_gateway_error_with_close_code(self):
        """Test gateway error with close code."""
        error = GatewayError(
            "Authentication failed",
            close_code=GatewayCloseCode.AUTHENTICATION_FAILED,
        )
        assert error.close_code == GatewayCloseCode.AUTHENTICATION_FAILED
        assert error.code == 4004
        assert error.should_reconnect is False

    def test_gateway_error_string(self):
        """Test gateway error string representation."""
        error = GatewayError(
            "Session timed out",
            close_code=GatewayCloseCode.SESSION_TIMED_OUT,
        )
        str_repr = str(error)
        assert "SESSION_TIMED_OUT" in str_repr
        assert "4009" in str_repr
        assert "Should Reconnect: True" in str_repr


class TestVoiceGatewayError:
    """Test VoiceGatewayError class."""

    def test_voice_error_with_close_code(self):
        """Test voice gateway error."""
        error = VoiceGatewayError(
            "Server crashed",
            close_code=VoiceGatewayCloseCode.VOICE_SERVER_CRASHED,
        )
        assert error.close_code == VoiceGatewayCloseCode.VOICE_SERVER_CRASHED
        assert error.should_reconnect is True


class TestRateLimitError:
    """Test RateLimitError class."""

    def test_rate_limit_error(self):
        """Test rate limit error."""
        error = RateLimitError(
            "Rate limited",
            retry_after=5.5,
            global_limit=True,
            route="/channels/123/messages",
        )
        assert error.retry_after == 5.5
        assert error.global_limit is True
        assert error.route == "/channels/123/messages"
        assert error.code == 429
        assert error.status == 429

    def test_rate_limit_error_string(self):
        """Test rate limit error string."""
        error = RateLimitError("Too many requests", retry_after=10.0)
        str_repr = str(error)
        assert "Retry After: 10.0s" in str_repr


class TestAuthenticationError:
    """Test AuthenticationError class."""

    def test_auth_error(self):
        """Test authentication error."""
        error = AuthenticationError(
            "Invalid token",
            reason="Token expired",
        )
        assert error.reason == "Token expired"
        assert error.code == 401
        assert error.status == 401


class TestForbiddenError:
    """Test ForbiddenError class."""

    def test_forbidden_error(self):
        """Test forbidden error."""
        error = ForbiddenError(
            "Missing permissions",
            missing_permissions=["SEND_MESSAGES", "MANAGE_CHANNELS"],
        )
        assert error.missing_permissions == ["SEND_MESSAGES", "MANAGE_CHANNELS"]
        assert error.code == 403


class TestNotFoundError:
    """Test NotFoundError class."""

    def test_not_found_error(self):
        """Test not found error."""
        error = NotFoundError(
            "Channel not found",
            resource_type="channel",
            resource_id=123456789,
        )
        assert error.resource_type == "channel"
        assert error.resource_id == 123456789
        assert error.code == 404


class TestValidationError:
    """Test ValidationError class."""

    def test_validation_error(self):
        """Test validation error."""
        error = ValidationError(
            "Invalid value",
            field="username",
            value="",
        )
        assert error.field == "username"
        assert error.value == ""
        assert error.code == 400


# ============================================================================
# Error Factory Tests
# ============================================================================


class TestCreateDiscordError:
    """Test create_discord_error factory function."""

    def test_create_auth_error(self):
        """Test creating authentication error."""
        data = {"code": 50014, "message": "Invalid authentication token"}
        error = create_discord_error(401, data)
        assert isinstance(error, AuthenticationError)
        # Note: AuthenticationError sets code to 401 (HTTP status), not Discord error code
        assert error.status == 401
        assert error.code == 401

    def test_create_forbidden_error(self):
        """Test creating forbidden error."""
        data = {"code": 50013, "message": "Missing permissions"}
        error = create_discord_error(403, data)
        assert isinstance(error, ForbiddenError)

    def test_create_not_found_error(self):
        """Test creating not found error."""
        data = {"code": 10003, "message": "Unknown channel"}
        error = create_discord_error(404, data)
        assert isinstance(error, NotFoundError)

    def test_create_rate_limit_error(self):
        """Test creating rate limit error."""
        data = {
            "message": "You are being rate limited",
            "retry_after": 5.0,
            "global": True,
        }
        error = create_discord_error(429, data)
        assert isinstance(error, RateLimitError)
        assert error.retry_after == 5.0
        assert error.global_limit is True

    def test_create_api_error_with_nested_errors(self):
        """Test creating API error with nested errors."""
        data = {
            "code": 50035,
            "message": "Invalid Form Body",
            "errors": {
                "content": {
                    "_errors": [{"code": "REQUIRED", "message": "Content is required"}]
                }
            },
        }
        error = create_discord_error(400, data)
        assert isinstance(error, DiscordAPIError)
        assert len(error.details) == 1

    def test_create_server_error(self):
        """Test creating server error."""
        data = {"message": "Internal server error"}
        error = create_discord_error(500, data)
        assert isinstance(error, VaidCordError)
        assert error.status == 500


class TestCreateGatewayError:
    """Test create_gateway_error factory function."""

    def test_create_known_gateway_error(self):
        """Test creating gateway error with known code."""
        error = create_gateway_error(4004)
        assert isinstance(error, GatewayError)
        assert error.close_code == GatewayCloseCode.AUTHENTICATION_FAILED
        assert error.should_reconnect is False

    def test_create_unknown_gateway_error(self):
        """Test creating gateway error with unknown code."""
        error = create_gateway_error(9999, "Custom error")
        assert isinstance(error, GatewayError)
        assert error.close_code is None
        assert "Custom error" in str(error)


class TestCreateVoiceGatewayError:
    """Test create_voice_gateway_error factory function."""

    def test_create_known_voice_error(self):
        """Test creating voice gateway error with known code."""
        error = create_voice_gateway_error(4015)
        assert isinstance(error, VoiceGatewayError)
        assert error.close_code == VoiceGatewayCloseCode.VOICE_SERVER_CRASHED
        assert error.should_reconnect is True

    def test_create_unknown_voice_error(self):
        """Test creating voice gateway error with unknown code."""
        error = create_voice_gateway_error(9999, "Custom voice error")
        assert isinstance(error, VoiceGatewayError)
        assert error.close_code is None


# ============================================================================
# ErrorDetails Tests
# ============================================================================


class TestErrorDetails:
    """Test ErrorDetails dataclass."""

    def test_error_details_creation(self):
        """Test creating error details."""
        details = ErrorDetails(
            code="REQUIRED",
            message="This field is required",
            path=["username"],
        )
        assert details.code == "REQUIRED"
        assert details.message == "This field is required"
        assert details.path == ["username"]

    def test_error_details_to_dict(self):
        """Test converting error details to dict."""
        details = ErrorDetails(
            code="INVALID",
            message="Invalid value",
            path=["embed", "title"],
        )
        data = details.to_dict()
        assert data["code"] == "INVALID"
        assert data["message"] == "Invalid value"
        assert data["path"] == ["embed", "title"]


# ============================================================================
# Integration Tests
# ============================================================================


class TestErrorIntegration:
    """Integration tests for error handling."""

    def test_complex_nested_error_parsing(self):
        """Test parsing complex nested error structure from Discord."""
        errors_data = {
            "activities": {
                "0": {
                    "platform": {
                        "_errors": [
                            {
                                "code": "BASE_TYPE_CHOICES",
                                "message": "Value must be one of ('desktop', 'android', 'ios').",
                            }
                        ]
                    },
                    "type": {
                        "_errors": [
                            {
                                "code": "BASE_TYPE_CHOICES",
                                "message": "Value must be one of (0, 1, 2, 3, 4, 5).",
                            }
                        ]
                    },
                }
            },
            "access_token": {
                "_errors": [
                    {"code": "BASE_TYPE_REQUIRED", "message": "This field is required"}
                ]
            },
        }

        error = DiscordAPIError(
            "Invalid Form Body",
            code=50035,
            status=400,
            errors=errors_data,
        )

        # Should have 3 error details
        assert len(error.details) == 3

        # Check paths
        paths = [d.path for d in error.details]
        assert ["activities", "0", "platform"] in paths
        assert ["activities", "0", "type"] in paths
        assert ["access_token"] in paths

    def test_request_error_format(self):
        """Test Request Error format from Discord docs."""
        # Root-level errors use "_errors" key directly in the errors object
        errors_data = {
            "_errors": [
                {
                    "code": "APPLICATION_COMMAND_TOO_LARGE",
                    "message": "Command exceeds maximum size (8000)",
                }
            ]
        }

        error = DiscordAPIError(
            "Invalid Form Body",
            code=50035,
            errors=errors_data,
        )

        # Root level errors are parsed with empty path
        assert len(error.details) == 1
        assert error.details[0].path == []  # Root level error
        assert error.details[0].code == "APPLICATION_COMMAND_TOO_LARGE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
