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

from vaidcord.filters import (
    CommandFilter,
    CommandHelpFilter,
    CommandSettingsFilter,
    CommandStartFilter,
    FilterLike,
    as_filter,
    run_filter_with_data,
)
from vaidcord.types import ChannelType, Event, EventType

T = TypeVar("T")
Handler = Callable[[Event], Awaitable[Any]]
NextHandler = Callable[[Event], Awaitable[Any]]
Middleware = Callable[[Event, NextHandler], Awaitable[Any]]
Filter = FilterLike


@dataclass
class HandlerConfig:
    """Configuration for a registered handler."""

    handler: Handler
    event_types: list[EventType]
    filters: list[Filter] = field(default_factory=list)
    priority: int = 0


@dataclass
class MiddlewareConfig:
    """Configuration for middleware registration."""

    middleware: Middleware
    priority: int = 0
    event_types: list[EventType] | None = None


@dataclass
class RouterFilterConfig:
    """Configuration for router-level (global) filters."""

    filter_obj: Filter
    priority: int = 0
    event_types: list[EventType] | None = None


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
        self._middlewares: list[MiddlewareConfig] = []
        self._router_filters: list[RouterFilterConfig] = []

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

    def on_topic_message(
        self,
        *filters: Filter,
        priority: int = 0,
    ) -> Callable[[Handler], Handler]:
        """
        Handle message events coming from topic/thread-like channels.
        """

        async def _topic_filter(event: Event) -> bool:
            channel = event.channel or (event.message.channel if event.message else None)
            if channel is None:
                return False
            return channel.type in {
                ChannelType.PUBLIC_THREAD,
                ChannelType.PRIVATE_THREAD,
                ChannelType.NEWS_THREAD,
                ChannelType.FORUM,
            }

        return self.on_message(_topic_filter, *filters, priority=priority)

    def on_guild_message(
        self,
        *filters: Filter,
        priority: int = 0,
    ) -> Callable[[Handler], Handler]:
        """Handle only guild-bound messages."""

        async def _guild_filter(event: Event) -> bool:
            if event.guild is not None:
                return True
            if event.message is not None and event.message.guild is not None:
                return True
            return bool(event.data.get("guild_id"))

        return self.on_message(_guild_filter, *filters, priority=priority)

    def on_private_message(
        self,
        *filters: Filter,
        priority: int = 0,
    ) -> Callable[[Handler], Handler]:
        """Handle only DM/private messages."""

        async def _private_filter(event: Event) -> bool:
            channel = event.channel or (event.message.channel if event.message else None)
            if channel is None:
                return False
            return channel.type in {ChannelType.DM, ChannelType.GROUP_DM}

        return self.on_message(_private_filter, *filters, priority=priority)

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

    def on_command(
        self,
        *commands: str,
        priority: int = 0,
        prefixes: tuple[str, ...] = ("/", "!", "."),
        ignore_case: bool = True,
        filters: list[Filter] | None = None,
    ) -> Callable[[Handler], Handler]:
        """Decorator for command handlers."""
        if not commands:
            raise ValueError("on_command requires at least one command")
        command_filter = CommandFilter(
            commands=tuple(commands),
            prefixes=prefixes,
            ignore_case=ignore_case,
        )
        combined_filters = [command_filter, *(filters or [])]
        return self.on_message(*combined_filters, priority=priority)

    def on_command_start(
        self,
        *,
        priority: int = 0,
        filters: list[Filter] | None = None,
    ) -> Callable[[Handler], Handler]:
        """Shortcut for /start command."""
        return self.on_message(CommandStartFilter(), *(filters or []), priority=priority)

    def on_command_help(
        self,
        *,
        priority: int = 0,
        filters: list[Filter] | None = None,
    ) -> Callable[[Handler], Handler]:
        """Shortcut for /help command."""
        return self.on_message(CommandHelpFilter(), *(filters or []), priority=priority)

    def on_command_settings(
        self,
        *,
        priority: int = 0,
        filters: list[Filter] | None = None,
    ) -> Callable[[Handler], Handler]:
        """Shortcut for /settings command."""
        return self.on_message(
            CommandSettingsFilter(),
            *(filters or []),
            priority=priority,
        )

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

    def add_filter(
        self,
        filter_obj: Filter,
        *,
        priority: int = 0,
        event_types: list[EventType] | None = None,
    ) -> None:
        """Add a global router filter applied to all handlers."""
        config = RouterFilterConfig(
            filter_obj=filter_obj,
            priority=priority,
            event_types=event_types,
        )
        self._router_filters.append(config)
        self._router_filters.sort(key=lambda item: item.priority, reverse=True)

    def router_filter(
        self,
        *,
        priority: int = 0,
        event_types: list[EventType] | None = None,
    ) -> Callable[[Filter], Filter]:
        """Decorator to register router-level filter."""

        def decorator(filter_obj: Filter) -> Filter:
            self.add_filter(
                filter_obj=filter_obj,
                priority=priority,
                event_types=event_types,
            )
            return filter_obj

        return decorator

    def _resolve_router_filter_configs(
        self, event_type: EventType
    ) -> list[RouterFilterConfig]:
        chain: list[RouterFilterConfig] = []
        if self._parent is not None:
            chain.extend(self._parent._resolve_router_filter_configs(event_type))
        chain.extend(self._router_filters)
        return [
            item
            for item in chain
            if item.event_types is None or event_type in item.event_types
        ]

    def add_middleware(
        self,
        middleware: Middleware,
        *,
        priority: int = 0,
        event_types: list[EventType] | None = None,
    ) -> None:
        """Register an event middleware for this router tree."""
        config = MiddlewareConfig(
            middleware=middleware,
            priority=priority,
            event_types=event_types,
        )
        self._middlewares.append(config)
        self._middlewares.sort(key=lambda item: item.priority, reverse=True)

    def middleware(
        self,
        *,
        priority: int = 0,
        event_types: list[EventType] | None = None,
    ) -> Callable[[Middleware], Middleware]:
        """Decorator to register middleware."""

        def decorator(middleware: Middleware) -> Middleware:
            self.add_middleware(
                middleware,
                priority=priority,
                event_types=event_types,
            )
            return middleware

        return decorator

    def _resolve_middleware_configs(
        self, event_type: EventType
    ) -> list[MiddlewareConfig]:
        chain: list[MiddlewareConfig] = []
        if self._parent is not None:
            chain.extend(self._parent._resolve_middleware_configs(event_type))
        chain.extend(self._middlewares)
        return [
            item
            for item in chain
            if item.event_types is None or event_type in item.event_types
        ]

    def _resolve_middleware_chain(self, event_type: EventType) -> list[Middleware]:
        configs = self._resolve_middleware_configs(event_type)
        return [item.middleware for item in configs]

    async def _execute_with_middlewares(
        self,
        event: Event,
        handler: Handler,
    ) -> Any:
        async def call(index: int, current_event: Event) -> Any:
            if index >= len(chain):
                return await handler(current_event)
            middleware = chain[index]
            return await middleware(current_event, lambda next_event: call(index + 1, next_event))

        chain = self._resolve_middleware_chain(event.type)
        return await call(0, event)

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
        skipped = object()

        # Process handlers from child routers first
        for router in self._routers:
            router_result = await router.propagate_event(event)
            if router_result is not None:
                result = router_result

        # Process handlers in this router
        handlers = self._handlers.get(event.type, [])
        router_filters = [
            item.filter_obj for item in self._resolve_router_filter_configs(event.type)
        ]
        for config in handlers:
            async def guarded_handler(current_event: Event) -> Any:
                filter_data: dict[str, Any] = {}
                for filter_func in [*router_filters, *config.filters]:
                    try:
                        passed, data = await run_filter_with_data(filter_func, current_event)
                        if data:
                            filter_data.update(data)
                        if not passed:
                            return skipped
                    except Exception:
                        return skipped
                if filter_data:
                    current_event.context.setdefault("filter_data", {}).update(filter_data)
                return await config.handler(current_event)

            try:
                current_result = await self._execute_with_middlewares(event, guarded_handler)
                if current_result is not skipped:
                    result = current_result
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

    @staticmethod
    def state_filter(*states: str, scope: str = "member") -> Filter:
        """
        Build a filter that checks `event.context['fsm']` state.
        """
        state_set = {state for state in states}

        async def _filter(event: Event) -> bool:
            if scope == "primary":
                fsm = event.context.get("fsm")
            else:
                fsm_map = event.context.get("fsm_map", {})
                fsm = fsm_map.get(scope)
            if fsm is None:
                return False
            current_state = await fsm.get_state()
            return current_state in state_set

        return _filter

    @staticmethod
    async def check_filter(event: Event, filter_obj: Filter) -> bool:
        """Utility for middlewares: evaluate any filter type against an event."""
        return await as_filter(filter_obj)(event)

    def on_message_state(
        self,
        *states: str,
        priority: int = 0,
        filters: list[Filter] | None = None,
        scope: str = "member",
    ) -> Callable[[Handler], Handler]:
        """
        Decorator that handles only MESSAGE_CREATE events in specific FSM states.
        """
        combined_filters = [self.state_filter(*states, scope=scope), *(filters or [])]
        return self.on_message(*combined_filters, priority=priority)

    def __repr__(self) -> str:
        return f"<Router name='{self.name}' handlers={sum(len(h) for h in self._handlers.values())}>"
