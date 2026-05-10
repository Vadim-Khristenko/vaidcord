"""Aiohttp transport session ownership.

:class:`TransportSession` is the only place in the HTTP layer that knows
about ``aiohttp``. It owns the ``ClientSession`` and ``TCPConnector`` and
exposes a small, mockable surface that the rest of the HTTP layer can
depend on.

Splitting it out means alternative transports (mock servers, in-process
fakes, eventually a non-aiohttp implementation) can be plugged in without
touching the rate-limit, retry, or request-routing code.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import aiohttp
from aiohttp import ClientSession, TCPConnector

from vaidcord.metadata import __version__, build_user_agent

from .config import HTTPConfig


class TransportSession:
    """Owns the aiohttp session lifecycle for an :class:`HTTPClient`."""

    def __init__(
        self,
        config: HTTPConfig,
        *,
        session_provider: Callable[[], Awaitable[ClientSession]] | None = None,
        session_closer: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._session: ClientSession | None = None
        self._session_provider = session_provider
        self._session_closer = session_closer

    @property
    def config(self) -> HTTPConfig:
        return self._config

    @property
    def headers(self) -> dict[str, str]:
        user_agent = self._config.user_agent or build_user_agent()
        return {
            "Authorization": f"Bot {self._config.token}",
            "User-Agent": user_agent,
            "X-VaidCord-Version": __version__,
        }

    async def get_session(self) -> ClientSession:
        if self._session_provider is not None:
            return await self._session_provider()
        if self._session is None or self._session.closed:
            connector = TCPConnector(limit=self._config.connector_limit)
            self._session = ClientSession(
                connector=connector,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=self._config.timeout),
            )
        return self._session

    async def close(self) -> None:
        if self._session_closer is not None:
            await self._session_closer()
            return
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


__all__ = ["TransportSession"]
