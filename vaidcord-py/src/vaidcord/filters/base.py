from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias

from vaidcord.types import Event

FilterResult: TypeAlias = bool | dict[str, Any] | Awaitable[bool | dict[str, Any]]
FilterCallable: TypeAlias = Callable[[Event], FilterResult]


class BaseFilter:
    async def __call__(self, event: Event) -> bool | dict[str, Any]:
        raise NotImplementedError

    def __and__(self, other: FilterLike) -> FilterExpr:
        return as_filter(self).__and__(other)

    def __or__(self, other: FilterLike) -> FilterExpr:
        return as_filter(self).__or__(other)

    def __invert__(self) -> FilterExpr:
        return ~as_filter(self)


class SupportsFilter(Protocol):
    def __call__(self, event: Event) -> FilterResult: ...




def _invoke_filter_callable(filter_obj: SupportsFilter | FilterCallable, event: Event) -> FilterResult:
    try:
        signature = inspect.signature(filter_obj)
    except (TypeError, ValueError):
        return filter_obj(event)

    params = signature.parameters
    if "bot" in params:
        return filter_obj(event, bot=event.bot)
    if "event" in params:
        return filter_obj(event=event)
    return filter_obj(event)

async def run_filter(filter_obj: SupportsFilter | FilterCallable, event: Event) -> bool:
    result = _invoke_filter_callable(filter_obj, event)
    if inspect.isawaitable(result):
        result = await result
    return True if isinstance(result, dict) else bool(result)


async def run_filter_with_data(
    filter_obj: SupportsFilter | FilterCallable,
    event: Event,
) -> tuple[bool, dict[str, Any]]:
    result = _invoke_filter_callable(filter_obj, event)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, dict):
        return True, result
    return bool(result), {}


def _to_pass_and_data(result: bool | dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    if isinstance(result, dict):
        return True, result
    return bool(result), {}


@dataclass(frozen=True)
class FilterExpr:
    callback: FilterCallable

    async def __call__(self, event: Event) -> bool | dict[str, Any]:
        result = self.callback(event)
        if inspect.isawaitable(result):
            result = await result
        return result

    def __and__(self, other: FilterLike) -> FilterExpr:
        other_expr = as_filter(other)

        async def _and(event: Event) -> bool | dict[str, Any]:
            left = await self(event)
            lp, ld = _to_pass_and_data(left)
            if not lp:
                return False
            right = await other_expr(event)
            rp, rd = _to_pass_and_data(right)
            if not rp:
                return False
            merged = {**ld, **rd}
            return merged or True

        return FilterExpr(_and)

    def __or__(self, other: FilterLike) -> FilterExpr:
        other_expr = as_filter(other)

        async def _or(event: Event) -> bool | dict[str, Any]:
            left = await self(event)
            lp, ld = _to_pass_and_data(left)
            if lp:
                return ld or True
            right = await other_expr(event)
            rp, rd = _to_pass_and_data(right)
            return rd or True if rp else False

        return FilterExpr(_or)

    def __invert__(self) -> FilterExpr:
        async def _not(event: Event) -> bool:
            return not await self(event)

        return FilterExpr(_not)


FilterLike: TypeAlias = FilterExpr | SupportsFilter | FilterCallable


def as_filter(filter_like: FilterLike) -> FilterExpr:
    if isinstance(filter_like, FilterExpr):
        return filter_like

    async def _cb(event: Event) -> bool | dict[str, Any]:
        result = _invoke_filter_callable(filter_like, event)
        if inspect.isawaitable(result):
            result = await result
        return result

    return FilterExpr(_cb)
