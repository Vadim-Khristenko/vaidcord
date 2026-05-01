from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from vaidcord.types import Event
from .base import BaseFilter, FilterCallable, run_filter
from .magic import _resolve_path


@dataclass(frozen=True)
class CustomFilter(BaseFilter):
    callback: FilterCallable
    async def __call__(self, event: Event) -> bool:
        return await run_filter(self.callback, event)


@dataclass(frozen=True)
class CommandFilter(BaseFilter):
    commands: tuple[str, ...]
    prefixes: tuple[str, ...] = ('/', '!', '.')
    ignore_case: bool = True
    path: str = 'message.content'

    async def __call__(self, event: Event) -> bool:
        text = _resolve_path(event, self.path, '')
        if not isinstance(text, str) or not text:
            return False
        token = text.strip().split(' ', 1)[0]
        cmd_set = {c.lower() for c in self.commands} if self.ignore_case else set(self.commands)
        for p in self.prefixes:
            if token.startswith(p):
                name = token[len(p):].split('@', 1)[0]
                name = name.lower() if self.ignore_case else name
                return name in cmd_set
        return False


class CommandStartFilter(CommandFilter):
    def __init__(self) -> None: super().__init__(("start",))
class CommandHelpFilter(CommandFilter):
    def __init__(self) -> None: super().__init__(("help",))
class CommandSettingsFilter(CommandFilter):
    def __init__(self) -> None: super().__init__(("settings",))


@dataclass(frozen=True)
class RegexFilter(BaseFilter):
    pattern: str
    flags: int = 0
    path: str = 'message.content'
    async def __call__(self, event: Event) -> bool:
        text = _resolve_path(event, self.path, '')
        return isinstance(text, str) and re.search(self.pattern, text, self.flags) is not None


@dataclass(frozen=True)
class UserFilter(BaseFilter):
    user_ids: set[int] | None = None
    usernames: set[str] | None = None
    allow_bots: bool | None = None
    async def __call__(self, event: Event) -> bool:
        user = event.user or (event.message.author if event.message else None)
        if user is None:
            return False
        if self.user_ids is not None and user.id not in self.user_ids:
            return False
        if self.usernames is not None and user.username not in self.usernames:
            return False
        if self.allow_bots is not None and user.bot != self.allow_bots:
            return False
        return True
