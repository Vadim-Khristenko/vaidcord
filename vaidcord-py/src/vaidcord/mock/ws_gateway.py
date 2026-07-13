"""Networked mock Discord gateway.

This module implements the server side of the Discord gateway protocol for
:class:`vaidcord.mock.MockDiscordServer`. Unlike :class:`vaidcord.mock.MockGateway`
(an in-process test double), this speaks real WebSocket frames on ``/gateway``
so an actual :class:`vaidcord.Bot` can connect end-to-end:

* ``op 10 HELLO`` on connect (configurable ``heartbeat_interval``)
* ``op 2 IDENTIFY``  -> ``READY`` dispatch with ``session_id`` and a
  ``resume_gateway_url`` pointing back at the mock
* ``op 1 HEARTBEAT`` -> ``op 11 HEARTBEAT_ACK``
* ``op 6 RESUME``    -> replay of buffered events past the client's ``seq``,
  then a ``RESUMED`` dispatch (unknown sessions get ``op 9 INVALID_SESSION``)
* server-initiated ``op 7 RECONNECT`` / ``op 9 INVALID_SESSION`` via the
  control plane for exercising reconnect logic

Every session keeps a ring buffer of dispatched events (size configurable via
:class:`vaidcord.mock.MockServerConfig.event_buffer_size`) so RESUME replay
works even after the socket dropped.
"""

from __future__ import annotations

import json
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from aiohttp import WSMsgType, web

from vaidcord.logging import get_logger

if TYPE_CHECKING:
    from vaidcord.mock.server import MockDiscordServer

logger = get_logger(__name__, category="MOCK")

# Gateway opcodes (subset used by the mock).
OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_PRESENCE_UPDATE = 3
OP_VOICE_STATE_UPDATE = 4
OP_RESUME = 6
OP_RECONNECT = 7
OP_REQUEST_GUILD_MEMBERS = 8
OP_INVALID_SESSION = 9
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11

_NON_REPLAYABLE = frozenset({"READY", "RESUMED"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class GatewaySession:
    """One identified gateway session (survives socket drops for RESUME)."""

    session_id: str
    user: dict[str, Any]
    intents: int = 0
    shard: list[int] = field(default_factory=lambda: [0, 1])
    seq: int = 0
    ws: web.WebSocketResponse | None = None
    buffer: deque[dict[str, Any]] = field(default_factory=deque)
    identified_at: str = field(default_factory=_now_iso)
    last_heartbeat_at: str | None = None
    heartbeats: int = 0
    resume_count: int = 0

    @property
    def connected(self) -> bool:
        return self.ws is not None and not self.ws.closed

    def info(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user": dict(self.user),
            "intents": self.intents,
            "shard": list(self.shard),
            "seq": self.seq,
            "connected": self.connected,
            "identified_at": self.identified_at,
            "last_heartbeat_at": self.last_heartbeat_at,
            "heartbeats": self.heartbeats,
            "resume_count": self.resume_count,
            "buffered_events": len(self.buffer),
        }


class GatewayHub:
    """Owns all gateway sessions and event broadcasting for the mock server."""

    def __init__(
        self,
        server: MockDiscordServer,
        *,
        notify: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._server = server
        self._notify = notify or (lambda payload: None)
        self.sessions: dict[str, GatewaySession] = {}
        self.events_dispatched = 0
        self.connections_seen = 0

    # ------------------------------------------------------------------ #
    # WebSocket handler                                                  #
    # ------------------------------------------------------------------ #

    async def handle(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections_seen += 1
        config = self._server.config
        await ws.send_json(
            {
                "op": OP_HELLO,
                "d": {
                    "heartbeat_interval": config.heartbeat_interval_ms,
                    "_trace": ["vaidcord-mock"],
                },
            }
        )
        session: GatewaySession | None = None
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    break
                try:
                    payload = json.loads(msg.data)
                except (TypeError, ValueError):
                    await ws.close(code=4002, message=b"Decode error")
                    break
                if not isinstance(payload, dict):
                    await ws.close(code=4002, message=b"Decode error")
                    break
                session = await self._handle_payload(ws, session, payload)
                if ws.closed:
                    break
        finally:
            if session is not None and session.ws is ws:
                session.ws = None
                self._emit("session.disconnect", session)
        return ws

    async def _handle_payload(
        self,
        ws: web.WebSocketResponse,
        session: GatewaySession | None,
        payload: dict[str, Any],
    ) -> GatewaySession | None:
        op = payload.get("op")
        data = payload.get("d")

        if op == OP_HEARTBEAT:
            if session is not None:
                session.heartbeats += 1
                session.last_heartbeat_at = _now_iso()
            await ws.send_json({"op": OP_HEARTBEAT_ACK})
            return session

        if op == OP_IDENTIFY:
            identify = data if isinstance(data, dict) else {}
            token = str(identify.get("token") or "")
            if not token:
                await ws.close(code=4004, message=b"Authentication failed.")
                return session
            session = self._create_session(ws, identify)
            await self._send_ready(session)
            self._emit("session.identify", session)
            return session

        if op == OP_RESUME:
            resume = data if isinstance(data, dict) else {}
            return await self._handle_resume(ws, resume)

        if op in (OP_PRESENCE_UPDATE, OP_VOICE_STATE_UPDATE, OP_REQUEST_GUILD_MEMBERS):
            return session  # accepted, intentionally inert

        await ws.close(code=4001, message=b"Unknown opcode")
        return session

    # ------------------------------------------------------------------ #
    # Session lifecycle                                                  #
    # ------------------------------------------------------------------ #

    def _create_session(
        self,
        ws: web.WebSocketResponse,
        identify: dict[str, Any],
    ) -> GatewaySession:
        session = GatewaySession(
            session_id=uuid.uuid4().hex,
            user=dict(self._server.current_user),
            intents=int(identify.get("intents") or 0),
            shard=list(identify.get("shard") or [0, 1]),
            ws=ws,
            buffer=deque(maxlen=self._server.config.event_buffer_size),
        )
        self.sessions[session.session_id] = session
        logger.info(
            {
                "event": "mock.gateway.identify",
                "session_id": session.session_id,
                "intents": session.intents,
            }
        )
        return session

    async def _send_ready(self, session: GatewaySession) -> None:
        ready = {
            "v": 10,
            "user": dict(self._server.current_user),
            "session_id": session.session_id,
            "resume_gateway_url": self._server.ws_url,
            "guilds": [dict(guild) for guild in self._server.guilds.values()],
            "application": {"id": str(self._server.current_user.get("id", "1")), "flags": 0},
            "shard": list(session.shard),
        }
        await self._send_event(session, "READY", ready)

    async def _handle_resume(
        self,
        ws: web.WebSocketResponse,
        resume: dict[str, Any],
    ) -> GatewaySession | None:
        session_id = str(resume.get("session_id") or "")
        session = self.sessions.get(session_id)
        if session is None:
            # Unknown/expired session: client must re-identify.
            await ws.send_json({"op": OP_INVALID_SESSION, "d": False})
            return None
        try:
            client_seq = int(resume.get("seq") or 0)
        except (TypeError, ValueError):
            client_seq = 0
        session.ws = ws
        session.resume_count += 1
        replayed = 0
        for buffered in list(session.buffer):
            if buffered["s"] > client_seq:
                await ws.send_json(buffered)
                replayed += 1
        await self._send_event(session, "RESUMED", {"_trace": ["vaidcord-mock"]})
        logger.info(
            {
                "event": "mock.gateway.resumed",
                "session_id": session.session_id,
                "replayed": replayed,
                "client_seq": client_seq,
            }
        )
        self._emit("session.resume", session)
        return session

    # ------------------------------------------------------------------ #
    # Broadcasting                                                       #
    # ------------------------------------------------------------------ #

    async def _send_event(
        self,
        session: GatewaySession,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        session.seq += 1
        payload = {"op": OP_DISPATCH, "t": event_type, "s": session.seq, "d": data}
        if event_type not in _NON_REPLAYABLE:
            session.buffer.append(payload)
        if session.connected and session.ws is not None:
            try:
                await session.ws.send_json(payload)
            except ConnectionError:  # socket died mid-send; keep buffering
                session.ws = None

    async def dispatch(self, event_type: str, data: dict[str, Any]) -> int:
        """Broadcast a dispatch to every session; returns live deliveries."""
        delivered = 0
        for session in list(self.sessions.values()):
            was_connected = session.connected
            await self._send_event(session, event_type, data)
            if was_connected:
                delivered += 1
        self.events_dispatched += 1
        self._notify(
            {
                "kind": "dispatch",
                "t": event_type,
                "at": _now_iso(),
                "delivered": delivered,
                "sessions": len(self.sessions),
            }
        )
        return delivered

    async def request_reconnect(self, session_id: str | None = None) -> int:
        """Send ``op 7 RECONNECT`` to one or all connected sessions."""
        sent = 0
        for session in self._select(session_id):
            if session.connected and session.ws is not None:
                await session.ws.send_json({"op": OP_RECONNECT, "d": None})
                sent += 1
        return sent

    async def invalidate_session(
        self,
        session_id: str | None = None,
        *,
        resumable: bool = False,
    ) -> int:
        """Send ``op 9 INVALID_SESSION`` to one or all connected sessions."""
        sent = 0
        for session in self._select(session_id):
            if session.connected and session.ws is not None:
                await session.ws.send_json({"op": OP_INVALID_SESSION, "d": resumable})
                sent += 1
            if not resumable:
                self.sessions.pop(session.session_id, None)
        return sent

    def _select(self, session_id: str | None) -> list[GatewaySession]:
        if session_id is None:
            return list(self.sessions.values())
        session = self.sessions.get(session_id)
        return [session] if session is not None else []

    # ------------------------------------------------------------------ #
    # Introspection / lifecycle                                          #
    # ------------------------------------------------------------------ #

    def sessions_info(self) -> list[dict[str, Any]]:
        return [session.info() for session in self.sessions.values()]

    def _emit(self, kind: str, session: GatewaySession) -> None:
        self._notify(
            {
                "kind": kind,
                "session_id": session.session_id,
                "at": _now_iso(),
                "sessions": len(self.sessions),
            }
        )

    async def close_all(self) -> None:
        for session in list(self.sessions.values()):
            if session.connected and session.ws is not None:
                await session.ws.close(code=1000, message=b"Mock server stopping")
                session.ws = None

    def reset(self) -> None:
        self.sessions.clear()
        self.events_dispatched = 0
