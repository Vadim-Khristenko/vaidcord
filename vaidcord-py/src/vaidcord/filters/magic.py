from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from vaidcord.types import ChannelType, Event
from .base import BaseFilter, FilterExpr, FilterLike, as_filter


def _resolve_path(event: Event, path: str, default: Any = None) -> Any:
    current: Any = event
    for part in path.split('.'):
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(part, default)
        else:
            current = getattr(current, part, default)
    return current


class MagicFilter:
    def __init__(self, path: str = '', *, selector: str | None = None) -> None:
        self._path = path
        self._selector = selector
        self._modifier: Callable[[Any], Any] | None = None

    def __getattr__(self, name: str) -> MagicFilter:
        path = f"{self._path}.{name}" if self._path else name
        return MagicFilter(path, selector=self._selector)

    def __getitem__(self, item: Any) -> MagicFilter:
        if item is Ellipsis:
            return MagicFilter(self._path, selector='any')
        if isinstance(item, slice) and item.start is None and item.stop is None and item.step is None:
            return MagicFilter(self._path, selector='all')
        path = f"{self._path}.{item}" if self._path else str(item)
        return MagicFilter(path, selector=self._selector)

    def _with_modifier(self, modifier: Callable[[Any], Any]) -> MagicFilter:
        mf = MagicFilter(self._path, selector=self._selector)
        mf._modifier = modifier
        return mf

    def _extract(self, event: Event) -> Any:
        val = _resolve_path(event, self._path)
        if self._modifier is None:
            return val
        try:
            return self._modifier(val)
        except Exception:
            return None

    def _cmp(self, op: Callable[[Any], bool]) -> FilterExpr:
        async def _f(event: Event) -> bool:
            current = self._extract(event)
            if self._selector == 'any':
                return isinstance(current, list) and any(op(x) for x in current)
            if self._selector == 'all':
                return isinstance(current, list) and all(op(x) for x in current)
            return op(current)

        return FilterExpr(_f)

    def __call__(self, event: Event) -> bool:
        return bool(self._extract(event))

    def __eq__(self, value: Any) -> FilterExpr:  # type: ignore[override]
        return self._cmp(lambda current: current == value)
    def __ne__(self, value: Any) -> FilterExpr:  # type: ignore[override]
        return self._cmp(lambda current: current != value)
    def __gt__(self, value: Any) -> FilterExpr:
        return self._cmp(lambda current: current is not None and current > value)
    def __ge__(self, value: Any) -> FilterExpr:
        return self._cmp(lambda current: current is not None and current >= value)
    def __lt__(self, value: Any) -> FilterExpr:
        return self._cmp(lambda current: current is not None and current < value)
    def __le__(self, value: Any) -> FilterExpr:
        return self._cmp(lambda current: current is not None and current <= value)

    def in_(self, values: Iterable[Any]) -> FilterExpr: return self._cmp(lambda current: current in set(values))
    def not_in(self, values: Iterable[Any]) -> FilterExpr: return self._cmp(lambda current: current not in set(values))
    def contains(self, value: Any) -> FilterExpr: return self._cmp(lambda current: current is not None and value in current)
    def exists(self) -> FilterExpr: return self._cmp(lambda current: current is not None)
    def is_(self, value: Any) -> FilterExpr: return self._cmp(lambda current: current is value)
    def is_not(self, value: Any) -> FilterExpr: return self._cmp(lambda current: current is not value)
    def cast(self, caster: Callable[[Any], Any]) -> MagicFilter: return self._with_modifier(lambda c: caster(c) if c is not None else None)
    def map(self, mapper: Callable[[Any], Any]) -> MagicFilter: return self._with_modifier(mapper)
    def lower(self) -> MagicFilter: return self._with_modifier(lambda c: c.lower() if isinstance(c, str) else None)
    def upper(self) -> MagicFilter: return self._with_modifier(lambda c: c.upper() if isinstance(c, str) else None)
    def len(self) -> MagicFilter: return self._with_modifier(lambda c: len(c) if c is not None else 0)

    def regex(self, pattern: str, flags: int = 0) -> FilterExpr:
        rgx = re.compile(pattern, flags)
        async def _f(event: Event) -> bool | dict[str, Any]:
            current = self._extract(event)
            if not isinstance(current, str):
                return False
            m = rgx.search(current)
            return {"regex_match": m, "regex_groups": m.groupdict()} if m else False
        return FilterExpr(_f)

    def bot_id_in(self, bot_ids: Iterable[int]) -> FilterExpr:
        return self._cmp(lambda current: getattr(current, "id", None) in set(bot_ids))

    def bot_username_in(self, usernames: Iterable[str]) -> FilterExpr:
        normalized = {u.lower() for u in usernames}
        return self._cmp(lambda current: str(getattr(current, "username", "")).lower() in normalized)

    def as_(self, name: str) -> FilterExpr:
        async def _f(event: Event) -> bool | dict[str, Any]:
            current = self._extract(event)
            return {name: current} if current is not None else False
        return FilterExpr(_f)


@dataclass(frozen=True)
class MagicData(BaseFilter):
    expr: FilterLike

    async def __call__(self, event: Event) -> bool | dict[str, Any]:
        payload = {**event.data, **event.context}
        shadow = Event(type=event.type, data=payload, guild=event.guild, channel=event.channel, user=event.user, message=event.message, interaction=event.interaction, raw_data=event.raw_data, bot=event.bot, context=event.context)
        return await as_filter(self.expr)(shadow)


@dataclass(frozen=True)
class ChatTypeFilter(BaseFilter):
    chat_type: ChannelType | str | list[ChannelType | str]

    async def __call__(self, event: Event) -> bool:
        channel = event.channel or (event.message.channel if event.message else None)
        if channel is None:
            return False
        expected = self.chat_type
        if isinstance(expected, list):
            names = {x.name.lower() if isinstance(x, ChannelType) else str(x).lower() for x in expected}
            return channel.type.name.lower() in names or str(channel.type.value) in names
        if isinstance(expected, ChannelType):
            return channel.type == expected
        return channel.type.name.lower() == str(expected).lower() or str(channel.type.value) == str(expected)


@dataclass(frozen=True)
class BotFilter(BaseFilter):
    """Filter for multi-bot scenarios."""

    bot_ids: set[int] | None = None
    bot_usernames: set[str] | None = None

    async def __call__(self, event: Event, bot: Any = None) -> bool:
        bot_obj = bot or event.bot
        if bot_obj is None:
            return False
        bot_id = getattr(bot_obj, "id", None)
        bot_username = getattr(bot_obj, "username", None)
        if self.bot_ids is not None and bot_id not in self.bot_ids:
            return False
        if self.bot_usernames is not None and bot_username not in self.bot_usernames:
            return False
        return True


F = MagicFilter()
