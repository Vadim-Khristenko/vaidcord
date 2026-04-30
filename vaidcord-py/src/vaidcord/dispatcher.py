from __future__ import annotations

import asyncio
from typing import Any, Protocol

from vaidcord.fsm import FSMMiddleware, MemoryFSMStorage
from vaidcord.router import Router


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
        storage: Any | None = None,
        name: str = "dispatcher",
    ) -> None:
        super().__init__(name=name)
        self.bot = bot
        resolved_storage = storage or MemoryFSMStorage()
        self.fsm = fsm or FSMMiddleware(storage=resolved_storage)
        self.add_middleware(self.fsm)
        self._active_bots: set[DispatcherBotProtocol] = set()
        self._started = False
        if bot is not None:
            self.provide("bot", bot)

    def setup_fsm(self, fsm: FSMMiddleware) -> None:
        self.fsm = fsm
        self.add_middleware(fsm)

    async def startup(self) -> None:
        await self.emit_startup()

    async def shutdown(self) -> None:
        await self.emit_shutdown()

    async def reconnect(self) -> None:
        await self.emit_reconnect()

    async def feed_event(self, event: Any) -> Any:
        return await self.propagate_event(event)

    def include_router(self, router: Router) -> None:
        if isinstance(router, Dispatcher):
            raise ValueError("Dispatcher cannot include another Dispatcher")
        super().include_router(router)

    async def start_polling(self, bot: DispatcherBotProtocol) -> None:
        """
        Start bot and route events through dispatcher routers.
        """
        self.bot = bot
        self.provide("bot", bot)
        bot.include_router(self)
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

    async def start_websocket(self, bot: DispatcherBotProtocol) -> None:
        """Alias for explicit websocket startup."""
        await self.start_polling(bot)

    async def start_polling_many(self, bots: list[DispatcherBotProtocol]) -> None:
        """Start multiple bots concurrently with shared dispatcher wiring."""
        if not bots:
            raise ValueError("start_polling_many requires at least one bot")
        await asyncio.gather(*(self.start_polling(bot) for bot in bots))

    async def start_webhook(self, bot: DispatcherBotProtocol, *, drop_pending_updates: bool = False) -> None:
        """Webhook-style startup helper (webhook server integration is app-defined)."""
        await bot.delete_webhook(drop_pending_updates=drop_pending_updates)
        await self.start_polling(bot)

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
