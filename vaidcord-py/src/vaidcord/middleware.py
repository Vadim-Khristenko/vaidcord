from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, Protocol

from vaidcord.types import Event

MiddlewareData = MutableMapping[str, Any]
MiddlewareHandler = Callable[[Event, MiddlewareData], Awaitable[Any]]


class SupportsMiddleware(Protocol):
    async def __call__(self, event: Event, next_handler: Callable[[Event], Awaitable[Any]]) -> Any: ...


class BaseMiddleware(ABC):
    """Base class for class-based middleware objects."""

    @abstractmethod
    async def __call__(
        self,
        handler: MiddlewareHandler,
        event: Event,
        data: MiddlewareData,
    ) -> Any:
        """Unified class-based middleware contract."""
        raise NotImplementedError
