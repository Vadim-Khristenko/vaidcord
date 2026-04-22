"""
Router system for VaidCord.

Inspired by Aiogram 3.x routers, this module provides a flexible way to organize
bot handlers into modular components.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from vaidcord.types import Event, EventType

T = TypeVar("T")
Handler = Callable[[Event], Awaitable[Any]]
Filter = Callable[[Event], Awaitable[bool]]


@dataclass
class HandlerConfig:
    """Configuration for a registered handler."""

    handler: Handler
    event_types: list[EventType]
    filters: list[Filter] = field(default_factory=list)
    priority: int = 0


class Router:
    """
    Router for organizing bot handlers.

    Routers allow you to split your bot's logic into separate modules,
    similar to blueprints in Flask or routers in FastAPI.

    Example:
        router = Router(name="commands")

        @router.on_message()
        async def handle_message(event: Event):
            await event.message.channel.send("Hello!")
    """

    def __init__(self, name: str | None = None) -> None:
        self.name = name or f"router_{id(self)}"
        self._handlers: dict[EventType, list[HandlerConfig]] = defaultdict(list)
        self._routers: list[Router] = []
        self._parent: Router | None = None

    def _resolve_event_types(self, *event_types: EventType | str) -> list[EventType]:
        """Resolve event types from arguments."""
        result = []
        for et in event_types:
            if isinstance(et, EventType):
                result.append(et)
            elif isinstance(et, str):
                try:
                    result.append(EventType[et.upper()])
                except KeyError as e:
                    raise ValueError(f"Unknown event type: {et}") from e
            else:
                raise TypeError(f"Invalid event type: {type(et)}")
        return result

    def register_handler(
        self,
        handler: Handler,
        *event_types: EventType | str,
        filters: list[Filter] | None = None,
        priority: int = 0,
    ) -> None:
        """
        Register a handler for specific event types.

        Args:
            handler: The async handler function
            *event_types: Event types to handle
            filters: Optional list of filter functions
            priority: Handler priority (higher = executed first)
        """
        resolved_types = self._resolve_event_types(*event_types)
        config = HandlerConfig(
            handler=handler,
            event_types=resolved_types,
            filters=filters or [],
            priority=priority,
        )

        for event_type in resolved_types:
            self._handlers[event_type].append(config)
            # Sort by priority (descending)
            self._handlers[event_type].sort(key=lambda x: x.priority, reverse=True)

    def on_message(
        self,
        *filters: Filter,
        priority: int = 0,
    ) -> Callable[[Handler], Handler]:
        """
        Decorator to register a message handler.

        Args:
            *filters: Filter functions to apply
            priority: Handler priority

        Example:
            @router.on_message()
            async def handle_message(event: Event):
                ...
        """

        def decorator(handler: Handler) -> Handler:
            self.register_handler(
                handler,
                EventType.MESSAGE_CREATE,
                filters=list(filters),
                priority=priority,
            )
            return handler

        return decorator

    def on_event(
        self,
        *event_types: EventType | str,
        filters: list[Filter] | None = None,
        priority: int = 0,
    ) -> Callable[[Handler], Handler]:
        """
        Decorator to register a handler for specific event types.

        Args:
            *event_types: Event types to handle
            filters: Filter functions to apply
            priority: Handler priority

        Example:
            @router.on_event(EventType.GUILD_CREATE)
            async def handle_guild_join(event: Event):
                ...
        """

        def decorator(handler: Handler) -> Handler:
            self.register_handler(
                handler,
                *event_types,
                filters=filters,
                priority=priority,
            )
            return handler

        return decorator

    def include_router(self, router: Router) -> None:
        """
        Include another router into this one.

        This allows for nested router structures and better organization.

        Args:
            router: Router to include
        """
        if router is self:
            raise ValueError("Cannot include router into itself")
        if router._parent is not None:
            raise ValueError(
                f"Router '{router.name}' is already included in another router"
            )

        router._parent = self
        self._routers.append(router)

    async def propagate_event(self, event: Event) -> Any:
        """
        Propagate an event through all registered handlers.

        This method is called by the Dispatcher to process events.

        Args:
            event: The event to process

        Returns:
            The result of the last executed handler, or None
        """
        result = None

        # Process handlers from child routers first
        for router in self._routers:
            router_result = await router.propagate_event(event)
            if router_result is not None:
                result = router_result

        # Process handlers in this router
        handlers = self._handlers.get(event.type, [])
        for config in handlers:
            # Check all filters
            should_execute = True
            for filter_func in config.filters:
                try:
                    if not await filter_func(event):
                        should_execute = False
                        break
                except Exception:
                    should_execute = False
                    break

            if should_execute:
                try:
                    result = await config.handler(event)
                except Exception as e:
                    # In production, you'd want to log this properly
                    print(f"Error in handler {config.handler.__name__}: {e}")
                    raise

        return result

    def get_handlers(self, event_type: EventType) -> list[HandlerConfig]:
        """Get all handlers for a specific event type."""
        return self._handlers.get(event_type, [])

    def clear_handlers(self, event_type: EventType | None = None) -> None:
        """
        Clear handlers.

        Args:
            event_type: Specific event type to clear, or None to clear all
        """
        if event_type is None:
            self._handlers.clear()
        else:
            self._handlers.pop(event_type, None)

    def __repr__(self) -> str:
        return f"<Router name='{self.name}' handlers={sum(len(h) for h in self._handlers.values())}>"
