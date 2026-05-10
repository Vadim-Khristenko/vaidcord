"""
Bot client for VaidCord.

This module provides the main Bot class that serves as the entry point
for creating Discord bots with VaidCord.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum, IntFlag
from typing import Any, Literal, cast

import aiohttp

from vaidcord._internal import EventParser, MessageService
from vaidcord.api_client import APIClient
from vaidcord.application import Application, ApplicationRoleConnectionMetadata
from vaidcord.commands import (
    ApplicationCommandType,
    CommandContext,
    CommandHandler,
    RegisteredCommand,
)
from vaidcord.errors import RateLimitError
from vaidcord.gateway_runtime import GatewayRuntime
from vaidcord.http import DiscordError
from vaidcord.logging import set_default_bot_id
from vaidcord.metadata import __version__, build_user_agent
from vaidcord.router import Router
from vaidcord.types import (
    Channel,
    Event,
    EventType,
    Guild,
    Message,
    MessagePin,
    Ready,
    User,
)
from vaidcord.voice import VoiceConnection, VoiceGatewayConfig, VoiceManager

logger = logging.getLogger(__name__)


class BotState(Enum):
    """Lifecycle states for the bot connection."""

    IDLE = "idle"
    CONNECTING = "connecting"
    IDENTIFYING = "identifying"
    READY = "ready"
    RECONNECTING = "reconnecting"
    STOPPING = "stopping"
    STOPPED = "stopped"


class GatewayIntent(IntFlag):
    """Gateway intents bitfield values from the Discord Gateway docs."""

    GUILDS = 1 << 0
    GUILD_MEMBERS = 1 << 1
    GUILD_MODERATION = 1 << 2
    GUILD_EMOJIS_AND_STICKERS = 1 << 3
    GUILD_INTEGRATIONS = 1 << 4
    GUILD_WEBHOOKS = 1 << 5
    GUILD_INVITES = 1 << 6
    GUILD_VOICE_STATES = 1 << 7
    GUILD_PRESENCES = 1 << 8
    GUILD_MESSAGES = 1 << 9
    GUILD_MESSAGE_REACTIONS = 1 << 10
    GUILD_MESSAGE_TYPING = 1 << 11
    DIRECT_MESSAGES = 1 << 12
    DIRECT_MESSAGE_REACTIONS = 1 << 13
    DIRECT_MESSAGE_TYPING = 1 << 14
    MESSAGE_CONTENT = 1 << 15
    GUILD_SCHEDULED_EVENTS = 1 << 16
    AUTO_MODERATION_CONFIGURATION = 1 << 20
    AUTO_MODERATION_EXECUTION = 1 << 21
    GUILD_MESSAGE_POLLS = 1 << 24
    DIRECT_MESSAGE_POLLS = 1 << 25

    @classmethod
    def default(cls) -> int:
        """Sensible default intents for common bot workloads."""
        return int(cls.GUILDS | cls.GUILD_MESSAGES | cls.DIRECT_MESSAGES)

    @classmethod
    def all(cls) -> int:
        """All currently documented intents."""
        return int(sum(intent.value for intent in cls))


@dataclass
class BotConfig:
    """Configuration for the Bot client."""

    token: str
    intents: int | GatewayIntent = GatewayIntent.default()
    shard_count: int = 1
    shard_id: int = 0
    presence: dict[str, Any] | None = None
    activity: dict[str, Any] | None = None
    api_version: str = "10"
    base_url: str = "https://discord.com/api"
    gateway_url: str = "wss://gateway.discord.gg"
    ignore_self_messages: bool = True
    auto_sync_commands: bool = True
    command_dev_guild_id: int | None = None
    command_sync_mode: Literal["replace", "merge"] = "replace"
    command_sync_guild_ids: tuple[int, ...] = ()
    keep_raw_data: bool = True
    """Whether typed events keep a ``raw_data`` copy of the gateway payload.

    Defaults to ``True`` for backwards compatibility. Set to ``False`` to
    disable population of ``raw_data`` on every parsed model and event,
    which can substantially reduce allocations for high-throughput bots
    that don't need direct access to the raw payload (see issue #26).
    """
    share_raw_data: bool = True
    """When ``keep_raw_data`` is ``True``, share the source dict reference.

    Default ``True``. Setting ``False`` restores the legacy behaviour of
    making a defensive ``dict()`` copy on every parse. The default is safe
    because the parser receives a fresh ``json.loads()`` dict that is not
    mutated anywhere else in the framework.
    """


class Bot(Router):
    """
    Main bot client for VaidCord.

    The Bot class is the central point for managing your Discord bot.
    It handles WebSocket connections, event dispatching, and API interactions.

    Example:
        bot = Bot(token="YOUR_TOKEN")

        @bot.on_message()
        async def handle_message(event: Event):
            print(f"Message from {event.message.author}: {event.message.content}")

        bot.run()
    """

    def __init__(
        self,
        token: str | None = None,
        config: BotConfig | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name="bot")

        if config is None:
            if token is None:
                raise ValueError("Either 'token' or 'config' must be provided")
            config = BotConfig(token=token, **kwargs)

        self.config = config
        if not self.config.ignore_self_messages:
            logger.warning(
                "Self message handling is enabled; this can cause message loops. "
                "Set ignore_self_messages=True to avoid this behavior."
            )
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._sequence: int | None = None
        self._session_id: str | None = None
        self._resume_gateway_url: str | None = None
        self._state = BotState.IDLE
        self.api_client = APIClient(
            token=self.config.token,
            base_url=self.config.base_url,
            api_version=self.config.api_version,
            session_provider=self._create_session,
            session_closer=self._close_session,
        )
        self.runtime = GatewayRuntime(self)
        self.voice = VoiceManager(self)

        # Cache for guilds, users, channels
        self._guilds: dict[int, Guild] = {}
        self._users: dict[int, User] = {}
        self._channels: dict[int, Channel] = {}
        self._user: User | None = None

        # Internal collaborators (issue #32). Bot keeps its public methods
        # but delegates parsing and message-resource endpoints here so the
        # facade stops growing every time a new Discord endpoint lands.
        self._parser = EventParser(self)
        self._messages = MessageService(self)

        # Event handlers for internal events
        self._ready_event = asyncio.Event()
        self._drop_pending_updates = False
        self._registered_commands: list[RegisteredCommand] = []
        self._command_sync_retry_task: asyncio.Task[None] | None = None

    @property
    def parser(self) -> EventParser:
        """Return the internal event parser used by services."""
        return self._parser

    def _log_extra(self) -> dict[str, str]:
        """Return logging context for this bot when its identity is known."""
        return {} if self.id is None else {"bot_id": str(self.id)}

    @property
    def is_ready(self) -> bool:
        """Check if the bot is ready and connected."""
        return self._ready_event.is_set()

    @property
    def state(self) -> BotState:
        """Current lifecycle state."""
        return self._state

    @property
    def user(self) -> User | None:
        """Get the bot's user object."""
        return self._user

    @property
    def id(self) -> int | None:
        """Get the bot user ID if available."""
        if self._user is None:
            return None
        return self._user.id

    @property
    def guilds(self) -> list[Guild]:
        """Get all cached guilds."""
        return list(self._guilds.values())

    @property
    def latency(self) -> float:
        """Get the WebSocket latency in seconds."""
        return self.runtime.latency

    async def _create_session(self) -> aiohttp.ClientSession:
        """Create an aiohttp session for API requests."""
        if self._session is None or self._session.closed:
            headers = {
                "Authorization": f"Bot {self.config.token}",
                "User-Agent": build_user_agent(),
                "X-VaidCord-Version": __version__,
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def _close_session(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an API request to Discord."""
        return await self.api_client.request(method, endpoint, **kwargs)


    async def _connect_gateway(self) -> None:
        await self.runtime.connect()

    async def _send_payload(self, payload: dict[str, Any]) -> None:
        await self.runtime.send_payload(payload)

    async def _identify(self) -> None:
        await self.runtime.identify()

    async def _heartbeat(self) -> None:
        return None

    async def _handle_dispatch(self, data: dict[str, Any]) -> None:
        """Handle a dispatch event from the gateway."""
        t = data.get("t")  # Event type
        d = data.get("d")  # Event data
        s = data.get("s")  # Sequence number

        if s is not None:
            self._sequence = s

        if t is None or d is None:
            return
        self.voice.handle_gateway_event(str(t).upper(), d)

        event_type_str = t.upper()
        try:
            event_type = EventType[event_type_str]
        except KeyError:
            logger.debug(
                {
                    "event": "gateway.dispatch.unknown",
                    "gateway_event": event_type_str,
                    "sequence": s,
                },
                extra=self._log_extra(),
            )
            return

        if self._drop_pending_updates and not self._ready_event.is_set() and event_type != EventType.READY:
            return

        event = await self._parse_event(event_type, d)

        # Handle special events
        if event_type == EventType.READY:
            await self._handle_ready(d)
            if self._drop_pending_updates:
                self._drop_pending_updates = False
        elif event_type in {EventType.MESSAGE_CREATE, EventType.MESSAGE_UPDATE} and event.message is not None:
            await self._handle_message_create(event, d)
            if (
                event_type == EventType.MESSAGE_CREATE
                and
                self.config.ignore_self_messages
                and self._user is not None
                and event.message is not None
                and event.message.author.id == self._user.id
            ):
                return
        elif event_type == EventType.INTERACTION_CREATE:
            await self._handle_interaction_create(d)

        # Propagate event to handlers
        await self.propagate_event(event)

    async def join_voice_channel(
        self,
        guild_id: int,
        channel_id: int,
        *,
        self_mute: bool = False,
        self_deaf: bool = False,
        config: VoiceGatewayConfig | None = None,
        wait_timeout: float = 30.0,
    ) -> VoiceConnection:
        if self._user is None:
            raise RuntimeError("Bot user is not known yet; wait for READY before joining voice")
        return await self.voice.connect(
            guild_id,
            channel_id,
            user_id=self._user.id,
            self_mute=self_mute,
            self_deaf=self_deaf,
            config=config,
            wait_timeout=wait_timeout,
        )

    def _raw(self, data: dict[str, Any]) -> dict[str, Any]:
        """Back-compat shim — see :meth:`EventParser.raw`."""
        return self._parser.raw(data)

    async def _parse_event(self, event_type: EventType, data: dict[str, Any]) -> Event:
        """Parse raw event data into a typed Event object.

        Delegates to :class:`EventParser`; method retained on Bot for
        back-compat with subclasses that override it.
        """
        return await self._parser.parse_event(event_type, data)

    def _parse_ready(self, data: dict[str, Any]) -> Ready:
        return self._parser.parse_ready(data)
    async def _handle_ready(self, data: dict[str, Any]) -> None:
        """Handle the READY event."""
        user_data = data.get("user", {})
        bot_user = self._parse_user(user_data)
        self._remember_bot_user(bot_user)

        # Cache guilds
        for guild_data in data.get("guilds", []):
            guild = self._parse_guild(guild_data)
            self._guilds[guild.id] = guild

        self._session_id = data.get("session_id")
        self._resume_gateway_url = data.get("resume_gateway_url")
        self._state = BotState.READY
        self._ready_event.set()
        getattr(logger, "success", logger.info)(
            "Bot logged in as %s (id=%s)",
            bot_user.username,
            bot_user.id,
            extra=self._log_extra(),
        )
        if self.config.auto_sync_commands and self._registered_commands:
            await self.sync_application_commands()

    async def _handle_interaction_create(self, data: dict[str, Any]) -> None:
        interaction_type = int(data.get("type", 0))
        if interaction_type != 2:
            return
        command_data = data.get("data")
        if not isinstance(command_data, dict):
            return
        name = command_data.get("name")
        command_type = int(command_data.get("type", 1))
        if not isinstance(name, str) or not name:
            return
        guild_id = int(data["guild_id"]) if data.get("guild_id") else None
        for command in self._registered_commands:
            if command.name != name or int(command.kind) != command_type:
                continue
            if command.guild_id is not None and command.guild_id != guild_id:
                continue
            await command.handler(CommandContext(raw=dict(data)))

    def slash_command(
        self,
        name: str | None = None,
        *,
        description: str = "No description",
        guild_id: int | None = None,
        options: list[dict[str, Any]] | None = None,
        dm_permission: bool | None = None,
        default_member_permissions: str | None = None,
        name_localizations: dict[str, str] | None = None,
        description_localizations: dict[str, str] | None = None,
        integration_types: list[int] | None = None,
        contexts: list[int] | None = None,
        nsfw: bool | None = None,
    ):
        def decorator(handler: CommandHandler) -> CommandHandler:
            self._registered_commands.append(
                RegisteredCommand(
                    name=name or handler.__name__,
                    description=description,
                    kind=ApplicationCommandType.CHAT_INPUT,
                    handler=handler,
                    guild_id=guild_id,
                    options=list(options or []),
                    dm_permission=dm_permission,
                    default_member_permissions=default_member_permissions,
                    name_localizations=name_localizations,
                    description_localizations=description_localizations,
                    integration_types=integration_types,
                    contexts=contexts,
                    nsfw=nsfw,
                )
            )
            return handler

        return decorator

    def user_command(
        self,
        name: str | None = None,
        *,
        guild_id: int | None = None,
        dm_permission: bool | None = None,
        default_member_permissions: str | None = None,
        name_localizations: dict[str, str] | None = None,
        integration_types: list[int] | None = None,
        contexts: list[int] | None = None,
        nsfw: bool | None = None,
    ):
        def decorator(handler: CommandHandler) -> CommandHandler:
            self._registered_commands.append(
                RegisteredCommand(
                    name=name or handler.__name__,
                    description="",
                    kind=ApplicationCommandType.USER,
                    handler=handler,
                    guild_id=guild_id,
                    dm_permission=dm_permission,
                    default_member_permissions=default_member_permissions,
                    name_localizations=name_localizations,
                    integration_types=integration_types,
                    contexts=contexts,
                    nsfw=nsfw,
                )
            )
            return handler

        return decorator

    def message_command(
        self,
        name: str | None = None,
        *,
        guild_id: int | None = None,
        dm_permission: bool | None = None,
        default_member_permissions: str | None = None,
        name_localizations: dict[str, str] | None = None,
        integration_types: list[int] | None = None,
        contexts: list[int] | None = None,
        nsfw: bool | None = None,
    ):
        def decorator(handler: CommandHandler) -> CommandHandler:
            self._registered_commands.append(
                RegisteredCommand(
                    name=name or handler.__name__,
                    description="",
                    kind=ApplicationCommandType.MESSAGE,
                    handler=handler,
                    guild_id=guild_id,
                    dm_permission=dm_permission,
                    default_member_permissions=default_member_permissions,
                    name_localizations=name_localizations,
                    integration_types=integration_types,
                    contexts=contexts,
                    nsfw=nsfw,
                )
            )
            return handler

        return decorator

    async def sync_application_commands(self) -> None:
        if self.id is None or not self._registered_commands:
            return
        try:
            await self._sync_application_commands_once()
        except RateLimitError as error:
            retry_after = max(1.0, float(error.retry_after or 5.0))
            logger.warning(
                "Application command sync is rate-limited. Commands will be retried in %.1f seconds.",
                retry_after,
                extra=self._log_extra(),
            )
            self._schedule_command_sync_retry(retry_after)

    async def _sync_application_commands_once(self) -> None:
        if self.id is None:
            return
        desired_global: list[dict[str, Any]] = []
        desired_guild: dict[int, list[dict[str, Any]]] = {}
        for command in self._registered_commands:
            payload = command.to_payload()
            target_guild_id = command.guild_id or self.config.command_dev_guild_id
            if target_guild_id is None:
                desired_global.append(payload)
            else:
                desired_guild.setdefault(target_guild_id, []).append(payload)
        for guild_id in self.config.command_sync_guild_ids:
            desired_guild.setdefault(guild_id, [])

        current_global = await self.api_client.list_global_commands(self.id)
        global_payload = self._resolve_command_sync_payload(current_global, desired_global)
        if self._commands_changed(current_global, global_payload):
            await self.api_client.bulk_overwrite_global_commands(self.id, global_payload)

        for guild_id, desired in desired_guild.items():
            current_guild = await self.api_client.list_guild_commands(self.id, guild_id)
            guild_payload = self._resolve_command_sync_payload(current_guild, desired)
            if self._commands_changed(current_guild, guild_payload):
                await self.api_client.bulk_overwrite_guild_commands(self.id, guild_id, guild_payload)

    def _schedule_command_sync_retry(self, retry_after: float) -> None:
        if self._command_sync_retry_task is not None and not self._command_sync_retry_task.done():
            return

        async def _runner() -> None:
            delay = retry_after
            try:
                while True:
                    await asyncio.sleep(delay)
                    try:
                        await self._sync_application_commands_once()
                        logger.info(
                            "Application command sync retry completed.",
                            extra=self._log_extra(),
                        )
                        return
                    except RateLimitError as error:
                        delay = max(1.0, float(error.retry_after or delay))
                        logger.warning(
                            "Application command sync is still rate-limited. Next retry in %.1f seconds.",
                            delay,
                            extra=self._log_extra(),
                        )
            except Exception:
                logger.exception("Application command sync retry failed.", extra=self._log_extra())
            finally:
                self._command_sync_retry_task = None

        self._command_sync_retry_task = asyncio.create_task(_runner())

    def _resolve_command_sync_payload(
        self,
        current: list[dict[str, Any]],
        desired: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if self.config.command_sync_mode == "replace":
            return desired
        merged: dict[tuple[int, str], dict[str, Any]] = {}
        for item in current:
            normalized = self._normalize_command_payload(item)
            key = (int(normalized.get("type", 1)), str(normalized.get("name", "")))
            if key[1]:
                merged[key] = normalized
        for item in desired:
            normalized = self._normalize_command_payload(item)
            key = (int(normalized.get("type", 1)), str(normalized.get("name", "")))
            if key[1]:
                merged[key] = normalized
        return list(merged.values())

    @staticmethod
    def _normalize_command_payload(payload: dict[str, Any]) -> dict[str, Any]:
        filtered = {
            key: value
            for key, value in payload.items()
            if key
            not in {
                "id",
                "application_id",
                "guild_id",
                "version",
                "default_permission",
                "name_localized",
                "description_localized",
            }
        }
        if "options" in filtered and isinstance(filtered["options"], list):
            filtered["options"] = [dict(option) for option in filtered["options"]]
        return filtered

    @staticmethod
    def _commands_changed(current: list[dict[str, Any]], desired: list[dict[str, Any]]) -> bool:
        left = sorted(
            (Bot._normalize_command_payload(item) for item in current),
            key=lambda item: (item.get("type"), item.get("name")),
        )
        right = sorted(
            (Bot._normalize_command_payload(item) for item in desired),
            key=lambda item: (item.get("type"), item.get("name")),
        )
        return left != right

    async def _handle_message_create(self, event: Event, data: dict[str, Any]) -> None:
        """Handle MESSAGE_CREATE event."""
        message = self._parse_message(data)
        event.message = message

        # Cache author and channel
        if data.get("author") is not None:
            self._users[message.author.id] = message.author
        self._channels[message.channel.id] = message.channel

        if message.guild:
            self._guilds[message.guild.id] = message.guild

    def _parse_user(self, data: dict[str, Any]) -> User:
        return self._parser.parse_user(data)
    def _remember_bot_user(self, user: User) -> None:
        """Cache current bot user and propagate its id to log contexts."""
        self._user = user
        self._users[user.id] = user
        self.api_client.set_bot_id(user.id)
        set_default_bot_id(user.id)

    def _parse_guild(self, data: dict[str, Any]) -> Guild:
        return self._parser.parse_guild(data)
    def _parse_channel(self, data: dict[str, Any]) -> Channel:
        return self._parser.parse_channel(data)
    def _parse_message(self, data: dict[str, Any]) -> Message:
        return self._parser.parse_message(data)
    def _parse_message_pin(self, data: dict[str, Any]) -> MessagePin:
        return self._parser.parse_message_pin(data)
    async def _receive_messages(self) -> None:
        await self.runtime.run()

    async def start(self) -> None:
        """Start the bot client."""
        if self._running:
            raise RuntimeError("Bot is already running")

        self._running = True
        self._state = BotState.CONNECTING
        logger.info(
            {
                "event": "bot.starting",
                "shard_id": self.config.shard_id,
                "shard_count": self.config.shard_count,
                "intents": int(self.config.intents),
                "drop_pending_updates": self._drop_pending_updates,
            },
            extra=self._log_extra(),
        )

        try:
            await self._connect_gateway()
            await self._receive_messages()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except asyncio.CancelledError:
            logger.info("Bot start task cancelled")
        finally:
            await self.stop()

    async def wait_until_ready(self, wait_timeout: float | None = None) -> bool:
        """
        Wait for the bot to become ready.

        Returns:
            True if ready was reached before timeout, otherwise False.
        """
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=wait_timeout)
        except TimeoutError:
            return False
        return True

    async def stop(self) -> None:
        """Stop the bot client."""
        self._running = False
        self._state = BotState.STOPPING
        self._ready_event.clear()

        await self.runtime.stop()
        if self._command_sync_retry_task is not None and not self._command_sync_retry_task.done():
            self._command_sync_retry_task.cancel()
        await self.api_client.close()
        await self._close_session()
        self._state = BotState.STOPPED
        logger.info({"event": "bot.stopped"}, extra=self._log_extra())

    async def send_message(
        self,
        channel_id: int,
        content: str | None = None,
        *,
        tts: bool = False,
        embeds: list[dict[str, Any]] | None = None,
        allowed_mentions: dict[str, Any] | None = None,
        components: list[dict[str, Any]] | None = None,
        sticker_ids: list[int] | None = None,
        message_reference: dict[str, Any] | None = None,
        flags: int | None = None,
        poll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a message; delegates to :class:`MessageService`."""
        return await self._messages.send_message(
            channel_id,
            content,
            tts=tts,
            embeds=embeds,
            allowed_mentions=allowed_mentions,
            components=components,
            sticker_ids=sticker_ids,
            message_reference=message_reference,
            flags=flags,
            poll=poll,
        )
    async def reply(
        self,
        channel_id: int,
        message_id: int,
        content: str,
        *,
        tts: bool = False,
        allowed_mentions: dict[str, Any] | None = None,
        mention_author: bool = True,
    ) -> dict[str, Any]:
        return await self._messages.reply(
            channel_id, message_id, content,
            tts=tts, allowed_mentions=allowed_mentions, mention_author=mention_author,
        )
    async def send_components_v2(
        self,
        channel_id: int,
        components: list[dict[str, Any]],
        *,
        allowed_mentions: dict[str, Any] | None = None,
        flags: int = 0,
    ) -> dict[str, Any]:
        return await self._messages.send_components_v2(
            channel_id, components,
            allowed_mentions=allowed_mentions, flags=flags,
        )
    async def send_dm(self, user_id: int, content: str, **kwargs: Any) -> Message:
        return await self._messages.send_dm(user_id, content, **kwargs)
    async def send_message_to_user(self, user_id: int, content: str, **kwargs: Any) -> Message:
        return await self._messages.send_message_to_user(user_id, content, **kwargs)
    async def send_poll(
        self,
        channel_id: int,
        question: str,
        answers: list[str],
        *,
        duration_hours: int = 24,
        allow_multiselect: bool = False,
        content: str | None = None,
    ) -> dict[str, Any]:
        return await self._messages.send_poll(
            channel_id, question, answers,
            duration_hours=duration_hours,
            allow_multiselect=allow_multiselect,
            content=content,
        )
    async def trigger_typing(self, channel_id: int) -> None:
        await self._messages.trigger_typing(channel_id)
    async def list_messages(
        self,
        channel_id: int,
        *,
        limit: int = 50,
        before: int | None = None,
        after: int | None = None,
        around: int | None = None,
    ) -> list[Message]:
        return await self._messages.list_messages(
            channel_id, limit=limit, before=before, after=after, around=around,
        )
    async def fetch_message(self, channel_id: int, message_id: int) -> Message:
        return await self._messages.fetch_message(channel_id, message_id)
    async def edit_message(self, channel_id: int, message_id: int, **payload: Any) -> Message:
        return await self._messages.edit_message(channel_id, message_id, **payload)
    async def delete_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._messages.delete_message(channel_id, message_id)
    async def crosspost_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._messages.crosspost_message(channel_id, message_id)
    async def add_reaction(self, channel_id: int, message_id: int, emoji: str) -> dict[str, Any]:
        return await self._messages.add_reaction(channel_id, message_id, emoji)
    async def delete_own_reaction(self, channel_id: int, message_id: int, emoji: str) -> dict[str, Any]:
        return await self._messages.delete_own_reaction(channel_id, message_id, emoji)
    async def delete_user_reaction(
        self,
        channel_id: int,
        message_id: int,
        emoji: str,
        user_id: int,
    ) -> dict[str, Any]:
        return await self._messages.delete_user_reaction(channel_id, message_id, emoji, user_id)
    async def list_reactions(self, channel_id: int, message_id: int, emoji: str, **params: Any) -> list[User]:
        return await self._messages.list_reactions(channel_id, message_id, emoji, **params)
    async def clear_reactions(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._messages.clear_reactions(channel_id, message_id)
    async def clear_reaction(self, channel_id: int, message_id: int, emoji: str) -> dict[str, Any]:
        return await self._messages.clear_reaction(channel_id, message_id, emoji)
    async def bulk_delete_messages(self, channel_id: int, message_ids: list[int]) -> dict[str, Any]:
        return await self._messages.bulk_delete_messages(channel_id, message_ids)
    async def list_pins(self, channel_id: int) -> list[Message]:
        return await self._messages.list_pins(channel_id)
    async def get_channel_pins(
        self,
        channel_id: int,
        *,
        before: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return await self._messages.get_channel_pins(channel_id, before=before, limit=limit)
    async def pin_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._messages.pin_message(channel_id, message_id)
    async def unpin_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._messages.unpin_message(channel_id, message_id)
    async def pin_channel_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._messages.pin_channel_message(channel_id, message_id)
    async def unpin_channel_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._messages.unpin_channel_message(channel_id, message_id)
    async def get_poll_answer_voters(
        self,
        channel_id: int,
        message_id: int,
        answer_id: int,
        **params: Any,
    ) -> list[User]:
        return await self._messages.get_poll_answer_voters(
            channel_id, message_id, answer_id, **params,
        )
    async def end_poll(self, channel_id: int, message_id: int) -> Message:
        return await self._messages.end_poll(channel_id, message_id)
    async def delete_webhook(self, *, drop_pending_updates: bool = False) -> dict[str, Any]:
        """Compatibility helper for aiogram-like startup flows."""
        if "discord.com/api" in self.config.base_url:
            logger.debug("Discord gateway bots do not use webhooks; delete_webhook is a no-op.")
            return {}
        try:
            return await self.request(
                "POST",
                "/webhooks",
                json={"drop_pending_updates": drop_pending_updates},
            )
        except DiscordError as exc:
            if "404" in exc.message:
                logger.debug("Webhook deletion is not supported by this API endpoint.")
                return {}
            raise

    def enable_drop_pending_updates(self) -> None:
        """Drop gateway events until READY is received."""
        self._drop_pending_updates = True
        logger.info({"event": "bot.drop_pending_updates.enabled"}, extra=self._log_extra())

    async def get_current_application(self) -> Application:
        data = await self.request("GET", "/applications/@me")
        return Application.from_dict(data)

    async def edit_current_application(self, **payload: Any) -> Application:
        data = await self.request("PATCH", "/applications/@me", json=payload)
        return Application.from_dict(data)

    async def get_application_role_connection_metadata(
        self,
        application_id: int,
    ) -> list[ApplicationRoleConnectionMetadata]:
        data = await self.request(
            "GET",
            f"/applications/{application_id}/role-connections/metadata",
        )
        items = cast(list[dict[str, Any]], data)
        return [ApplicationRoleConnectionMetadata.from_dict(item) for item in items]

    async def update_application_role_connection_metadata(
        self,
        application_id: int,
        records: list[ApplicationRoleConnectionMetadata],
    ) -> list[ApplicationRoleConnectionMetadata]:
        if len(records) > 5:
            raise ValueError("Discord allows at most 5 role connection metadata records")
        data = await self.request(
            "PUT",
            f"/applications/{application_id}/role-connections/metadata",
            json=[item.to_dict() for item in records],
        )
        items = cast(list[dict[str, Any]], data)
        return [ApplicationRoleConnectionMetadata.from_dict(item) for item in items]

    async def fetch_channel(self, channel_id: int) -> Channel:
        """Fetch and parse a channel from the API."""
        data = await self.api_client.fetch_channel(channel_id)
        channel = self._parse_channel(data)
        self._channels[channel.id] = channel
        return channel

    async def modify_channel(self, channel_id: int, **payload: Any) -> Channel:
        """Modify and parse a channel from the API."""
        data = await self.api_client.modify_channel(channel_id, payload)
        channel = self._parse_channel(data)
        self._channels[channel.id] = channel
        return channel

    async def delete_channel(self, channel_id: int) -> dict[str, Any]:
        """Delete a channel and clear it from the local cache."""
        result = await self.api_client.delete_channel(channel_id)
        self._channels.pop(channel_id, None)
        return result

    async def list_channel_invites(self, channel_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_channel_invites(channel_id)

    async def create_channel_invite(self, channel_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.create_channel_invite(channel_id, payload)

    async def edit_channel_permissions(
        self,
        channel_id: int,
        overwrite_id: int,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.edit_channel_permissions(channel_id, overwrite_id, payload)

    async def delete_channel_permission(self, channel_id: int, overwrite_id: int) -> dict[str, Any]:
        return await self.api_client.delete_channel_permission(channel_id, overwrite_id)

    async def follow_news_channel(self, channel_id: int, webhook_channel_id: int) -> dict[str, Any]:
        return await self.api_client.follow_news_channel(channel_id, webhook_channel_id)

    async def start_thread_from_message(self, channel_id: int, message_id: int, **payload: Any) -> Channel:
        data = await self.api_client.start_thread_from_message(channel_id, message_id, payload)
        return self._parse_channel(data)

    async def start_thread_without_message(self, channel_id: int, **payload: Any) -> Channel:
        data = await self.api_client.start_thread_without_message(channel_id, payload)
        return self._parse_channel(data)

    async def join_thread(self, channel_id: int) -> dict[str, Any]:
        return await self.api_client.join_thread(channel_id)

    async def leave_thread(self, channel_id: int) -> dict[str, Any]:
        return await self.api_client.leave_thread(channel_id)

    async def add_thread_member(self, channel_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.add_thread_member(channel_id, user_id)

    async def remove_thread_member(self, channel_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.remove_thread_member(channel_id, user_id)

    async def list_public_archived_threads(self, channel_id: int, **params: Any) -> dict[str, Any]:
        return await self.api_client.list_public_archived_threads(channel_id, **params)

    async def list_private_archived_threads(self, channel_id: int, **params: Any) -> dict[str, Any]:
        return await self.api_client.list_private_archived_threads(channel_id, **params)

    async def list_joined_private_archived_threads(self, channel_id: int, **params: Any) -> dict[str, Any]:
        return await self.api_client.list_joined_private_archived_threads(channel_id, **params)

    async def fetch_guild(self, guild_id: int) -> Guild:
        """Fetch and parse a guild from the API."""
        data = await self.api_client.fetch_guild(guild_id)
        guild = self._parse_guild(data)
        self._guilds[guild.id] = guild
        return guild

    async def fetch_guild_preview(self, guild_id: int) -> dict[str, Any]:
        return await self.api_client.fetch_guild_preview(guild_id)

    async def list_guild_channels(self, guild_id: int) -> list[Channel]:
        """List and parse guild channels from the API."""
        items = await self.api_client.list_guild_channels(guild_id)
        channels = [self._parse_channel(item) for item in items]
        for channel in channels:
            self._channels[channel.id] = channel
        return channels

    async def list_guild_roles(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_roles(guild_id)

    async def create_guild_role(self, guild_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.create_guild_role(guild_id, payload)

    async def modify_guild_role_positions(
        self,
        guild_id: int,
        positions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return await self.api_client.modify_guild_role_positions(guild_id, positions)

    async def modify_guild_role(self, guild_id: int, role_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.modify_guild_role(guild_id, role_id, payload)

    async def delete_guild_role(self, guild_id: int, role_id: int) -> dict[str, Any]:
        return await self.api_client.delete_guild_role(guild_id, role_id)

    async def get_guild_member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.get_guild_member(guild_id, user_id)

    async def list_guild_members(self, guild_id: int, **params: Any) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_members(guild_id, **params)

    async def add_guild_member(self, guild_id: int, user_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.add_guild_member(guild_id, user_id, payload)

    async def modify_guild_member(self, guild_id: int, user_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.modify_guild_member(guild_id, user_id, payload)

    async def remove_guild_member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.remove_guild_member(guild_id, user_id)

    async def ban_guild_member(self, guild_id: int, user_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.ban_guild_member(guild_id, user_id, **payload)

    async def unban_guild_member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.unban_guild_member(guild_id, user_id)

    async def list_guild_bans(self, guild_id: int, **params: Any) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_bans(guild_id, **params)

    async def get_guild_ban(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self.api_client.get_guild_ban(guild_id, user_id)

    async def list_guild_emojis(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_emojis(guild_id)

    async def list_guild_stickers(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_stickers(guild_id)

    async def list_scheduled_events(self, guild_id: int, **params: Any) -> list[dict[str, Any]]:
        return await self.api_client.list_scheduled_events(guild_id, **params)

    async def create_scheduled_event(self, guild_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.create_scheduled_event(guild_id, payload)

    async def fetch_scheduled_event(self, guild_id: int, event_id: int, **params: Any) -> dict[str, Any]:
        return await self.api_client.fetch_scheduled_event(guild_id, event_id, **params)

    async def modify_scheduled_event(
        self,
        guild_id: int,
        event_id: int,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.modify_scheduled_event(guild_id, event_id, payload)

    async def delete_scheduled_event(self, guild_id: int, event_id: int) -> dict[str, Any]:
        return await self.api_client.delete_scheduled_event(guild_id, event_id)

    async def fetch_user(self, user_id: int) -> User:
        """Fetch and parse a user from the API."""
        data = await self.api_client.fetch_user(user_id)
        user = self._parse_user(data)
        self._users[user.id] = user
        return user

    async def get_current_user(self) -> User:
        """Get the current bot user via REST."""
        data = await self.api_client.get_current_user()
        user = self._parse_user(data)
        self._remember_bot_user(user)
        return user

    async def modify_current_user(self, **payload: Any) -> User:
        """Modify the current user settings (username/avatar/banner)."""
        data = await self.api_client.modify_current_user(payload)
        user = self._parse_user(data)
        self._remember_bot_user(user)
        return user

    async def get_current_user_guilds(self, **params: Any) -> list[Guild]:
        """Get current user guild list (/users/@me/guilds)."""
        data = await self.api_client.get_current_user_guilds(**params)
        guilds = [self._parse_guild(item) for item in data]
        for guild in guilds:
            self._guilds[guild.id] = guild
        return guilds

    async def get_current_user_guild_member(self, guild_id: int) -> dict[str, Any]:
        """Get current user guild member object for a guild."""
        return await self.api_client.get_current_user_guild_member(guild_id)

    async def leave_guild(self, guild_id: int) -> dict[str, Any]:
        """Leave a guild as current user."""
        result = await self.api_client.leave_guild(guild_id)
        self._guilds.pop(guild_id, None)
        return result

    async def create_group_dm(self, access_tokens: list[str], nicks: dict[str, str]) -> Channel:
        data = await self.api_client.create_group_dm(access_tokens, nicks)
        return self._parse_channel(data)

    async def get_current_user_connections(self) -> list[dict[str, Any]]:
        return await self.api_client.get_current_user_connections()

    async def get_current_user_application_role_connection(self, application_id: int) -> dict[str, Any]:
        return await self.api_client.get_current_user_application_role_connection(application_id)

    async def update_current_user_application_role_connection(
        self,
        application_id: int,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.update_current_user_application_role_connection(application_id, payload)

    async def fetch_invite(self, invite_code: str, **params: Any) -> dict[str, Any]:
        return await self.api_client.fetch_invite(invite_code, **params)

    async def delete_invite(self, invite_code: str) -> dict[str, Any]:
        return await self.api_client.delete_invite(invite_code)

    async def create_webhook(self, channel_id: int, **payload: Any) -> dict[str, Any]:
        return await self.api_client.create_webhook(channel_id, payload)

    async def list_channel_webhooks(self, channel_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_channel_webhooks(channel_id)

    async def list_guild_webhooks(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.api_client.list_guild_webhooks(guild_id)

    async def execute_webhook(
        self,
        webhook_id: int,
        token: str,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.execute_webhook(webhook_id, token, payload)

    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.create_interaction_response(
            interaction_id,
            interaction_token,
            payload,
        )

    async def create_followup_message(
        self,
        application_id: int,
        interaction_token: str,
        **payload: Any,
    ) -> dict[str, Any]:
        return await self.api_client.create_followup_message(
            application_id,
            interaction_token,
            payload,
        )

    def run(self, *, drop_pending_updates: bool = False) -> None:
        """Run the bot (blocking)."""
        try:
            if drop_pending_updates:
                self.enable_drop_pending_updates()
            asyncio.run(self.start())
        except KeyboardInterrupt:
            pass

    def __repr__(self) -> str:
        return f"<Bot name='{self.name}' ready={self.is_ready}>"
