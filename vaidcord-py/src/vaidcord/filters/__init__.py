"""Powerful filter system inspired by Aiogram-style filtering."""

from .base import (
    BaseFilter,
    FilterCallable,
    FilterExpr,
    FilterLike,
    FilterResult,
    SupportsFilter,
    as_filter,
    run_filter,
    run_filter_with_data,
)
from .builtin import (
    CommandFilter,
    CommandHelpFilter,
    CommandSettingsFilter,
    CommandStartFilter,
    CustomFilter,
    RegexFilter,
    UserFilter,
)
from .magic import BotFilter, ChatTypeFilter, F, MagicData, MagicFilter

__all__ = [
    "BaseFilter",
    "FilterCallable",
    "FilterExpr",
    "FilterLike",
    "FilterResult",
    "SupportsFilter",
    "as_filter",
    "run_filter",
    "run_filter_with_data",
    "CommandFilter",
    "CommandHelpFilter",
    "CommandSettingsFilter",
    "CommandStartFilter",
    "CustomFilter",
    "RegexFilter",
    "UserFilter",
    "MagicFilter",
    "BotFilter",
    "MagicData",
    "ChatTypeFilter",
    "F",
]
