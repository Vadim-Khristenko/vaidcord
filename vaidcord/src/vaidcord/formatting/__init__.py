"""
Discord Formatting Utilities.

Provides comprehensive support for Discord's formatting syntax including:
- Bold, italic, underline, strikethrough
- Spoilers, code blocks (inline and multi-line)
- Mentions (users, roles, channels)
- Timestamps with various formats
- Links, quotes, and more
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Final


class TextStyle(Enum):
    """Text style options for Discord formatting."""

    BOLD = "**"
    ITALIC = "*"
    UNDERLINE = "__"
    STRIKETHROUGH = "~~"
    SPOILER = "||"


class CodeBlockLanguage(Enum):
    """Common code block languages supported by Discord."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JSON = "json"
    YAML = "yaml"
    SQL = "sql"
    BASH = "bash"
    DIFF = "diff"
    HTML = "html"
    CSS = "css"
    NONE = ""


class TimestampStyle(Enum):
    """Discord timestamp format styles."""

    SHORT_TIME = "t"  # 16:20
    LONG_TIME = "T"  # 16:20:30
    SHORT_DATE = "d"  # 20/04/2021
    LONG_DATE = "D"  # 20 April 2021
    SHORT_DATETIME = "f"  # 20 April 2021 16:20
    LONG_DATETIME = "F"  # Tuesday, 20 April 2021 16:20
    RELATIVE = "R"  # 2 months ago


@dataclass(frozen=True)
class Mention:
    """Represents a Discord mention."""

    id: int
    type: str  # 'user', 'role', 'channel'

    def __str__(self) -> str:
        if self.type == "user":
            return f"<@{self.id}>"
        elif self.type == "role":
            return f"<@&{self.id}>"
        elif self.type == "channel":
            return f"<#{self.id}>"
        else:
            return f"<@{self.id}>"


class Formatter:
    """
    Utility class for Discord text formatting.

    This class provides static methods for all common Discord formatting operations,
    designed for maximum performance and ease of use.
    """

    # Precompiled regex patterns for validation
    _URL_PATTERN: Final = re.compile(
        r"https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}"
        r"\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)"
    )

    @staticmethod
    def bold(text: str) -> str:
        """Make text bold."""
        return f"**{text}**"

    @staticmethod
    def italic(text: str) -> str:
        """Make text italic."""
        return f"*{text}*"

    @staticmethod
    def underline(text: str) -> str:
        """Underline text."""
        return f"__{text}__"

    @staticmethod
    def strikethrough(text: str) -> str:
        """Add strikethrough to text."""
        return f"~~{text}~~"

    @staticmethod
    def spoiler(text: str) -> str:
        """Hide text as a spoiler."""
        return f"||{text}||"

    @staticmethod
    def inline_code(text: str) -> str:
        """Format text as inline code."""
        # Escape backticks in the text
        escaped = text.replace("`", "\\`")
        return f"`{escaped}`"

    @staticmethod
    def code_block(
        code: str, language: CodeBlockLanguage | str = CodeBlockLanguage.NONE
    ) -> str:
        """
        Create a multi-line code block.

        Args:
            code: The code to format
            language: Programming language for syntax highlighting
        """
        lang_value = (
            language.value if isinstance(language, CodeBlockLanguage) else language
        )
        # Escape triple backticks in the code
        escaped = code.replace("```", "\\`\\`\\`")
        return f"```{lang_value}\n{escaped}\n```"

    @staticmethod
    def combine_styles(text: str, *styles: TextStyle) -> str:
        """
        Apply multiple text styles to text.

        Args:
            text: The text to style
            *styles: Variable number of TextStyle enums

        Example:
            Formatter.combine_styles("text", TextStyle.BOLD, TextStyle.ITALIC)
            Returns: "***text***"
        """
        result = text
        for style in styles:
            if style == TextStyle.BOLD:
                result = f"**{result}**"
            elif style == TextStyle.ITALIC:
                result = f"*{result}*"
            elif style == TextStyle.UNDERLINE:
                result = f"__{result}__"
            elif style == TextStyle.STRIKETHROUGH:
                result = f"~~{result}~~"
            elif style == TextStyle.SPOILER:
                result = f"||{result}||"
        return result

    @staticmethod
    def mention_user(user_id: int) -> str:
        """Create a user mention."""
        return f"<@{user_id}>"

    @staticmethod
    def mention_role(role_id: int) -> str:
        """Create a role mention."""
        return f"<@&{role_id}>"

    @staticmethod
    def mention_channel(channel_id: int) -> str:
        """Create a channel mention."""
        return f"<#{channel_id}>"

    @staticmethod
    def timestamp(
        dt: datetime | None = None,
        timestamp: int | None = None,
        style: TimestampStyle = TimestampStyle.LONG_DATETIME,
    ) -> str:
        """
        Create a Discord timestamp.

        Args:
            dt: datetime object (alternative to timestamp)
            timestamp: Unix timestamp in seconds (alternative to dt)
            style: TimestampStyle enum for formatting

        Returns:
            Formatted timestamp string like <t:1234567890:F>
        """
        if dt is not None:
            ts = int(dt.timestamp())
        elif timestamp is not None:
            ts = timestamp
        else:
            ts = int(datetime.now().timestamp())

        return f"<t:{ts}:{style.value}>"

    @staticmethod
    def link(text: str, url: str) -> str:
        """
        Create a markdown link.

        Args:
            text: Display text
            url: URL (must start with http:// or https://)
        """
        if not Formatter._URL_PATTERN.match(url):
            raise ValueError("Invalid URL. Must start with http:// or https://")
        return f"[{text}]({url})"

    @staticmethod
    def quote(text: str, multiline: bool = False) -> str:
        """
        Create a quote block.

        Args:
            text: Text to quote
            multiline: If True, creates a multi-line quote block
        """
        if multiline:
            lines = text.split("\n")
            return "\n".join(f">>> {line}" if i == 0 else f"> {line}" for i, line in enumerate(lines))
        else:
            lines = text.split("\n")
            return "\n".join(f"> {line}" for line in lines)

    @staticmethod
    def escape(text: str, *, code: bool = False) -> str:
        """
        Escape special Discord markdown characters.

        Args:
            text: Text to escape
            code: If True, also escapes backticks for use in code blocks
        """
        special_chars = "*_~`|@"
        if code:
            special_chars += "\\"
        result = text
        for char in special_chars:
            result = result.replace(char, f"\\{char}")
        return result

    @staticmethod
    def user_mention_from_obj(user_id: int) -> Mention:
        """Create a Mention object from a user ID."""
        return Mention(id=user_id, type="user")

    @staticmethod
    def role_mention_from_obj(role_id: int) -> Mention:
        """Create a Mention object from a role ID."""
        return Mention(id=role_id, type="role")

    @staticmethod
    def channel_mention_from_obj(channel_id: int) -> Mention:
        """Create a Mention object from a channel ID."""
        return Mention(id=channel_id, type="channel")
