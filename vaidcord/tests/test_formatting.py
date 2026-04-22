"""Tests for VaidCord formatting utilities."""

from datetime import datetime, timezone

import pytest

from vaidcord.formatting import (
    CodeBlockLanguage,
    Formatter,
    Mention,
    TextStyle,
    TimestampStyle,
)


class TestTextStyle:
    """Tests for basic text styling."""

    def test_bold(self) -> None:
        assert Formatter.bold("hello") == "**hello**"

    def test_italic(self) -> None:
        assert Formatter.italic("hello") == "*hello*"

    def test_underline(self) -> None:
        assert Formatter.underline("hello") == "__hello__"

    def test_strikethrough(self) -> None:
        assert Formatter.strikethrough("hello") == "~~hello~~"

    def test_spoiler(self) -> None:
        assert Formatter.spoiler("hello") == "||hello||"

    def test_inline_code(self) -> None:
        assert Formatter.inline_code("hello") == "`hello`"

    def test_inline_code_with_backticks(self) -> None:
        assert Formatter.inline_code("he`llo") == "`he\\`llo`"


class TestCodeBlock:
    """Tests for code block formatting."""

    def test_code_block_no_language(self) -> None:
        result = Formatter.code_block("print('hello')")
        assert result == "```\nprint('hello')\n```"

    def test_code_block_with_language_enum(self) -> None:
        result = Formatter.code_block("print('hello')", CodeBlockLanguage.PYTHON)
        assert result == "```python\nprint('hello')\n```"

    def test_code_block_with_language_string(self) -> None:
        result = Formatter.code_block("print('hello')", "javascript")
        assert result == "```javascript\nprint('hello')\n```"

    def test_code_block_with_triple_backticks(self) -> None:
        result = Formatter.code_block("```code```")
        assert "\\`\\`\\`" in result


class TestCombinedStyles:
    """Tests for combining multiple styles."""

    def test_bold_and_italic(self) -> None:
        result = Formatter.combine_styles("text", TextStyle.BOLD, TextStyle.ITALIC)
        assert result == "***text***"

    def test_bold_underline_strikethrough(self) -> None:
        result = Formatter.combine_styles(
            "text",
            TextStyle.BOLD,
            TextStyle.UNDERLINE,
            TextStyle.STRIKETHROUGH,
        )
        assert result == "~~__**text**__~~"

    def test_spoiler_and_bold(self) -> None:
        result = Formatter.combine_styles("secret", TextStyle.SPOILER, TextStyle.BOLD)
        # Order matters: SPOILER first, then BOLD is applied to the result
        assert result == "**||secret||**"


class TestMentions:
    """Tests for Discord mentions."""

    def test_user_mention(self) -> None:
        assert Formatter.mention_user(123456789) == "<@123456789>"

    def test_role_mention(self) -> None:
        assert Formatter.mention_role(987654321) == "<@&987654321>"

    def test_channel_mention(self) -> None:
        assert Formatter.mention_channel(456789123) == "<#456789123>"

    def test_mention_object_user(self) -> None:
        mention = Formatter.user_mention_from_obj(123)
        assert str(mention) == "<@123>"
        assert mention.id == 123
        assert mention.type == "user"

    def test_mention_object_role(self) -> None:
        mention = Formatter.role_mention_from_obj(456)
        assert str(mention) == "<@&456>"
        assert mention.type == "role"

    def test_mention_object_channel(self) -> None:
        mention = Formatter.channel_mention_from_obj(789)
        assert str(mention) == "<#789>"
        assert mention.type == "channel"


class TestTimestamps:
    """Tests for Discord timestamps."""

    def test_timestamp_with_datetime(self) -> None:
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = Formatter.timestamp(dt=dt, style=TimestampStyle.LONG_DATETIME)
        assert result.startswith("<t:")
        assert ":F>" in result

    def test_timestamp_with_unix_timestamp(self) -> None:
        result = Formatter.timestamp(timestamp=1704110400, style=TimestampStyle.SHORT_DATE)
        assert result == "<t:1704110400:d>"

    def test_timestamp_current_time(self) -> None:
        result = Formatter.timestamp()
        assert result.startswith("<t:")
        assert ">" in result

    def test_timestamp_all_styles(self) -> None:
        for style in TimestampStyle:
            result = Formatter.timestamp(timestamp=1704110400, style=style)
            assert f":{style.value}>" in result


class TestLinks:
    """Tests for markdown links."""

    def test_valid_link(self) -> None:
        result = Formatter.link("Click here", "https://example.com")
        assert result == "[Click here](https://example.com)"

    def test_valid_http_link(self) -> None:
        result = Formatter.link("HTTP Link", "http://example.com")
        assert result == "[HTTP Link](http://example.com)"

    def test_invalid_url_no_protocol(self) -> None:
        with pytest.raises(ValueError, match="Invalid URL"):
            Formatter.link("Bad Link", "example.com")

    def test_invalid_url_ftp(self) -> None:
        with pytest.raises(ValueError, match="Invalid URL"):
            Formatter.link("FTP Link", "ftp://example.com")


class TestQuotes:
    """Tests for quote blocks."""

    def test_single_line_quote(self) -> None:
        result = Formatter.quote("Hello")
        assert result == "> Hello"

    def test_multiline_quote(self) -> None:
        result = Formatter.quote("Line 1\nLine 2\nLine 3")
        lines = result.split("\n")
        assert lines[0] == "> Line 1"
        assert lines[1] == "> Line 2"
        assert lines[2] == "> Line 3"

    def test_multiline_quote_explicit(self) -> None:
        result = Formatter.quote("Line 1\nLine 2", multiline=True)
        lines = result.split("\n")
        assert lines[0] == ">>> Line 1"
        assert lines[1] == "> Line 2"


class TestEscape:
    """Tests for escaping special characters."""

    def test_escape_basic(self) -> None:
        result = Formatter.escape("*hello* _world_")
        assert result == "\\*hello\\* \\_world\\_"

    def test_escape_with_code(self) -> None:
        result = Formatter.escape("`code`", code=True)
        assert "\\`" in result

    def test_escape_mentions(self) -> None:
        result = Formatter.escape("@everyone @here")
        assert "\\@" in result


class TestFormatterEdgeCases:
    """Tests for edge cases and empty inputs."""

    def test_empty_string_styles(self) -> None:
        assert Formatter.bold("") == "****"
        assert Formatter.italic("") == "**"

    def test_empty_string_code_block(self) -> None:
        result = Formatter.code_block("")
        assert result == "```\n\n```"

    def test_very_long_text(self) -> None:
        long_text = "a" * 10000
        result = Formatter.bold(long_text)
        assert result.startswith("**")
        assert result.endswith("**")
        assert len(result) == len(long_text) + 4
