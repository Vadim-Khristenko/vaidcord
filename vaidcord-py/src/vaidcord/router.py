"""
Router system for VaidCord.

Inspired by Aiogram 3.x routers, this module provides a flexible way to organize
bot handlers into modular components.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
import inspect
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
from vaidcord.middleware import BaseMiddleware
from vaidcord.types import ChannelType, Event, EventType
from vaidcord.typing import (
    EventHandler,
    EventHandlerResult,
    FilterDataMap,
    Middleware,
    NextHandler,
)

T = TypeVar("T")

LifecycleHandler = Callable[[], Awaitable[None]]
Filter = FilterLike


@dataclass
class HandlerConfig:
    """Configuration for a registered handler."""

    handler: EventHandler
    event_types: list[EventType]
    filters: list[Filter] = field(default_factory=list)
    priority: int = 0
    accepted_kwargs: set[str] = field(default_factory=set)


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


class StopPropagation(Exception):
    """Signal to stop event propagation from middleware or handlers."""


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
        self._outer_middlewares: list[MiddlewareConfig] = []
        self._router_filters: list[RouterFilterConfig] = []
        self._dependencies: dict[str, Any] = {}
        self._startup_handlers: list[LifecycleHandler] = []
        self._shutdown_handlers: list[LifecycleHandler] = []
        self._reconnect_handlers: list[LifecycleHandler] = []

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
        handler: EventHandler,
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
            accepted_kwargs=self._extract_accepted_kwargs(handler),
        )

        for event_type in resolved_types:
            self._handlers[event_type].append(config)
            # Sort by priority (descending)
            self._handlers[event_type].sort(key=lambda x: x.priority, reverse=True)

    def on_message(
        self,
        *filters: Filter,
        priority: int = 0,
    ) -> Callable[[EventHandler], EventHandler]:
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

        def decorator(handler: EventHandler) -> EventHandler:
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
    ) -> Callable[[EventHandler], EventHandler]:
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
    ) -> Callable[[EventHandler], EventHandler]:
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
    ) -> Callable[[EventHandler], EventHandler]:
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
    ) -> Callable[[EventHandler], EventHandler]:
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

        def decorator(handler: EventHandler) -> EventHandler:
            self.register_handler(
                handler,
                *event_types,
                filters=filters,
                priority=priority,
            )
            return handler

        return decorator


    def on_gateway_event(
        self,
        event_name: str,
        *filters: Filter,
        priority: int = 0,
    ) -> Callable[[EventHandler], EventHandler]:
        return self.on_event(event_name, filters=list(filters), priority=priority)

    def _event_shortcut(
        self,
        event_type: EventType,
        *filters: Filter,
        priority: int = 0,
    ) -> Callable[[EventHandler], EventHandler]:
        return self.on_event(event_type, filters=list(filters), priority=priority)

    def on_hello(self, *filters: Filter, priority: int = 0) -> Callable[[EventHandler], EventHandler]:
        return self._event_shortcut(EventType.HELLO, *filters, priority=priority)

    def on_ready(self, *filters: Filter, priority: int = 0) -> Callable[[EventHandler], EventHandler]:
        return self._event_shortcut(EventType.READY, *filters, priority=priority)

    def on_resume(self, *filters: Filter, priority: int = 0) -> Callable[[EventHandler], EventHandler]:
        return self._event_shortcut(EventType.RESUMED, *filters, priority=priority)

    def on_update_message(self, *filters: Filter, priority: int = 0) -> Callable[[EventHandler], EventHandler]:
        return self._event_shortcut(EventType.MESSAGE_UPDATE, *filters, priority=priority)

    def on_delete_message(self, *filters: Filter, priority: int = 0) -> Callable[[EventHandler], EventHandler]:
        return self._event_shortcut(EventType.MESSAGE_DELETE, *filters, priority=priority)

    def on_delete_message_many(self, *filters: Filter, priority: int = 0) -> Callable[[EventHandler], EventHandler]:
        return self._event_shortcut(EventType.MESSAGE_DELETE_BULK, *filters, priority=priority)

    def on_reaction(self, *filters: Filter, priority: int = 0) -> Callable[[EventHandler], EventHandler]:
        return self._event_shortcut(EventType.REACTION_ADD, *filters, priority=priority)

    def on_delete_reaction(self, *filters: Filter, priority: int = 0) -> Callable[[EventHandler], EventHandler]:
        return self._event_shortcut(EventType.REACTION_REMOVE, *filters, priority=priority)

    def on_delete_all_reaction(self, *filters: Filter, priority: int = 0) -> Callable[[EventHandler], EventHandler]:
        return self._event_shortcut(EventType.MESSAGE_REACTION_REMOVE_ALL, *filters, priority=priority)

    def on_delete_emoji_for_reaction(self, *filters: Filter, priority: int = 0) -> Callable[[EventHandler], EventHandler]:
        return self._event_shortcut(EventType.MESSAGE_REACTION_REMOVE_EMOJI, *filters, priority=priority)

    def on_command(
        self,
        *commands: str,
        priority: int = 0,
        prefixes: tuple[str, ...] = ("/", "!", "."),
        ignore_case: bool = True,
        filters: list[Filter] | None = None,
    ) -> Callable[[EventHandler], EventHandler]:
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
    ) -> Callable[[EventHandler], EventHandler]:
        """Shortcut for /start command."""
        return self.on_message(CommandStartFilter(), *(filters or []), priority=priority)

    def on_command_help(
        self,
        *,
        priority: int = 0,
        filters: list[Filter] | None = None,
    ) -> Callable[[EventHandler], EventHandler]:
        """Shortcut for /help command."""
        return self.on_message(CommandHelpFilter(), *(filters or []), priority=priority)

    def on_command_settings(
        self,
        *,
        priority: int = 0,
        filters: list[Filter] | None = None,
    ) -> Callable[[EventHandler], EventHandler]:
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

    def include_routers(self, *routers: Router) -> None:
        """Aiogram-like helper to include multiple routers in one call."""
        for router in routers:
            self.include_router(router)

    def message(
        self,
        *filters: Filter,
        priority: int = 0,
    ) -> Callable[[EventHandler], EventHandler]:
        """Aiogram-like alias for on_message."""
        return self.on_message(*filters, priority=priority)

    def provide(self, name: str, value: Any) -> None:
        """Register dependency value available for handler injection by name."""
        self._dependencies[name] = value

    def _resolve_dependencies(self) -> dict[str, Any]:
        deps: dict[str, Any] = {}
        if self._parent is not None:
            deps.update(self._parent._resolve_dependencies())
        deps.update(self._dependencies)
        return deps

    @staticmethod
    def _extract_accepted_kwargs(handler: EventHandler) -> set[str]:
        signature = inspect.signature(handler)
        accepted: set[str] = set()
        for name, param in signature.parameters.items():
            if name == "event":
                continue
            if param.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}:
                accepted.add(name)
        return accepted

    def _build_handler_kwargs(
        self,
        *,
        dependencies: Mapping[str, Any],
        filter_data: Mapping[str, Any],
        accepted_kwargs: set[str],
    ) -> dict[str, Any]:
        """Create deterministic kwargs map for DI-style handler invocation."""
        full_kwargs = {**dependencies, **filter_data}
        if not accepted_kwargs:
            return {}
        return {name: value for name, value in full_kwargs.items() if name in accepted_kwargs}

    def on_startup(self) -> Callable[[LifecycleHandler], LifecycleHandler]:
        def decorator(handler: LifecycleHandler) -> LifecycleHandler:
            self._startup_handlers.append(handler)
            return handler
        return decorator

    def on_shutdown(self) -> Callable[[LifecycleHandler], LifecycleHandler]:
        def decorator(handler: LifecycleHandler) -> LifecycleHandler:
            self._shutdown_handlers.append(handler)
            return handler
        return decorator

    def on_reconnect(self) -> Callable[[LifecycleHandler], LifecycleHandler]:
        def decorator(handler: LifecycleHandler) -> LifecycleHandler:
            self._reconnect_handlers.append(handler)
            return handler
        return decorator

    async def emit_startup(self) -> None:
        for router in self._routers:
            await router.emit_startup()
        for handler in self._startup_handlers:
            await handler()

    async def emit_shutdown(self) -> None:
        for router in self._routers:
            await router.emit_shutdown()
        for handler in self._shutdown_handlers:
            await handler()

    async def emit_reconnect(self) -> None:
        for router in self._routers:
            await router.emit_reconnect()
        for handler in self._reconnect_handlers:
            await handler()

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

    def register_middleware(
        self,
        middleware: Middleware,
        *,
        layer: str = "inner",
        priority: int = 0,
        event_types: list[EventType] | None = None,
    ) -> None:
        if layer not in {"inner", "outer"}:
            raise ValueError("layer must be 'inner' or 'outer'")
        if layer == "outer":
            self.add_outer_middleware(middleware, priority=priority, event_types=event_types)
            return
        self.add_middleware(middleware, priority=priority, event_types=event_types)

    def middleware_layer(
        self,
        *,
        layer: str = "inner",
        priority: int = 0,
        event_types: list[EventType] | None = None,
    ) -> Callable[[Middleware], Middleware]:
        def decorator(middleware: Middleware) -> Middleware:
            self.register_middleware(
                middleware,
                layer=layer,
                priority=priority,
                event_types=event_types,
            )
            return middleware

        return decorator

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
        layer: str = "inner",
    ) -> Callable[[Middleware], Middleware]:
        """Decorator to register middleware for selected layer."""

        def decorator(middleware: Middleware) -> Middleware:
            self.register_middleware(
                middleware,
                layer=layer,
                priority=priority,
                event_types=event_types,
            )
            return middleware

        return decorator


    def add_outer_middleware(
        self,
        middleware: Middleware,
        *,
        priority: int = 0,
        event_types: list[EventType] | None = None,
    ) -> None:
        """Register an outer middleware (runs before filter checks)."""
        config = MiddlewareConfig(
            middleware=middleware,
            priority=priority,
            event_types=event_types,
        )
        self._outer_middlewares.append(config)
        self._outer_middlewares.sort(key=lambda item: item.priority, reverse=True)

    def outer_middleware(
        self,
        *,
        priority: int = 0,
        event_types: list[EventType] | None = None,
    ) -> Callable[[Middleware], Middleware]:
        def decorator(middleware: Middleware) -> Middleware:
            self.add_outer_middleware(
                middleware,
                priority=priority,
                event_types=event_types,
            )
            return middleware

        return decorator

    def _resolve_outer_middleware_configs(
        self, event_type: EventType
    ) -> list[MiddlewareConfig]:
        chain: list[MiddlewareConfig] = []
        if self._parent is not None:
            chain.extend(self._parent._resolve_outer_middleware_configs(event_type))
        chain.extend(self._outer_middlewares)
        return [
            item
            for item in chain
            if item.event_types is None or event_type in item.event_types
        ]

    def _resolve_outer_middleware_chain(self, event_type: EventType) -> list[Middleware]:
        configs = self._resolve_outer_middleware_configs(event_type)
        return [item.middleware for item in configs]

    async def _invoke_middleware(
        self,
        middleware: Middleware,
        event: Event,
        next_handler: NextHandler,
    ) -> EventHandlerResult:
        if isinstance(middleware, BaseMiddleware):
            async def aiogram_handler(inner_event: Event, _data: dict[str, Any]) -> EventHandlerResult:
                return await next_handler(inner_event)

            return await middleware(aiogram_handler, event, event.context)

        return await middleware(event, next_handler)

    async def _execute_outer_middlewares(
        self,
        event: Event,
        handler: EventHandler,
    ) -> EventHandlerResult:
        async def call(index: int, current_event: Event) -> EventHandlerResult:
            if index >= len(chain):
                return await handler(current_event)
            middleware = chain[index]
            next_handler: NextHandler = lambda next_event: call(index + 1, next_event)
            try:
                return await self._invoke_middleware(middleware, current_event, next_handler)
            except StopPropagation:
                return None

        chain = self._resolve_outer_middleware_chain(event.type)
        return await call(0, event)

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
        handler: EventHandler,
    ) -> EventHandlerResult:
        async def call(index: int, current_event: Event) -> EventHandlerResult:
            if index >= len(chain):
                return await handler(current_event)
            middleware = chain[index]
            next_handler: NextHandler = lambda next_event: call(index + 1, next_event)
            try:
                return await self._invoke_middleware(middleware, current_event, next_handler)
            except StopPropagation:
                return None

        chain = self._resolve_middleware_chain(event.type)
        return await call(0, event)

    async def propagate_event(self, event: Event) -> EventHandlerResult:
        async def _inner(current_event: Event) -> EventHandlerResult:
            result = None
            skipped = object()

            for router in self._routers:
                router_result = await router.propagate_event(current_event)
                if router_result is not None:
                    result = router_result

            handlers = self._handlers.get(current_event.type, [])
            router_filters = [
                item.filter_obj for item in self._resolve_router_filter_configs(current_event.type)
            ]
            for config in handlers:
                async def guarded_handler(local_event: Event) -> EventHandlerResult:
                    filter_data: FilterDataMap = {}
                    for filter_func in [*router_filters, *config.filters]:
                        try:
                            passed, data = await run_filter_with_data(filter_func, local_event)
                            if data:
                                filter_data.update(data)
                            if not passed:
                                return skipped
                        except Exception:
                            return skipped
                    if filter_data:
                        local_event.context.setdefault("filter_data", {}).update(filter_data)
                    accepted_kwargs = self._build_handler_kwargs(
                        dependencies=self._resolve_dependencies(),
                        filter_data=local_event.context.get("filter_data", {}),
                        accepted_kwargs=config.accepted_kwargs,
                    )
                    return await config.handler(local_event, **accepted_kwargs)

                current_result = await self._execute_with_middlewares(current_event, guarded_handler)
                if current_result is not skipped:
                    result = current_result

            return result

        return await self._execute_outer_middlewares(event, _inner)

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

    @staticmethod
    def stop_propagation() -> None:
        """Raise StopPropagation from middleware/handler to drop event."""
        raise StopPropagation

    def on_message_state(
        self,
        *states: str,
        priority: int = 0,
        filters: list[Filter] | None = None,
        scope: str = "member",
    ) -> Callable[[EventHandler], EventHandler]:
        """
        Decorator that handles only MESSAGE_CREATE events in specific FSM states.
        """
        combined_filters = [self.state_filter(*states, scope=scope), *(filters or [])]
        return self.on_message(*combined_filters, priority=priority)

    def __repr__(self) -> str:
        return f"<Router name='{self.name}' handlers={sum(len(h) for h in self._handlers.values())}>"
