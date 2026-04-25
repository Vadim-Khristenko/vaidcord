"""
Powerful filter system inspired by Aiogram-style filtering.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias

from vaidcord.types import Event

FilterResult: TypeAlias = bool | dict[str, Any] | Awaitable[bool | dict[str, Any]]
FilterCallable: TypeAlias = Callable[[Event], FilterResult]


class SupportsFilter(Protocol):
    """Protocol for filter objects."""

    def __call__(self, event: Event) -> FilterResult: ...


def _resolve_path(event: Event, path: str, default: Any = None) -> Any:
    current: Any = event
    for part in path.split("."):
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(part, default)
        else:
            current = getattr(current, part, default)
    return current


async def run_filter(filter_obj: SupportsFilter | FilterCallable, event: Event) -> bool:
    """Run sync or async filter callables uniformly."""
    result = filter_obj(event)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, dict):
        return True
    return bool(result)


async def run_filter_with_data(
    filter_obj: SupportsFilter | FilterCallable,
    event: Event,
) -> tuple[bool, dict[str, Any]]:
    """
    Run filter and capture propagated data.

    Aiogram-like behavior: dict means "filter passed + inject data".
    """
    result = filter_obj(event)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, dict):
        return True, result
    return bool(result), {}


@dataclass(frozen=True)
class FilterExpr:
    """Composable filter expression (`&`, `|`, `~`)."""

    callback: FilterCallable

    async def __call__(self, event: Event) -> bool:
        return await run_filter(self.callback, event)

    def __and__(self, other: FilterLike) -> FilterExpr:
        other_expr = as_filter(other)

        async def _and(event: Event) -> bool:
            return await self(event) and await other_expr(event)

        return FilterExpr(_and)

    def __or__(self, other: FilterLike) -> FilterExpr:
        other_expr = as_filter(other)

        async def _or(event: Event) -> bool:
            return await self(event) or await other_expr(event)

        return FilterExpr(_or)

    def __invert__(self) -> FilterExpr:
        async def _not(event: Event) -> bool:
            return not await self(event)

        return FilterExpr(_not)


FilterLike: TypeAlias = FilterExpr | SupportsFilter | FilterCallable


def as_filter(filter_like: FilterLike) -> FilterExpr:
    """Convert any supported filter type to composable FilterExpr."""
    if isinstance(filter_like, FilterExpr):
        return filter_like

    async def _cb(event: Event) -> bool:
        return await run_filter(filter_like, event)

    return FilterExpr(_cb)


class MagicFilter:
    """Attribute-path driven filter builder similar to aiogram's magic filters."""

    def __init__(self, path: str = "") -> None:
        self._path = path
        self._modifier: Callable[[Any], Any] | None = None

    def __getattr__(self, name: str) -> MagicFilter:
        path = f"{self._path}.{name}" if self._path else name
        return MagicFilter(path)

    def _with_modifier(self, modifier: Callable[[Any], Any]) -> MagicFilter:
        result = MagicFilter(self._path)
        result._modifier = modifier
        return result

    def _extract(self, event: Event) -> Any:
        value = _resolve_path(event, self._path)
        if self._modifier is not None:
            try:
                return self._modifier(value)
            except Exception:
                return None
        return value

    async def __call__(self, event: Event) -> bool:
        return bool(self._extract(event))

    def resolve(self, event: Event) -> Any:
        return self._extract(event)

    def _cmp(self, op: Callable[[Any], bool]) -> FilterExpr:
        async def _filter(event: Event) -> bool:
            return op(self._extract(event))

        return FilterExpr(_filter)

    def __eq__(self, value: Any) -> FilterExpr:  # type: ignore[override]
        return self.equals(value)

    def __ne__(self, value: Any) -> FilterExpr:  # type: ignore[override]
        return self._cmp(lambda current: current != value)

    def __lt__(self, value: Any) -> FilterExpr:
        return self._cmp(lambda current: current is not None and current < value)

    def __le__(self, value: Any) -> FilterExpr:
        return self._cmp(lambda current: current is not None and current <= value)

    def __gt__(self, value: Any) -> FilterExpr:
        return self._cmp(lambda current: current is not None and current > value)

    def __ge__(self, value: Any) -> FilterExpr:
        return self._cmp(lambda current: current is not None and current >= value)

    def __matmul__(self, values: Iterable[Any]) -> FilterExpr:
        return self.in_(values)

    def equals(self, value: Any) -> FilterExpr:
        return self._cmp(lambda current: current == value)

    def contains(self, value: Any) -> FilterExpr:
        return self._cmp(lambda current: current is not None and value in current)

    def startswith(self, prefix: str) -> FilterExpr:
        return self._cmp(lambda current: isinstance(current, str) and current.startswith(prefix))

    def endswith(self, suffix: str) -> FilterExpr:
        return self._cmp(lambda current: isinstance(current, str) and current.endswith(suffix))

    def regex(self, pattern: str, flags: int = 0) -> FilterExpr:
        regex = re.compile(pattern, flags)
        return self._cmp(lambda current: isinstance(current, str) and regex.search(current) is not None)

    def regexp(self, pattern: str, flags: int = 0) -> FilterExpr:
        """Alias used in aiogram docs."""
        return self.regex(pattern, flags=flags)

    def in_(self, values: Iterable[Any]) -> FilterExpr:
        value_set = set(values)
        return self._cmp(lambda current: current in value_set)

    def func(self, callback: Callable[[Any], bool]) -> FilterExpr:
        return self._cmp(lambda current: callback(current))

    def lower(self) -> MagicFilter:
        return self._with_modifier(
            lambda current: current.lower() if isinstance(current, str) else None
        )

    def upper(self) -> MagicFilter:
        return self._with_modifier(
            lambda current: current.upper() if isinstance(current, str) else None
        )

    def len(self) -> MagicFilter:
        return self._with_modifier(lambda current: len(current) if current is not None else 0)


F = MagicFilter()


@dataclass(frozen=True)
class CustomFilter:
    """Adapter for user-defined callable filters."""

    callback: FilterCallable

    async def __call__(self, event: Event) -> bool:
        return await run_filter(self.callback, event)


@dataclass(frozen=True)
class CommandFilter:
    """Filter for command messages."""

    commands: tuple[str, ...]
    prefixes: tuple[str, ...] = ("/", "!", ".")
    ignore_case: bool = True
    path: str = "message.content"

    async def __call__(self, event: Event) -> bool:
        text = _resolve_path(event, self.path, "")
        if not isinstance(text, str) or not text:
            return False

        command_token = text.strip().split(" ", 1)[0]
        for prefix in self.prefixes:
            if command_token.startswith(prefix):
                name = command_token[len(prefix) :]
                if "@" in name:
                    name = name.split("@", 1)[0]
                candidate = name.lower() if self.ignore_case else name
                command_set = (
                    {cmd.lower() for cmd in self.commands}
                    if self.ignore_case
                    else set(self.commands)
                )
                return candidate in command_set
        return False


class CommandStartFilter(CommandFilter):
    def __init__(self) -> None:
        super().__init__(commands=("start",))


class CommandHelpFilter(CommandFilter):
    def __init__(self) -> None:
        super().__init__(commands=("help",))


class CommandSettingsFilter(CommandFilter):
    def __init__(self) -> None:
        super().__init__(commands=("settings",))


@dataclass(frozen=True)
class RegexFilter:
    """Regex based filter for text fields."""

    pattern: str
    flags: int = 0
    path: str = "message.content"

    async def __call__(self, event: Event) -> bool:
        text = _resolve_path(event, self.path, "")
        if not isinstance(text, str):
            return False
        return re.search(self.pattern, text, self.flags) is not None


@dataclass(frozen=True)
class UserFilter:
    """User-based filter."""

    user_ids: set[int] | None = None
    usernames: set[str] | None = None
    allow_bots: bool | None = None

    async def __call__(self, event: Event) -> bool:
        user = event.user or (event.message.author if event.message else None)
        if user is None:
            return False
        if self.user_ids is not None and user.id not in self.user_ids:
            return False
        if self.usernames is not None and user.username not in self.usernames:
            return False
        if self.allow_bots is not None and user.bot != self.allow_bots:
            return False
        return True
