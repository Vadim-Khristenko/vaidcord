"""
Router system for VaidCord.

Inspired by Aiogram 3.x routers, this module provides a flexible way to organize
bot handlers into modular components.
"""

from __future__ import annotations

import inspect
import types
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

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
from vaidcord.types import ChannelType, Event, EventType, WebhookEventType
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
HandlerDecorator = Callable[[EventHandler], EventHandler]
RoutableEventType = EventType | WebhookEventType


@dataclass
class HandlerConfig:
    """Configuration for a registered handler."""

    handler: EventHandler
    event_types: list[RoutableEventType]
    filters: list[Filter] = field(default_factory=list)
    priority: int = 0
    accepted_kwargs: set[str] = field(default_factory=set)
    accepted_annotations: dict[str, Any] = field(default_factory=dict)
    pass_event: bool = True


@dataclass
class MiddlewareConfig:
    """Configuration for middleware registration."""

    middleware: Middleware
    priority: int = 0
    event_types: list[RoutableEventType] | None = None


@dataclass
class RouterFilterConfig:
    """Configuration for router-level (global) filters."""

    filter_obj: Filter
    priority: int = 0
    event_types: list[RoutableEventType] | None = None


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
            await event.message.answer("Hello!")
    """

    def __init__(self, name: str | None = None) -> None:
        self.name = name or f"router_{id(self)}"
        self._handlers: dict[RoutableEventType, list[HandlerConfig]] = defaultdict(list)
        self._routers: list[Router] = []
        self._parent: Router | None = None
        self._middlewares: list[MiddlewareConfig] = []
        self._outer_middlewares: list[MiddlewareConfig] = []
        self._router_filters: list[RouterFilterConfig] = []
        self._dependencies: dict[str, Any] = {}
        self._startup_handlers: list[LifecycleHandler] = []
        self._shutdown_handlers: list[LifecycleHandler] = []
        self._reconnect_handlers: list[LifecycleHandler] = []
        self._dependencies_cache: dict[str, Any] | None = None
        self._router_filter_cache: dict[RoutableEventType, list[RouterFilterConfig]] = {}
        self._middleware_cache: dict[RoutableEventType, list[MiddlewareConfig]] = {}
        self._outer_middleware_cache: dict[RoutableEventType, list[MiddlewareConfig]] = {}

    def _invalidate_resolution_caches(self) -> None:
        self._dependencies_cache = None
        self._router_filter_cache.clear()
        self._middleware_cache.clear()
        self._outer_middleware_cache.clear()
        for router in self._routers:
            router._invalidate_resolution_caches()

    def _resolve_event_types(self, *event_types: RoutableEventType | str) -> list[RoutableEventType]:
        """Resolve event types from arguments."""
        result: list[RoutableEventType] = []
        for et in event_types:
            if isinstance(et, EventType | WebhookEventType):
                result.append(et)
            elif isinstance(et, str):
                event_name = et.upper()
                try:
                    result.append(EventType[event_name])
                    continue
                except KeyError:
                    pass
                try:
                    result.append(WebhookEventType[event_name])
                except KeyError as error:
                    raise ValueError(f"Unknown event type: {et}") from error
            else:
                raise TypeError(f"Invalid event type: {type(et)}")
        return result

    def register_handler(
        self,
        handler: EventHandler,
        *event_types: RoutableEventType | str,
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
        accepted_kwargs, accepted_annotations, pass_event = self._inspect_handler_signature(handler)
        config = HandlerConfig(
            handler=handler,
            event_types=resolved_types,
            filters=filters or [],
            priority=priority,
            accepted_kwargs=accepted_kwargs,
            accepted_annotations=accepted_annotations,
            pass_event=pass_event,
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
                ChannelType.GUILD_MEDIA,
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
        *event_types: RoutableEventType | str,
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
        event_type: RoutableEventType,
        *filters: Filter,
        priority: int = 0,
    ) -> Callable[[EventHandler], EventHandler]:
        return self.on_event(event_type, filters=list(filters), priority=priority)

    def on_hello(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.HELLO, *filters, priority=priority)

    def on_ready(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.READY, *filters, priority=priority)

    def on_resumed(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.RESUMED, *filters, priority=priority)

    def on_reconnect_event(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.RECONNECT, *filters, priority=priority)

    def on_rate_limited(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.RATE_LIMITED, *filters, priority=priority)

    def on_invalid_session(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.INVALID_SESSION, *filters, priority=priority)

    def on_application_command_permissions_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.APPLICATION_COMMAND_PERMISSIONS_UPDATE, *filters, priority=priority)

    def on_auto_moderation_rule_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.AUTO_MODERATION_RULE_CREATE, *filters, priority=priority)

    def on_auto_moderation_rule_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.AUTO_MODERATION_RULE_UPDATE, *filters, priority=priority)

    def on_auto_moderation_rule_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.AUTO_MODERATION_RULE_DELETE, *filters, priority=priority)

    def on_auto_moderation_action_execution(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.AUTO_MODERATION_ACTION_EXECUTION, *filters, priority=priority)

    def on_channel_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.CHANNEL_CREATE, *filters, priority=priority)

    def on_channel_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.CHANNEL_UPDATE, *filters, priority=priority)

    def on_channel_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.CHANNEL_DELETE, *filters, priority=priority)

    def on_channel_info(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.CHANNEL_INFO, *filters, priority=priority)

    def on_channel_pins_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.CHANNEL_PINS_UPDATE, *filters, priority=priority)

    def on_thread_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.THREAD_CREATE, *filters, priority=priority)

    def on_thread_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.THREAD_UPDATE, *filters, priority=priority)

    def on_thread_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.THREAD_DELETE, *filters, priority=priority)

    def on_thread_list_sync(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.THREAD_LIST_SYNC, *filters, priority=priority)

    def on_thread_member_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.THREAD_MEMBER_UPDATE, *filters, priority=priority)

    def on_thread_members_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.THREAD_MEMBERS_UPDATE, *filters, priority=priority)

    def on_entitlement_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.ENTITLEMENT_CREATE, *filters, priority=priority)

    def on_entitlement_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.ENTITLEMENT_UPDATE, *filters, priority=priority)

    def on_entitlement_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.ENTITLEMENT_DELETE, *filters, priority=priority)

    def on_guild_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_CREATE, *filters, priority=priority)

    def on_guild_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_UPDATE, *filters, priority=priority)

    def on_guild_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_DELETE, *filters, priority=priority)

    def on_guild_audit_log_entry_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_AUDIT_LOG_ENTRY_CREATE, *filters, priority=priority)

    def on_guild_ban_add(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_BAN_ADD, *filters, priority=priority)

    def on_guild_ban_remove(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_BAN_REMOVE, *filters, priority=priority)

    def on_guild_emojis_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_EMOJIS_UPDATE, *filters, priority=priority)

    def on_guild_stickers_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_STICKERS_UPDATE, *filters, priority=priority)

    def on_guild_integrations_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_INTEGRATIONS_UPDATE, *filters, priority=priority)

    def on_guild_member_add(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_MEMBER_ADD, *filters, priority=priority)

    def on_guild_member_remove(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_MEMBER_REMOVE, *filters, priority=priority)

    def on_guild_member_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_MEMBER_UPDATE, *filters, priority=priority)

    def on_guild_members_chunk(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_MEMBERS_CHUNK, *filters, priority=priority)

    def on_guild_role_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_ROLE_CREATE, *filters, priority=priority)

    def on_guild_role_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_ROLE_UPDATE, *filters, priority=priority)

    def on_guild_role_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_ROLE_DELETE, *filters, priority=priority)

    def on_guild_scheduled_event_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_SCHEDULED_EVENT_CREATE, *filters, priority=priority)

    def on_guild_scheduled_event_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_SCHEDULED_EVENT_UPDATE, *filters, priority=priority)

    def on_guild_scheduled_event_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_SCHEDULED_EVENT_DELETE, *filters, priority=priority)

    def on_guild_scheduled_event_user_add(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_SCHEDULED_EVENT_USER_ADD, *filters, priority=priority)

    def on_guild_scheduled_event_user_remove(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_SCHEDULED_EVENT_USER_REMOVE, *filters, priority=priority)

    def on_guild_soundboard_sound_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_SOUNDBOARD_SOUND_CREATE, *filters, priority=priority)

    def on_guild_soundboard_sound_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_SOUNDBOARD_SOUND_UPDATE, *filters, priority=priority)

    def on_guild_soundboard_sound_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_SOUNDBOARD_SOUND_DELETE, *filters, priority=priority)

    def on_guild_soundboard_sounds_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.GUILD_SOUNDBOARD_SOUNDS_UPDATE, *filters, priority=priority)

    def on_soundboard_sounds(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.SOUNDBOARD_SOUNDS, *filters, priority=priority)

    def on_integration_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.INTEGRATION_CREATE, *filters, priority=priority)

    def on_integration_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.INTEGRATION_UPDATE, *filters, priority=priority)

    def on_integration_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.INTEGRATION_DELETE, *filters, priority=priority)

    def on_interaction_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.INTERACTION_CREATE, *filters, priority=priority)

    def on_invite_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.INVITE_CREATE, *filters, priority=priority)

    def on_invite_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.INVITE_DELETE, *filters, priority=priority)

    def on_message_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message(*filters, priority=priority)

    def on_message_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.MESSAGE_UPDATE, *filters, priority=priority)

    def on_message_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.MESSAGE_DELETE, *filters, priority=priority)

    def on_message_delete_bulk(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.MESSAGE_DELETE_BULK, *filters, priority=priority)

    def on_message_reaction_add(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.MESSAGE_REACTION_ADD, *filters, priority=priority)

    def on_message_reaction_remove(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.MESSAGE_REACTION_REMOVE, *filters, priority=priority)

    def on_message_reaction_remove_all(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.MESSAGE_REACTION_REMOVE_ALL, *filters, priority=priority)

    def on_message_reaction_remove_emoji(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.MESSAGE_REACTION_REMOVE_EMOJI, *filters, priority=priority)

    def on_presence_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.PRESENCE_UPDATE, *filters, priority=priority)

    def on_stage_instance_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.STAGE_INSTANCE_CREATE, *filters, priority=priority)

    def on_stage_instance_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.STAGE_INSTANCE_UPDATE, *filters, priority=priority)

    def on_stage_instance_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.STAGE_INSTANCE_DELETE, *filters, priority=priority)

    def on_subscription_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.SUBSCRIPTION_CREATE, *filters, priority=priority)

    def on_subscription_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.SUBSCRIPTION_UPDATE, *filters, priority=priority)

    def on_subscription_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.SUBSCRIPTION_DELETE, *filters, priority=priority)

    def on_typing_start(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.TYPING_START, *filters, priority=priority)

    def on_user_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.USER_UPDATE, *filters, priority=priority)

    def on_voice_channel_effect_send(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.VOICE_CHANNEL_EFFECT_SEND, *filters, priority=priority)

    def on_voice_channel_start_time_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.VOICE_CHANNEL_START_TIME_UPDATE, *filters, priority=priority)

    def on_voice_channel_status_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.VOICE_CHANNEL_STATUS_UPDATE, *filters, priority=priority)

    def on_voice_state_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.VOICE_STATE_UPDATE, *filters, priority=priority)

    def on_voice_server_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.VOICE_SERVER_UPDATE, *filters, priority=priority)

    def on_webhooks_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.WEBHOOKS_UPDATE, *filters, priority=priority)

    def on_message_poll_vote_add(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.MESSAGE_POLL_VOTE_ADD, *filters, priority=priority)

    def on_message_poll_vote_remove(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(EventType.MESSAGE_POLL_VOTE_REMOVE, *filters, priority=priority)

    def on_resume(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_resumed(*filters, priority=priority)

    def on_update_message(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_update(*filters, priority=priority)

    def on_delete_message(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_delete(*filters, priority=priority)

    def on_delete_message_many(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_delete_bulk(*filters, priority=priority)

    def on_reaction(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_reaction_add(*filters, priority=priority)

    def on_reaction_add(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_reaction_add(*filters, priority=priority)

    def on_reaction_remove(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_reaction_remove(*filters, priority=priority)

    def on_reaction_remove_all(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_reaction_remove_all(*filters, priority=priority)

    def on_reaction_remove_emoji(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_reaction_remove_emoji(*filters, priority=priority)

    def on_delete_reaction(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_reaction_remove(*filters, priority=priority)

    def on_delete_all_reaction(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_reaction_remove_all(*filters, priority=priority)

    def on_delete_emoji_for_reaction(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_reaction_remove_emoji(*filters, priority=priority)

    def on_member_join(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_guild_member_add(*filters, priority=priority)

    def on_member_leave(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_guild_member_remove(*filters, priority=priority)

    def on_member_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_guild_member_update(*filters, priority=priority)

    def on_guild_join(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_guild_create(*filters, priority=priority)

    def on_guild_leave(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_guild_delete(*filters, priority=priority)

    def on_typing(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_typing_start(*filters, priority=priority)

    def on_interaction(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_interaction_create(*filters, priority=priority)

    def on_poll_vote_add(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_poll_vote_add(*filters, priority=priority)

    def on_poll_vote_remove(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self.on_message_poll_vote_remove(*filters, priority=priority)

    def on_webhook_application_authorized(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.APPLICATION_AUTHORIZED, *filters, priority=priority)

    def on_webhook_application_deauthorized(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.APPLICATION_DEAUTHORIZED, *filters, priority=priority)

    def on_webhook_entitlement_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.ENTITLEMENT_CREATE, *filters, priority=priority)

    def on_webhook_entitlement_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.ENTITLEMENT_UPDATE, *filters, priority=priority)

    def on_webhook_entitlement_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.ENTITLEMENT_DELETE, *filters, priority=priority)

    def on_webhook_quest_user_enrollment(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.QUEST_USER_ENROLLMENT, *filters, priority=priority)

    def on_webhook_lobby_message_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.LOBBY_MESSAGE_CREATE, *filters, priority=priority)

    def on_webhook_lobby_message_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.LOBBY_MESSAGE_UPDATE, *filters, priority=priority)

    def on_webhook_lobby_message_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.LOBBY_MESSAGE_DELETE, *filters, priority=priority)

    def on_webhook_game_direct_message_create(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.GAME_DIRECT_MESSAGE_CREATE, *filters, priority=priority)

    def on_webhook_game_direct_message_update(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.GAME_DIRECT_MESSAGE_UPDATE, *filters, priority=priority)

    def on_webhook_game_direct_message_delete(self, *filters: Filter, priority: int = 0) -> HandlerDecorator:
        return self._event_shortcut(WebhookEventType.GAME_DIRECT_MESSAGE_DELETE, *filters, priority=priority)

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
        self._invalidate_resolution_caches()

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
        self._invalidate_resolution_caches()

    def _resolve_dependencies(self) -> dict[str, Any]:
        if self._dependencies_cache is not None:
            return dict(self._dependencies_cache)
        deps: dict[str, Any] = {}
        if self._parent is not None:
            deps.update(self._parent._resolve_dependencies())
        deps.update(self._dependencies)
        self._dependencies_cache = deps
        return deps

    @staticmethod
    def _inspect_handler_signature(handler: EventHandler) -> tuple[set[str], dict[str, Any], bool]:
        signature = inspect.signature(handler)
        try:
            type_hints = get_type_hints(handler)
        except Exception:
            type_hints = {}
        accepted: set[str] = set()
        annotations: dict[str, Any] = {}
        pass_event = False
        first_positional = True
        for name, param in signature.parameters.items():
            annotation = type_hints.get(name, param.annotation)
            if first_positional and param.kind in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }:
                if name in {"event", "_event"} or annotation is Event or annotation == "Event":
                    pass_event = True
                    first_positional = False
                    continue
                first_positional = False
            if name in {"event", "_event"}:
                continue
            if param.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}:
                accepted.add(name)
                if annotation is not inspect.Parameter.empty:
                    annotations[name] = annotation
        return accepted, annotations, pass_event

    @staticmethod
    def _matches_annotation(value: Any, annotation: Any) -> bool:
        if annotation in {Any, inspect.Parameter.empty, None}:
            return False
        origin = get_origin(annotation)
        if origin in {types.UnionType, Union}:
            return any(Router._matches_annotation(value, arg) for arg in get_args(annotation))
        if origin is not None:
            annotation = origin
        if isinstance(annotation, str):
            return False
        try:
            return isinstance(value, annotation)
        except TypeError:
            return False

    def _build_handler_kwargs(
        self,
        *,
        dependencies: Mapping[str, Any],
        context_data: Mapping[str, Any],
        filter_data: Mapping[str, Any],
        accepted_kwargs: set[str],
        accepted_annotations: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create deterministic kwargs map for DI-style handler invocation."""
        full_kwargs = {**dependencies, **context_data, **filter_data}
        if not accepted_kwargs:
            return {}
        kwargs = {name: value for name, value in full_kwargs.items() if name in accepted_kwargs}
        annotations = accepted_annotations or {}
        injectable_values = list(full_kwargs.values())
        for name in accepted_kwargs:
            if name in kwargs:
                continue
            annotation = annotations.get(name)
            for value in injectable_values:
                if self._matches_annotation(value, annotation):
                    kwargs[name] = value
                    break
        return kwargs

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
            params = inspect.signature(handler).parameters
            if params:
                self.register_handler(handler, EventType.RECONNECT)
                return handler
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
        event_types: list[RoutableEventType] | None = None,
    ) -> None:
        """Add a global router filter applied to all handlers."""
        config = RouterFilterConfig(
            filter_obj=filter_obj,
            priority=priority,
            event_types=event_types,
        )
        self._router_filters.append(config)
        self._router_filters.sort(key=lambda item: item.priority, reverse=True)
        self._invalidate_resolution_caches()

    def router_filter(
        self,
        *,
        priority: int = 0,
        event_types: list[RoutableEventType] | None = None,
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
        self, event_type: RoutableEventType
    ) -> list[RouterFilterConfig]:
        cached = self._router_filter_cache.get(event_type)
        if cached is not None:
            return list(cached)
        chain: list[RouterFilterConfig] = []
        if self._parent is not None:
            chain.extend(self._parent._resolve_router_filter_configs(event_type))
        chain.extend(self._router_filters)
        resolved = [
            item
            for item in chain
            if item.event_types is None or event_type in item.event_types
        ]
        self._router_filter_cache[event_type] = resolved
        return list(resolved)

    def register_middleware(
        self,
        middleware: Middleware,
        *,
        layer: str = "inner",
        priority: int = 0,
        event_types: list[RoutableEventType] | None = None,
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
        event_types: list[RoutableEventType] | None = None,
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
        event_types: list[RoutableEventType] | None = None,
    ) -> None:
        """Register an event middleware for this router tree."""
        config = MiddlewareConfig(
            middleware=middleware,
            priority=priority,
            event_types=event_types,
        )
        self._middlewares.append(config)
        self._middlewares.sort(key=lambda item: item.priority, reverse=True)
        self._invalidate_resolution_caches()

    def middleware(
        self,
        *,
        priority: int = 0,
        event_types: list[RoutableEventType] | None = None,
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
        event_types: list[RoutableEventType] | None = None,
    ) -> None:
        """Register an outer middleware (runs before filter checks)."""
        config = MiddlewareConfig(
            middleware=middleware,
            priority=priority,
            event_types=event_types,
        )
        self._outer_middlewares.append(config)
        self._outer_middlewares.sort(key=lambda item: item.priority, reverse=True)
        self._invalidate_resolution_caches()

    def outer_middleware(
        self,
        *,
        priority: int = 0,
        event_types: list[RoutableEventType] | None = None,
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
        self, event_type: RoutableEventType
    ) -> list[MiddlewareConfig]:
        cached = self._outer_middleware_cache.get(event_type)
        if cached is not None:
            return list(cached)
        chain: list[MiddlewareConfig] = []
        if self._parent is not None:
            chain.extend(self._parent._resolve_outer_middleware_configs(event_type))
        chain.extend(self._outer_middlewares)
        resolved = [
            item
            for item in chain
            if item.event_types is None or event_type in item.event_types
        ]
        self._outer_middleware_cache[event_type] = resolved
        return list(resolved)

    def _resolve_outer_middleware_chain(self, event_type: RoutableEventType) -> list[Middleware]:
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
        self, event_type: RoutableEventType
    ) -> list[MiddlewareConfig]:
        cached = self._middleware_cache.get(event_type)
        if cached is not None:
            return list(cached)
        chain: list[MiddlewareConfig] = []
        if self._parent is not None:
            chain.extend(self._parent._resolve_middleware_configs(event_type))
        chain.extend(self._middlewares)
        resolved = [
            item
            for item in chain
            if item.event_types is None or event_type in item.event_types
        ]
        self._middleware_cache[event_type] = resolved
        return list(resolved)

    def _resolve_middleware_chain(self, event_type: RoutableEventType) -> list[Middleware]:
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
        dependencies = self._resolve_dependencies()
        if dependencies:
            event.context.update(dependencies)
        if event.bot is not None:
            event.context["bot"] = event.bot
        event.context.setdefault("event", event)
        for name in (
            "message",
            "user",
            "guild",
            "channel",
            "interaction",
            "object",
            "payload",
            "ready",
            "resume",
            "deleted_message",
            "deleted_messages",
            "reaction",
            "typing",
            "poll_vote",
        ):
            value = getattr(event, name, None)
            if value is not None:
                event.context.setdefault(name, value)

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
                async def guarded_handler(
                    local_event: Event,
                    handler_config: HandlerConfig = config,
                ) -> EventHandlerResult:
                    filter_data: FilterDataMap = {}
                    for filter_func in [*router_filters, *handler_config.filters]:
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
                        context_data={
                            key: value
                            for key, value in local_event.context.items()
                            if key != "filter_data"
                        },
                        filter_data=local_event.context.get("filter_data", {}),
                        accepted_kwargs=handler_config.accepted_kwargs,
                        accepted_annotations=handler_config.accepted_annotations,
                    )
                    if handler_config.pass_event:
                        return await handler_config.handler(local_event, **accepted_kwargs)
                    return await handler_config.handler(**accepted_kwargs)

                current_result = await self._execute_with_middlewares(current_event, guarded_handler)
                if current_result is not skipped:
                    result = current_result

            return result

        return await self._execute_outer_middlewares(event, _inner)

    def get_handlers(self, event_type: RoutableEventType) -> list[HandlerConfig]:
        """Get all handlers for a specific event type."""
        return self._handlers.get(event_type, [])

    def clear_handlers(self, event_type: RoutableEventType | None = None) -> None:
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
    def state_filter(*states: object, scope: str = "primary") -> Filter:
        """
        Build a filter that checks `event.context['fsm']` state.
        """
        state_set = {str(state) for state in states}

        async def _filter(event: Event) -> bool:
            if scope == "primary":
                fsm = event.context.get("fsm")
                resolved_scope = event.context.get("fsm_primary_scope")
            else:
                fsm_map = event.context.get("fsm_map", {})
                fsm = fsm_map.get(scope)
                resolved_scope = scope
            if fsm is None:
                return False
            state_snapshot = event.context.get("fsm_states", {})
            current_state = state_snapshot.get(resolved_scope)
            if current_state is None and resolved_scope not in state_snapshot:
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
        *states: object,
        priority: int = 0,
        filters: list[Filter] | None = None,
        scope: str = "primary",
    ) -> Callable[[EventHandler], EventHandler]:
        """
        Decorator that handles only MESSAGE_CREATE events in specific FSM states.
        """
        combined_filters = [self.state_filter(*states, scope=scope), *(filters or [])]
        return self.on_message(*combined_filters, priority=priority)

    def __repr__(self) -> str:
        return f"<Router name='{self.name}' handlers={sum(len(h) for h in self._handlers.values())}>"
