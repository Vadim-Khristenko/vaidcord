from __future__ import annotations

from typing import Any

from vaidcord.bot import Bot
from vaidcord.fsm import FSMMiddleware
from vaidcord.router import Router


class Dispatcher(Router):
    """Top-level router with Bot/FSM wiring, inspired by Aiogram 3.x."""

    def __init__(self, bot: Bot | None = None, *, fsm: FSMMiddleware | None = None, name: str = "dispatcher") -> None:
        super().__init__(name=name)
        self.bot = bot
        self.fsm = fsm
        if bot is not None:
            self.provide("bot", bot)

    def setup_fsm(self, fsm: FSMMiddleware) -> None:
        self.fsm = fsm

    async def startup(self) -> None:
        await self.emit_startup()

    async def shutdown(self) -> None:
        await self.emit_shutdown()

    async def reconnect(self) -> None:
        await self.emit_reconnect()

    async def feed_event(self, event: Any) -> Any:
        return await self.propagate_event(event)
