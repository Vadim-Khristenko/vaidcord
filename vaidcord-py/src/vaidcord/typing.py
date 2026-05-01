"""Shared typing contracts and abstractions for router APIs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Concatenate, Generic, ParamSpec, Protocol, TypeAlias, TypeVar

from vaidcord.types import Event

P = ParamSpec("P")
R = TypeVar("R")
TEvent = TypeVar("TEvent", bound=Event)
TResult = TypeVar("TResult", covariant=True)

EventHandlerResult: TypeAlias = object | None
FilterDataMap: TypeAlias = dict[str, Any]
FilterDataView: TypeAlias = Mapping[str, Any]


class EventHandler(Protocol):
    """Async router handler callable supporting DI-style kwargs."""

    def __call__(self, event: Event, /, **kwargs: Any) -> Awaitable[EventHandlerResult]: ...


class NextHandler(Protocol):
    """Middleware next callable."""

    def __call__(self, event: Event, /) -> Awaitable[EventHandlerResult]: ...


class Middleware(Protocol):
    """Async middleware callable."""

    def __call__(
        self,
        event: Event,
        next_handler: NextHandler,
        /,
    ) -> Awaitable[EventHandlerResult]: ...


InnerMiddleware = Middleware
OuterMiddleware = Middleware
LastHandler = EventHandler
LastMiddleware = Middleware
NextMiddleware = NextHandler

class DIEventCallable(Protocol[P, R]):
    """Generic callable taking Event first for DI-style wrappers."""

    def __call__(self, event: Event, /, *args: P.args, **kwargs: P.kwargs) -> R: ...


DIWrapper: TypeAlias = Callable[
    [DIEventCallable[P, Awaitable[R]]],
    Callable[Concatenate[Event, P], Awaitable[R]],
]


class AbstractEventHandler(ABC, Generic[TEvent]):
    """ABC alternative for teams that prefer class-based handlers."""

    @abstractmethod
    async def __call__(
        self, event: TEvent, /, **kwargs: Any
    ) -> EventHandlerResult: ...


class AbstractMiddleware(ABC, Generic[TEvent]):
    """ABC alternative for class-based middleware with explicit next contract."""

    @abstractmethod
    async def __call__(
        self,
        event: TEvent,
        next_handler: NextHandler,
        /,
    ) -> EventHandlerResult: ...
