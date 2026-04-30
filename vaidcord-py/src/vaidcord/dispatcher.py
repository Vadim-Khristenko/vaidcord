from __future__ import annotations

from typing import Any

from vaidcord.bot import Bot
from vaidcord.fsm import FSMMiddleware, MemoryFSMStorage
from vaidcord.router import Router


class Dispatcher(Router):
    """Top-level router with Bot/FSM wiring, inspired by Aiogram 3.x."""

    def __init__(
        self,
        bot: Bot | None = None,
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

    async def start_polling(self, bot: Bot) -> None:
        """
        Start bot and route events through dispatcher routers.
        """
        self.bot = bot
        self.provide("bot", bot)
        bot.include_router(self)
        await self.startup()
        try:
            await bot.start()
        finally:
            await self.shutdown()

    async def start_websocket(self, bot: Bot) -> None:
        """Alias for explicit websocket startup."""
        await self.start_polling(bot)

    async def start_webhook(self, bot: Bot, *, drop_pending_updates: bool = False) -> None:
        """Webhook-style startup helper (webhook server integration is app-defined)."""
        await bot.delete_webhook(drop_pending_updates=drop_pending_updates)
        await self.start_polling(bot)
