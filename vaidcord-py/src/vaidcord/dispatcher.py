from __future__ import annotations

import asyncio
from typing import Any, Protocol

from vaidcord.fsm import BaseFSMStorage, FSMMiddleware, MemoryFSMStorage
from vaidcord.router import Router
from vaidcord.types import Event
from vaidcord.typing import EventHandlerResult


class DispatcherBotProtocol(Protocol):
    def include_router(self, router: Router) -> None: ...

    async def start(self) -> None: ...

    async def delete_webhook(self, *, drop_pending_updates: bool = False) -> dict[str, Any]: ...


class Dispatcher(Router):
    """Top-level router with Bot/FSM wiring, inspired by Aiogram 3.x."""

    def __init__(
        self,
        bot: DispatcherBotProtocol | None = None,
        *,
        fsm: FSMMiddleware | None = None,
        storage: BaseFSMStorage | None = None,
        name: str = "dispatcher",
    ) -> None:
        super().__init__(name=name)
        self.bot = bot
        resolved_storage = storage or MemoryFSMStorage()
        self.fsm = fsm or FSMMiddleware(storage=resolved_storage)
        self.add_outer_middleware(self.fsm)
        self._active_bots: set[DispatcherBotProtocol] = set()
        self._started = False
        if bot is not None:
            self.provide("bot", bot)

    def setup_fsm(self, fsm: FSMMiddleware) -> None:
        self.fsm = fsm
        self.add_outer_middleware(fsm)

    async def startup(self) -> None:
        await self.emit_startup()

    async def shutdown(self) -> None:
        await self.emit_shutdown()

    async def reconnect(self) -> None:
        await self.emit_reconnect()

    async def feed_event(self, event: Event) -> EventHandlerResult:
        return await self.propagate_event(event)

    def include_router(self, router: Router) -> None:
        if isinstance(router, Dispatcher):
            raise ValueError("Dispatcher cannot include another Dispatcher")
        super().include_router(router)

    async def start_polling(
        self,
        bot: DispatcherBotProtocol,
        *,
        drop_pending_updates: bool = False,
    ) -> None:
        """
        Start bot and route events through dispatcher routers.
        """
        self.bot = bot
        self.provide("bot", bot)
        self._attach_to_bot(bot)
        if drop_pending_updates and hasattr(bot, "enable_drop_pending_updates"):
            bot.enable_drop_pending_updates()  # type: ignore[attr-defined]
        self._active_bots.add(bot)
        if not self._started:
            await self.startup()
            self._started = True
        try:
            await bot.start()
        finally:
            self._active_bots.discard(bot)
            if not self._active_bots and self._started:
                await self.shutdown()
                self._started = False

    def _attach_to_bot(self, bot: DispatcherBotProtocol) -> None:
        routers = getattr(bot, "_routers", None)
        if isinstance(routers, list) and self in routers:
            return
        if self._parent is None:
            bot.include_router(self)
            return
        if isinstance(routers, list):
            routers.append(self)
            return
        bot.include_router(self)

    async def start_websocket(
        self,
        bot: DispatcherBotProtocol,
        *,
        drop_pending_updates: bool = False,
    ) -> None:
        """Alias for explicit websocket startup."""
        await self.start_polling(bot, drop_pending_updates=drop_pending_updates)

    async def start_polling_many(
        self,
        bots: list[DispatcherBotProtocol],
        *,
        drop_pending_updates: bool = False,
    ) -> None:
        """Start multiple bots concurrently with shared dispatcher wiring."""
        if not bots:
            raise ValueError("start_polling_many requires at least one bot")
        await asyncio.gather(
            *(self.start_polling(bot, drop_pending_updates=drop_pending_updates) for bot in bots)
        )

    async def start_webhook(self, bot: DispatcherBotProtocol, *, drop_pending_updates: bool = False) -> None:
        """Webhook-style startup helper (webhook server integration is app-defined)."""
        await bot.delete_webhook(drop_pending_updates=drop_pending_updates)
        await self.start_polling(bot, drop_pending_updates=drop_pending_updates)

    async def start_webhook_many(
        self,
        bots: list[DispatcherBotProtocol],
        *,
        drop_pending_updates: bool = False,
    ) -> None:
        """Webhook-style startup for multiple bots concurrently."""
        if not bots:
            raise ValueError("start_webhook_many requires at least one bot")
        await asyncio.gather(
            *(self.start_webhook(bot, drop_pending_updates=drop_pending_updates) for bot in bots)
        )
