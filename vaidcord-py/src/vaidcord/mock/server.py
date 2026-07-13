"""Aiohttp-based mock Discord server.

Simulates the Discord REST API (``/api/v10``) plus a real WebSocket gateway
(``/gateway``) so a genuine :class:`vaidcord.Bot` can run end-to-end against
it. A control plane under ``/api/mock/*`` drives state injection, chaos
testing, rate-limit simulation, scenario scripting and state snapshots, and
an optional single-file operator UI is served at ``/``.

See ``docs/MOCK.md`` for the full endpoint reference.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from aiohttp import web

from vaidcord.logging import get_logger
from vaidcord.mock.config import MockServerConfig
from vaidcord.mock.snowflake import SnowflakeGenerator
from vaidcord.mock.ui import MOCK_UI_HTML, validate_mock_ui
from vaidcord.mock.ws_gateway import GatewayHub

logger = get_logger(__name__, category="MOCK")

DEFAULT_GATEWAY_URL = "wss://gateway.discord.gg"

# Discord JSON error codes used by the simulation.
ERROR_UNKNOWN_GUILD = 10004
ERROR_UNKNOWN_CHANNEL = 10003
ERROR_UNKNOWN_MESSAGE = 10008
ERROR_UNKNOWN_USER = 10013
ERROR_MISSING_ACCESS = 50001
ERROR_EMPTY_MESSAGE = 50006
ERROR_INVALID_FORM_BODY = 50035
ERROR_INVALID_JSON = 50109

MAX_CONTENT_LENGTH = 2000


def _copy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return dict(payload)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _discord_error(
    status: int,
    message: str,
    code: int,
    *,
    errors: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> web.Response:
    body: dict[str, Any] = {"message": message, "code": code}
    if errors is not None:
        body["errors"] = errors
    body.update(extra)
    return web.json_response(body, status=status, headers=headers)


class _RateLimiter:
    """Fixed-window per-route + global rate limiter with Discord headers."""

    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = {}

    def reset(self) -> None:
        self._windows.clear()

    def snapshot(self) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        return {
            key: {"count": count, "expires_in": round(max(0.0, started - now), 3)}
            for key, (started, count) in self._windows.items()
        }

    def hit(self, key: str, limit: int, window: float) -> tuple[bool, int, float]:
        """Count a hit; returns ``(limited, remaining, reset_after)``.

        ``started`` in the window map stores the window *expiry* time so the
        snapshot/reset math stays trivial.
        """
        now = time.monotonic()
        expiry, count = self._windows.get(key, (0.0, 0))
        if now >= expiry:
            expiry, count = now + window, 0
        if count >= limit:
            self._windows[key] = (expiry, count)
            return True, 0, max(0.0, expiry - now)
        count += 1
        self._windows[key] = (expiry, count)
        return False, limit - count, max(0.0, expiry - now)

    @staticmethod
    def bucket_id(key: str) -> str:
        return hashlib.sha1(key.encode()).hexdigest()[:16]  # noqa: S324 - not security


@dataclass
class MockDiscordServer:
    """Aiohttp-based mock Discord server for integration tests and local testing."""

    host: str = "127.0.0.1"
    port: int = 18080
    enable_ui: bool = False
    gateway_url: str = DEFAULT_GATEWAY_URL
    config: MockServerConfig = field(default_factory=MockServerConfig)
    _app: web.Application = field(default_factory=web.Application, init=False)
    _runner: web.AppRunner | None = field(default=None, init=False)
    _site: web.TCPSite | None = field(default=None, init=False)
    requests: list[dict[str, Any]] = field(default_factory=list, init=False)
    messages: list[dict[str, Any]] = field(default_factory=list, init=False)
    typing_events: list[dict[str, Any]] = field(default_factory=list, init=False)
    users: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    channels: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    guilds: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    denied_channels: set[str] = field(default_factory=set, init=False)
    _messages_by_id: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _current_user: dict[str, Any] = field(default_factory=dict, init=False)
    _requests_by_id: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _snowflakes: SnowflakeGenerator = field(default_factory=SnowflakeGenerator, init=False)
    _rate_limiter: _RateLimiter = field(default_factory=_RateLimiter, init=False)
    _sse_queues: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set, init=False)
    _scenarios: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _scenario_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict, init=False)
    gateway_events: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=500), init=False
    )

    def __post_init__(self) -> None:
        validate_mock_ui()
        self._initial_config = replace(self.config)
        self.hub = GatewayHub(self, notify=self._notify_sse)
        self._seed_state()
        self._app.middlewares.append(self._access_log_middleware)
        self._app.middlewares.append(self._simulation_middleware)
        self._register_routes()

    def _register_routes(self) -> None:
        router = self._app.router
        router.add_get("/", self._ui)
        router.add_get("/gateway", self.hub.handle)

        # -- control plane ------------------------------------------------
        router.add_get("/api/mock/state", self._mock_state)
        router.add_post("/api/mock/messages", self._mock_message)
        router.add_post("/api/mock/profiles", self._create_profile)
        router.add_patch("/api/mock/profiles/{user_id}", self._update_profile)
        router.add_patch("/api/mock/current-user", self._set_current_user)
        router.add_post("/api/mock/reset", self._mock_reset)
        router.add_get("/api/mock/events", self._events_stream)
        router.add_get("/api/mock/chaos", self._get_chaos)
        router.add_post("/api/mock/chaos", self._set_chaos)
        router.add_patch("/api/mock/chaos", self._set_chaos)
        router.add_get("/api/mock/ratelimit", self._get_ratelimit)
        router.add_post("/api/mock/ratelimit", self._set_ratelimit)
        router.add_patch("/api/mock/ratelimit", self._set_ratelimit)
        router.add_get("/api/mock/permissions", self._get_permissions)
        router.add_post("/api/mock/permissions", self._set_permissions)
        router.add_get("/api/mock/state/export", self._export_state)
        router.add_post("/api/mock/state/import", self._import_state)
        router.add_get("/api/mock/scenario", self._list_scenarios)
        router.add_post("/api/mock/scenario", self._start_scenario)
        router.add_delete("/api/mock/scenario/{scenario_id}", self._cancel_scenario)
        router.add_get("/api/mock/gateway", self._gateway_state)
        router.add_post("/api/mock/gateway/reconnect", self._gateway_reconnect)
        router.add_post("/api/mock/gateway/invalidate", self._gateway_invalidate)

        # -- Discord REST surface ------------------------------------------
        router.add_get("/api/v10/gateway", self._gateway_plain)
        router.add_get("/api/v10/gateway/bot", self._gateway_bot)
        router.add_get("/api/v10/users/@me", self._get_current_user)
        router.add_get("/api/v10/users/{user_id}", self._get_user)
        router.add_get("/api/v10/users/@me/guilds", self._list_current_user_guilds)
        router.add_get("/api/v10/guilds/{guild_id}", self._get_guild)
        router.add_get("/api/v10/guilds/{guild_id}/channels", self._list_guild_channels)
        router.add_post("/api/v10/users/@me/channels", self._create_dm)

        router.add_get("/api/v10/channels/{channel_id}", self._get_channel)
        router.add_patch("/api/v10/channels/{channel_id}", self._edit_channel)
        router.add_delete("/api/v10/channels/{channel_id}", self._delete_channel)
        router.add_get("/api/v10/channels/{channel_id}/messages", self._list_messages)
        router.add_post("/api/v10/channels/{channel_id}/messages", self._send_message)
        router.add_get(
            "/api/v10/channels/{channel_id}/messages/{message_id}",
            self._get_message,
        )
        router.add_patch(
            "/api/v10/channels/{channel_id}/messages/{message_id}",
            self._edit_message,
        )
        router.add_delete(
            "/api/v10/channels/{channel_id}/messages/{message_id}",
            self._delete_message,
        )
        router.add_post("/api/v10/channels/{channel_id}/typing", self._trigger_typing)

    # ------------------------------------------------------------------ #
    # State seeding & shared helpers                                      #
    # ------------------------------------------------------------------ #

    def _seed_state(self) -> None:
        self.requests = []
        self.messages = []
        self.typing_events = []
        self._messages_by_id = {}
        self._requests_by_id = {}
        self.denied_channels = set()
        self.gateway_events.clear()
        self._current_user = {
            "id": "1",
            "username": "MockBot",
            "discriminator": "0",
            "bot": True,
        }
        self.users = {
            "1": _copy_payload(self._current_user),
            "2": {
                "id": "2",
                "username": "MockUser",
                "discriminator": "0",
                "bot": False,
            },
        }
        self.guilds = {
            "999": {
                "id": "999",
                "name": "Mock Guild",
                "owner": True,
                "owner_id": "1",
                "features": [],
                "member_count": 2,
            }
        }
        self.channels = {
            "123": {
                "id": "123",
                "type": 0,
                "name": "general",
                "topic": "Mock Discord workspace",
                "guild_id": "999",
            }
        }

    @property
    def current_user(self) -> dict[str, Any]:
        """The profile REST responses and gateway READY payloads act as."""
        return self._current_user

    @property
    def ws_url(self) -> str:
        """WebSocket URL of this mock's own gateway endpoint."""
        if self.gateway_url != DEFAULT_GATEWAY_URL:
            return self.gateway_url
        return f"ws://{self.host}:{self.port}/gateway"

    def _record_request(
        self,
        request: web.Request,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_id = request.get("mock_request_id")
        entry: dict[str, Any] = {
            "method": request.method,
            "path": str(request.rel_url),
        }
        if request_id is not None:
            entry["request_id"] = str(request_id)
            self._requests_by_id[str(request_id)] = entry
        if payload is not None:
            entry["json"] = payload
        self.requests.append(entry)
        return entry

    async def _read_json(self, request: web.Request) -> tuple[dict[str, Any], None] | tuple[None, web.Response]:
        try:
            payload = await request.json()
        except (ValueError, UnicodeDecodeError):
            self._record_request(request)
            return None, _discord_error(
                400, "The request body contains invalid JSON.", ERROR_INVALID_JSON
            )
        if not isinstance(payload, dict):
            self._record_request(request)
            return None, _discord_error(
                400, "The request body contains invalid JSON.", ERROR_INVALID_JSON
            )
        return payload, None

    # ------------------------------------------------------------------ #
    # Middlewares                                                         #
    # ------------------------------------------------------------------ #

    @web.middleware
    async def _access_log_middleware(
        self,
        request: web.Request,
        handler: Any,
    ) -> web.StreamResponse:
        request_id = str(uuid.uuid4())
        request["mock_request_id"] = request_id
        started = time.perf_counter()
        logger.info(
            {
                "event": "mock.request.start",
                "request_id": request_id,
                "method": request.method,
                "path": str(request.rel_url),
            }
        )
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            self._log_request_done(request_id, request, status=exc.status, started=started)
            raise
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                {
                    "event": "mock.request.error",
                    "request_id": request_id,
                    "method": request.method,
                    "path": str(request.rel_url),
                    "duration_ms": duration_ms,
                }
            )
            raise
        self._log_request_done(request_id, request, status=response.status, started=started)
        return response

    def _log_request_done(
        self,
        request_id: str,
        request: web.Request,
        *,
        status: int,
        started: float,
    ) -> None:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        entry = self._requests_by_id.pop(request_id, None)
        if entry is not None:
            entry["status"] = status
            entry["duration_ms"] = duration_ms
        logger.info(
            {
                "event": "mock.request.done",
                "request_id": request_id,
                "method": request.method,
                "path": str(request.rel_url),
                "status": status,
                "duration_ms": duration_ms,
            }
        )
        if not str(request.rel_url).startswith("/api/mock/events"):
            self._notify_sse(
                {
                    "kind": "request",
                    "method": request.method,
                    "path": str(request.rel_url),
                    "status": status,
                    "duration_ms": duration_ms,
                    "at": _utc_now_iso(),
                }
            )

    @web.middleware
    async def _simulation_middleware(
        self,
        request: web.Request,
        handler: Any,
    ) -> web.StreamResponse:
        """Chaos, permissions and rate-limit simulation for ``/api/v10``."""
        if not request.path.startswith("/api/v10"):
            return await handler(request)

        config = self.config

        # Permission enforcement (simple channel-level deny list).
        channel_id = request.match_info.get("channel_id")
        if (
            config.enforce_permissions
            and channel_id is not None
            and channel_id in self.denied_channels
        ):
            self._record_request(request)
            return _discord_error(403, "Missing Access", ERROR_MISSING_ACCESS)

        # Rate limiting.
        rl_headers: dict[str, str] = {}
        if config.rate_limit_enabled:
            limited_response = self._apply_rate_limits(request, rl_headers)
            if limited_response is not None:
                self._record_request(request)
                return limited_response

        # Chaos: latency injection.
        latency_ms = config.chaos_latency_ms
        if config.chaos_jitter_ms > 0:
            latency_ms += random.random() * config.chaos_jitter_ms  # noqa: S311
        if latency_ms > 0:
            await asyncio.sleep(latency_ms / 1000)

        # Chaos: error injection.
        if config.chaos_error_rate > 0 and random.random() < config.chaos_error_rate:  # noqa: S311
            self._record_request(request)
            return _discord_error(
                config.chaos_error_status,
                "Mock chaos error injected",
                config.chaos_error_code,
                headers={"X-Mock-Chaos": "error"},
            )

        response = await handler(request)
        for key, value in rl_headers.items():
            response.headers[key] = value
        return response

    def _bucket_key(self, request: web.Request) -> str:
        resource = request.match_info.route.resource
        canonical = resource.canonical if resource is not None else request.path
        major = request.match_info.get("channel_id") or request.match_info.get("guild_id") or "-"
        return f"{request.method}:{canonical}:{major}"

    def _apply_rate_limits(
        self,
        request: web.Request,
        rl_headers: dict[str, str],
    ) -> web.Response | None:
        config = self.config

        limited, _, reset_after = self._rate_limiter.hit(
            "__global__", config.global_rate_limit, config.global_rate_limit_window
        )
        if limited:
            retry_after = round(reset_after, 3)
            return _discord_error(
                429,
                "You are being rate limited.",
                0,
                retry_after=retry_after,
                headers={
                    "X-RateLimit-Global": "true",
                    "X-RateLimit-Scope": "global",
                    "Retry-After": str(retry_after),
                },
                **{"global": True},
            )

        key = self._bucket_key(request)
        limited, remaining, reset_after = self._rate_limiter.hit(
            key, config.rate_limit_per_route, config.rate_limit_window
        )
        bucket = self._rate_limiter.bucket_id(key)
        reset_at = time.time() + reset_after
        headers = {
            "X-RateLimit-Limit": str(config.rate_limit_per_route),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": f"{reset_at:.3f}",
            "X-RateLimit-Reset-After": f"{reset_after:.3f}",
            "X-RateLimit-Bucket": bucket,
        }
        if limited:
            retry_after = round(reset_after, 3)
            headers["Retry-After"] = str(retry_after)
            headers["X-RateLimit-Scope"] = "user"
            return _discord_error(
                429,
                "You are being rate limited.",
                0,
                retry_after=retry_after,
                headers=headers,
                **{"global": False},
            )
        rl_headers.update(headers)
        return None

    # ------------------------------------------------------------------ #
    # Gateway event fan-out                                               #
    # ------------------------------------------------------------------ #

    def _notify_sse(self, payload: dict[str, Any]) -> None:
        if payload.get("kind") == "dispatch":
            self.gateway_events.append(payload)
        for queue in list(self._sse_queues):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(payload)

    async def _dispatch(self, event_type: str, data: dict[str, Any]) -> int:
        return await self.hub.dispatch(event_type, data)

    async def _events_stream(self, request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse()
        response.content_type = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Accel-Buffering"] = "no"
        await response.prepare(request)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._sse_queues.add(queue)
        try:
            await response.write(b"event: hello\ndata: {}\n\n")
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    await response.write(b": keepalive\n\n")
                    continue
                if item.get("kind") == "__shutdown__":
                    break
                body = json.dumps(item)
                await response.write(f"data: {body}\n\n".encode())
        except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self._sse_queues.discard(queue)
        return response

    # ------------------------------------------------------------------ #
    # Entity helpers                                                      #
    # ------------------------------------------------------------------ #

    def _sync_guild_member_counts(self) -> None:
        member_count = len(self.users)
        for guild in self.guilds.values():
            guild["member_count"] = member_count

    def _ensure_user(
        self,
        user_id: str,
        *,
        username: str | None = None,
        bot: bool = False,
        discriminator: str | None = None,
        global_name: str | None = None,
    ) -> dict[str, Any]:
        existing = self.users.get(user_id)
        if existing is not None:
            if username:
                existing["username"] = username
            existing["bot"] = bot
            if discriminator is not None:
                existing["discriminator"] = discriminator
            if global_name is not None:
                existing["global_name"] = global_name
            return existing
        user = {
            "id": user_id,
            "username": username or f"User{user_id}",
            "discriminator": discriminator or "0",
            "bot": bot,
        }
        if global_name is not None:
            user["global_name"] = global_name
        self.users[user_id] = user
        self._sync_guild_member_counts()
        return user

    def _upsert_profile(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        profile = self._ensure_user(
            user_id,
            username=str(payload.get("username") or f"User{user_id}"),
            bot=bool(payload.get("bot", False)),
            discriminator=str(payload.get("discriminator", "0")),
            global_name=(
                str(payload["global_name"]) if payload.get("global_name") is not None else None
            ),
        )
        if "global_name" in payload and payload.get("global_name") in ("", None):
            profile.pop("global_name", None)
        self._sync_guild_member_counts()
        return profile

    def _ensure_guild(self, guild_id: str, *, name: str | None = None) -> dict[str, Any]:
        existing = self.guilds.get(guild_id)
        if existing is not None:
            if name:
                existing["name"] = name
            return existing
        guild = {
            "id": guild_id,
            "name": name or f"Guild {guild_id}",
            "owner": False,
            "owner_id": "1",
            "features": [],
            "member_count": len(self.users),
        }
        self.guilds[guild_id] = guild
        return guild

    def _ensure_channel(
        self,
        channel_id: str,
        *,
        channel_type: int = 0,
        name: str | None = None,
        guild_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self.channels.get(channel_id)
        if existing is not None:
            if name:
                existing["name"] = name
            if guild_id is not None:
                existing["guild_id"] = guild_id
            return existing
        channel = {
            "id": channel_id,
            "type": channel_type,
            "name": name or f"channel-{channel_id}",
        }
        if guild_id is not None:
            channel["guild_id"] = guild_id
        self.channels[channel_id] = channel
        return channel

    def _build_message(
        self,
        *,
        channel_id: str,
        content: str,
        author: dict[str, Any],
        guild_id: str | None = None,
        tts: bool = False,
    ) -> dict[str, Any]:
        message = {
            "id": self._snowflakes.generate_str(),
            "channel_id": channel_id,
            "content": content,
            "tts": tts,
            "timestamp": _utc_now_iso(),
            "edited_timestamp": None,
            "author": _copy_payload(author),
        }
        if guild_id is not None:
            message["guild_id"] = guild_id
        return message

    def _validate_message_payload(self, payload: dict[str, Any]) -> web.Response | None:
        if not self.config.strict_validation:
            return None
        content = payload.get("content")
        has_content = content is not None and str(content).strip() != ""
        has_alternative = any(
            payload.get(key)
            for key in ("embeds", "components", "sticker_ids", "attachments", "poll", "files")
        )
        if not has_content and not has_alternative:
            return _discord_error(400, "Cannot send an empty message", ERROR_EMPTY_MESSAGE)
        if has_content and len(str(content)) > MAX_CONTENT_LENGTH:
            return _discord_error(
                400,
                "Invalid Form Body",
                ERROR_INVALID_FORM_BODY,
                errors={
                    "content": {
                        "_errors": [
                            {
                                "code": "BASE_TYPE_MAX_LENGTH",
                                "message": f"Must be {MAX_CONTENT_LENGTH} or fewer in length.",
                            }
                        ]
                    }
                },
            )
        return None

    # ------------------------------------------------------------------ #
    # Control plane: UI / state / reset                                   #
    # ------------------------------------------------------------------ #

    async def _ui(self, request: web.Request) -> web.Response:
        if not self.enable_ui:
            raise web.HTTPNotFound
        self._record_request(request)
        return web.Response(text=MOCK_UI_HTML, content_type="text/html")

    async def _mock_state(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(
            {
                "base_url": self.base_url,
                "gateway_url": self.gateway_url,
                "ws_url": self.ws_url,
                "current_user": self._current_user,
                "requests": self.requests,
                "messages": self.messages,
                "typing_events": self.typing_events,
                "users": list(self.users.values()),
                "channels": list(self.channels.values()),
                "guilds": list(self.guilds.values()),
                "gateway": {
                    "sessions": self.hub.sessions_info(),
                    "events_dispatched": self.hub.events_dispatched,
                    "recent_events": list(self.gateway_events)[-50:],
                },
                "chaos": self._chaos_payload(),
                "rate_limit": self._ratelimit_payload(),
                "permissions": self._permissions_payload(),
                "scenarios": list(self._scenarios.values()),
            }
        )

    async def _mock_reset(self, request: web.Request) -> web.Response:
        self._record_request(request)
        self._seed_state()
        self.config = replace(self._initial_config)
        self._rate_limiter.reset()
        self.hub.reset()
        for task in self._scenario_tasks.values():
            task.cancel()
        self._scenario_tasks.clear()
        self._scenarios.clear()
        return web.json_response({"ok": True})

    # ------------------------------------------------------------------ #
    # Control plane: message/typing injection & profiles                  #
    # ------------------------------------------------------------------ #

    async def _inject_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        channel_id = str(payload.get("channel_id", "123"))
        guild_id = payload.get("guild_id")
        guild_name = payload.get("guild_name")
        channel_name = payload.get("channel_name")
        author_id = str(payload.get("author_id", "2"))
        author_name = str(payload.get("author_username", "MockUser"))
        author_bot = bool(payload.get("author_bot", False))

        if guild_id is not None:
            self._ensure_guild(str(guild_id), name=str(guild_name) if guild_name else None)
        self._ensure_channel(
            channel_id,
            channel_type=1 if guild_id is None and channel_id.startswith("dm-") else 0,
            name=str(channel_name) if channel_name else None,
            guild_id=str(guild_id) if guild_id is not None else None,
        )
        author = self._ensure_user(author_id, username=author_name, bot=author_bot)
        message = self._build_message(
            channel_id=channel_id,
            content=str(payload.get("content", "")),
            author=author,
            guild_id=str(guild_id) if guild_id is not None else None,
        )
        self.messages.append(message)
        self._messages_by_id[message["id"]] = message
        await self._dispatch("MESSAGE_CREATE", message)
        return message

    async def _mock_message(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        message = await self._inject_message(payload)
        return web.json_response(message)

    async def _create_profile(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        user_id = str(payload.get("id") or len(self.users) + 1)
        profile = self._upsert_profile(user_id, payload)
        if payload.get("set_current"):
            self._current_user = profile
        return web.json_response(profile)

    async def _update_profile(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        user_id = request.match_info["user_id"]
        if user_id not in self.users:
            raise web.HTTPNotFound(text='{"message":"Unknown User","code":10013}')
        updated = self._upsert_profile(user_id, {**self.users[user_id], **payload})
        if self._current_user["id"] == user_id:
            self._current_user = updated
        return web.json_response(updated)

    async def _set_current_user(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        user_id = str(payload.get("user_id", ""))
        user = self.users.get(user_id)
        if user is None:
            raise web.HTTPNotFound(text='{"message":"Unknown User","code":10013}')
        self._current_user = user
        return web.json_response(user)

    # ------------------------------------------------------------------ #
    # Control plane: chaos / rate limit / permissions                     #
    # ------------------------------------------------------------------ #

    def _chaos_payload(self) -> dict[str, Any]:
        return {
            "latency_ms": self.config.chaos_latency_ms,
            "jitter_ms": self.config.chaos_jitter_ms,
            "error_rate": self.config.chaos_error_rate,
            "error_status": self.config.chaos_error_status,
            "error_code": self.config.chaos_error_code,
        }

    async def _get_chaos(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(self._chaos_payload())

    def _apply_chaos_settings(self, payload: dict[str, Any]) -> None:
        if "latency_ms" in payload:
            self.config.chaos_latency_ms = max(0.0, float(payload["latency_ms"]))
        if "jitter_ms" in payload:
            self.config.chaos_jitter_ms = max(0.0, float(payload["jitter_ms"]))
        if "error_rate" in payload:
            self.config.chaos_error_rate = min(1.0, max(0.0, float(payload["error_rate"])))
        if "error_status" in payload:
            self.config.chaos_error_status = int(payload["error_status"])
        if "error_code" in payload:
            self.config.chaos_error_code = int(payload["error_code"])

    async def _set_chaos(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        try:
            self._apply_chaos_settings(payload)
        except (TypeError, ValueError):
            return _discord_error(400, "Invalid Form Body", ERROR_INVALID_FORM_BODY)
        self._notify_sse({"kind": "chaos", "at": _utc_now_iso(), **self._chaos_payload()})
        return web.json_response(self._chaos_payload())

    def _ratelimit_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.config.rate_limit_enabled,
            "per_route_limit": self.config.rate_limit_per_route,
            "per_route_window": self.config.rate_limit_window,
            "global_limit": self.config.global_rate_limit,
            "global_window": self.config.global_rate_limit_window,
        }

    async def _get_ratelimit(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(
            {**self._ratelimit_payload(), "buckets": self._rate_limiter.snapshot()}
        )

    async def _set_ratelimit(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        try:
            if "enabled" in payload:
                self.config.rate_limit_enabled = bool(payload["enabled"])
            if "per_route_limit" in payload:
                self.config.rate_limit_per_route = max(1, int(payload["per_route_limit"]))
            if "per_route_window" in payload:
                self.config.rate_limit_window = max(0.001, float(payload["per_route_window"]))
            if "global_limit" in payload:
                self.config.global_rate_limit = max(1, int(payload["global_limit"]))
            if "global_window" in payload:
                self.config.global_rate_limit_window = max(
                    0.001, float(payload["global_window"])
                )
        except (TypeError, ValueError):
            return _discord_error(400, "Invalid Form Body", ERROR_INVALID_FORM_BODY)
        self._rate_limiter.reset()
        return web.json_response(self._ratelimit_payload())

    def _permissions_payload(self) -> dict[str, Any]:
        return {
            "enforce": self.config.enforce_permissions,
            "denied_channels": sorted(self.denied_channels),
        }

    async def _get_permissions(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(self._permissions_payload())

    async def _set_permissions(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        if "enforce" in payload:
            self.config.enforce_permissions = bool(payload["enforce"])
        channel_id = payload.get("channel_id")
        if channel_id is not None:
            if payload.get("allow", False):
                self.denied_channels.discard(str(channel_id))
            else:
                self.denied_channels.add(str(channel_id))
        return web.json_response(self._permissions_payload())

    # ------------------------------------------------------------------ #
    # Control plane: snapshots                                            #
    # ------------------------------------------------------------------ #

    async def _export_state(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(
            {
                "version": 1,
                "exported_at": _utc_now_iso(),
                "current_user": self._current_user,
                "users": list(self.users.values()),
                "channels": list(self.channels.values()),
                "guilds": list(self.guilds.values()),
                "messages": self.messages,
                "typing_events": self.typing_events,
            }
        )

    async def _import_state(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload={"import": True})
        try:
            users = {str(user["id"]): dict(user) for user in payload.get("users", [])}
            channels = {
                str(channel["id"]): dict(channel) for channel in payload.get("channels", [])
            }
            guilds = {str(guild["id"]): dict(guild) for guild in payload.get("guilds", [])}
            messages = [dict(message) for message in payload.get("messages", [])]
            typing_events = [dict(event) for event in payload.get("typing_events", [])]
            messages_by_id = {str(message["id"]): message for message in messages}
        except (TypeError, KeyError):
            return _discord_error(400, "Invalid Form Body", ERROR_INVALID_FORM_BODY)
        if not users:
            return _discord_error(
                400,
                "Invalid Form Body",
                ERROR_INVALID_FORM_BODY,
                errors={"users": {"_errors": [{"code": "REQUIRED", "message": "Required"}]}},
            )
        self.users = users
        self.channels = channels
        self.guilds = guilds
        self.messages = messages
        self.typing_events = typing_events
        self._messages_by_id = messages_by_id
        current = payload.get("current_user") or {}
        current_id = str(current.get("id", ""))
        self._current_user = self.users.get(current_id) or next(iter(self.users.values()))
        self._sync_guild_member_counts()
        return web.json_response(
            {
                "ok": True,
                "users": len(self.users),
                "channels": len(self.channels),
                "guilds": len(self.guilds),
                "messages": len(self.messages),
            }
        )

    # ------------------------------------------------------------------ #
    # Control plane: scenario runner                                      #
    # ------------------------------------------------------------------ #

    _SCENARIO_ACTIONS = frozenset(
        {"message", "typing", "dispatch", "chaos", "reconnect", "invalidate", "wait"}
    )

    async def _start_scenario(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        steps = payload.get("steps")
        if not isinstance(steps, list) or not steps:
            return _discord_error(
                400,
                "Invalid Form Body",
                ERROR_INVALID_FORM_BODY,
                errors={
                    "steps": {
                        "_errors": [
                            {"code": "REQUIRED", "message": "steps must be a non-empty list"}
                        ]
                    }
                },
            )
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or step.get("action") not in self._SCENARIO_ACTIONS:
                return _discord_error(
                    400,
                    "Invalid Form Body",
                    ERROR_INVALID_FORM_BODY,
                    errors={
                        f"steps.{index}.action": {
                            "_errors": [
                                {
                                    "code": "ENUM_TYPE_COERCE",
                                    "message": "Unknown scenario action",
                                }
                            ]
                        }
                    },
                )
        scenario_id = uuid.uuid4().hex[:8]
        record = {
            "id": scenario_id,
            "name": str(payload.get("name") or f"scenario-{scenario_id}"),
            "status": "running",
            "steps_total": len(steps),
            "steps_done": 0,
            "started_at": _utc_now_iso(),
        }
        self._scenarios[scenario_id] = record
        task = asyncio.create_task(self._run_scenario(scenario_id, steps))
        self._scenario_tasks[scenario_id] = task
        return web.json_response(record, status=202)

    async def _run_scenario(self, scenario_id: str, steps: list[dict[str, Any]]) -> None:
        record = self._scenarios[scenario_id]
        loop = asyncio.get_running_loop()
        started = loop.time()
        ordered = sorted(steps, key=lambda step: float(step.get("at", 0.0)))
        try:
            for index, step in enumerate(ordered):
                delay = started + float(step.get("at", 0.0)) - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                await self._execute_scenario_step(step)
                record["steps_done"] = index + 1
            record["status"] = "completed"
            record["finished_at"] = _utc_now_iso()
        except asyncio.CancelledError:
            record["status"] = "cancelled"
            record["finished_at"] = _utc_now_iso()
            raise
        except Exception as exc:
            record["status"] = "error"
            record["error"] = str(exc)
            record["finished_at"] = _utc_now_iso()
            logger.exception({"event": "mock.scenario.error", "scenario_id": scenario_id})
        finally:
            self._scenario_tasks.pop(scenario_id, None)
            self._notify_sse({"kind": "scenario", "at": _utc_now_iso(), **record})

    async def _execute_scenario_step(self, step: dict[str, Any]) -> None:
        action = step.get("action")
        data = step.get("data") or {}
        if action == "message":
            await self._inject_message(data)
        elif action == "typing":
            await self._inject_typing(
                channel_id=str(data.get("channel_id", "123")),
                user_id=str(data.get("user_id", self._current_user["id"])),
            )
        elif action == "dispatch":
            await self._dispatch(str(data.get("t", "MOCK_EVENT")), data.get("d") or {})
        elif action == "chaos":
            self._apply_chaos_settings(data)
        elif action == "reconnect":
            await self.hub.request_reconnect(data.get("session_id"))
        elif action == "invalidate":
            await self.hub.invalidate_session(
                data.get("session_id"), resumable=bool(data.get("resumable", False))
            )
        elif action == "wait":
            pass  # timing handled by the "at" offset

    async def _list_scenarios(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(list(self._scenarios.values()))

    async def _cancel_scenario(self, request: web.Request) -> web.Response:
        self._record_request(request)
        scenario_id = request.match_info["scenario_id"]
        record = self._scenarios.get(scenario_id)
        if record is None:
            raise web.HTTPNotFound(text='{"message":"Unknown Scenario","code":0}')
        task = self._scenario_tasks.get(scenario_id)
        if task is not None:
            task.cancel()
        else:
            record.setdefault("finished_at", _utc_now_iso())
        return web.json_response(record)

    # ------------------------------------------------------------------ #
    # Control plane: gateway                                              #
    # ------------------------------------------------------------------ #

    async def _gateway_state(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(
            {
                "ws_url": self.ws_url,
                "sessions": self.hub.sessions_info(),
                "events_dispatched": self.hub.events_dispatched,
                "connections_seen": self.hub.connections_seen,
                "recent_events": list(self.gateway_events)[-50:],
            }
        )

    @staticmethod
    async def _read_json_optional(request: web.Request) -> dict[str, Any]:
        try:
            payload = await request.json()
        except (ValueError, UnicodeDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    async def _gateway_reconnect(self, request: web.Request) -> web.Response:
        payload = await self._read_json_optional(request)
        self._record_request(request, payload=payload)
        sent = await self.hub.request_reconnect(payload.get("session_id"))
        return web.json_response({"sent": sent})

    async def _gateway_invalidate(self, request: web.Request) -> web.Response:
        payload = await self._read_json_optional(request)
        self._record_request(request, payload=payload)
        sent = await self.hub.invalidate_session(
            payload.get("session_id"),
            resumable=bool(payload.get("resumable", False)),
        )
        return web.json_response({"sent": sent})

    # ------------------------------------------------------------------ #
    # Discord REST handlers                                               #
    # ------------------------------------------------------------------ #

    async def _gateway_plain(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response({"url": self.ws_url})

    async def _gateway_bot(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(
            {
                "url": self.ws_url,
                "shards": 1,
                "session_start_limit": {
                    "total": 1000,
                    "remaining": 999,
                    "reset_after": 14_400_000,
                    "max_concurrency": 1,
                },
            }
        )

    async def _get_current_user(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(self._current_user)

    async def _get_user(self, request: web.Request) -> web.Response:
        self._record_request(request)
        user_id = request.match_info["user_id"]
        user = self.users.get(user_id)
        if user is None:
            raise web.HTTPNotFound(text='{"message":"Unknown User","code":10013}')
        return web.json_response(user)

    async def _list_current_user_guilds(self, request: web.Request) -> web.Response:
        self._record_request(request)
        return web.json_response(list(self.guilds.values()))

    async def _get_guild(self, request: web.Request) -> web.Response:
        self._record_request(request)
        guild_id = request.match_info["guild_id"]
        guild = self.guilds.get(guild_id)
        if guild is None:
            raise web.HTTPNotFound(text='{"message":"Unknown Guild","code":10004}')
        return web.json_response(guild)

    async def _list_guild_channels(self, request: web.Request) -> web.Response:
        self._record_request(request)
        guild_id = request.match_info["guild_id"]
        guild = self.guilds.get(guild_id)
        if guild is None:
            raise web.HTTPNotFound(text='{"message":"Unknown Guild","code":10004}')
        channels = [
            channel for channel in self.channels.values() if channel.get("guild_id") == guild_id
        ]
        return web.json_response(channels)

    async def _get_channel(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        channel = self.channels.get(channel_id)
        if channel is None:
            raise web.HTTPNotFound(text='{"message":"Unknown Channel","code":10003}')
        return web.json_response(channel)

    async def _edit_channel(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        channel_id = request.match_info["channel_id"]
        channel = self.channels.get(channel_id)
        if channel is None:
            raise web.HTTPNotFound(text='{"message":"Unknown Channel","code":10003}')
        for key in ("name", "topic", "position", "nsfw"):
            if key in payload:
                channel[key] = payload[key]
        await self._dispatch("CHANNEL_UPDATE", dict(channel))
        return web.json_response(channel)

    async def _delete_channel(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        channel = self.channels.pop(channel_id, None)
        if channel is None:
            raise web.HTTPNotFound(text='{"message":"Unknown Channel","code":10003}')
        removed_ids = {
            message["id"] for message in self.messages if message["channel_id"] == channel_id
        }
        self.messages = [
            message for message in self.messages if message["channel_id"] != channel_id
        ]
        self.typing_events = [
            event for event in self.typing_events if event["channel_id"] != channel_id
        ]
        for message_id in removed_ids:
            self._messages_by_id.pop(message_id, None)
        await self._dispatch("CHANNEL_DELETE", dict(channel))
        return web.json_response(channel)

    async def _list_messages(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        limit = int(request.query.get("limit", "50"))
        messages = [msg for msg in self.messages if msg["channel_id"] == channel_id]
        before = request.query.get("before")
        after = request.query.get("after")
        around = request.query.get("around")
        if before is not None:
            messages = [msg for msg in messages if int(msg["id"]) < int(before)]
        if after is not None:
            messages = [msg for msg in messages if int(msg["id"]) > int(after)]
        if around is not None:
            center_index = next(
                (index for index, msg in enumerate(messages) if msg["id"] == around),
                None,
            )
            if center_index is None:
                messages = []
            else:
                radius = max(1, limit // 2)
                start = max(0, center_index - radius)
                stop = center_index + radius + 1
                messages = messages[start:stop]
        return web.json_response(list(reversed(messages[-limit:])))

    async def _get_message(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        message_id = request.match_info["message_id"]
        message = self._messages_by_id.get(message_id)
        if message is None or message["channel_id"] != channel_id:
            raise web.HTTPNotFound(text='{"message":"Unknown Message","code":10008}')
        return web.json_response(message)

    async def _send_message(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        validation_error = self._validate_message_payload(payload)
        if validation_error is not None:
            return validation_error
        channel_id = request.match_info["channel_id"]
        channel = self.channels.get(channel_id)
        if channel is None:
            channel = self._ensure_channel(channel_id)
        message = self._build_message(
            channel_id=channel_id,
            content=str(payload.get("content", "")),
            tts=bool(payload.get("tts", False)),
            author=self._current_user,
            guild_id=channel.get("guild_id"),
        )
        for key in ("embeds", "components", "flags", "message_reference", "poll"):
            if key in payload:
                message[key] = payload[key]
        self.messages.append(message)
        self._messages_by_id[message["id"]] = message
        await self._dispatch("MESSAGE_CREATE", message)
        return web.json_response(message)

    async def _edit_message(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        channel_id = request.match_info["channel_id"]
        message_id = request.match_info["message_id"]
        message = self._messages_by_id.get(message_id)
        if message is None or message["channel_id"] != channel_id:
            raise web.HTTPNotFound(text='{"message":"Unknown Message","code":10008}')
        for key in ("content", "embeds", "components", "flags"):
            if key in payload:
                message[key] = payload[key]
        message["edited_timestamp"] = _utc_now_iso()
        await self._dispatch("MESSAGE_UPDATE", dict(message))
        return web.json_response(message)

    async def _delete_message(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        message_id = request.match_info["message_id"]
        message = self._messages_by_id.get(message_id)
        if message is None or message["channel_id"] != channel_id:
            raise web.HTTPNotFound(text='{"message":"Unknown Message","code":10008}')
        self.messages = [item for item in self.messages if item["id"] != message_id]
        self._messages_by_id.pop(message_id, None)
        await self._dispatch(
            "MESSAGE_DELETE",
            {
                "id": message_id,
                "channel_id": channel_id,
                **({"guild_id": message["guild_id"]} if "guild_id" in message else {}),
            },
        )
        return web.Response(status=204)

    async def _inject_typing(self, *, channel_id: str, user_id: str) -> dict[str, Any]:
        if channel_id not in self.channels:
            self._ensure_channel(channel_id)
        user = self.users.get(user_id) or self._current_user
        event = {
            "channel_id": channel_id,
            "user_id": user["id"],
            "username": user["username"],
            "timestamp": _utc_now_iso(),
        }
        self.typing_events.append(event)
        await self._dispatch(
            "TYPING_START",
            {
                "channel_id": channel_id,
                "user_id": user["id"],
                "timestamp": int(time.time()),
            },
        )
        return event

    async def _trigger_typing(self, request: web.Request) -> web.Response:
        self._record_request(request)
        channel_id = request.match_info["channel_id"]
        await self._inject_typing(channel_id=channel_id, user_id=self._current_user["id"])
        return web.Response(status=204)

    async def _create_dm(self, request: web.Request) -> web.Response:
        payload, error = await self._read_json(request)
        if error is not None:
            return error
        self._record_request(request, payload=payload)
        recipient_id = str(payload.get("recipient_id", "0"))
        recipient = self._ensure_user(recipient_id)
        try:
            channel_id = str(int(recipient_id) + 1000)
        except ValueError:
            channel_id = f"dm-{recipient_id}"
        channel = self._ensure_channel(
            channel_id,
            channel_type=1,
            name=f"dm-{recipient['username']}",
        )
        channel["recipients"] = [recipient]
        return web.json_response({"id": channel_id, "type": 1, "recipients": [recipient]})

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self._sync_bound_port()
        logger.info(
            {
                "event": "mock.server.started",
                "host": self.host,
                "port": self.port,
                "base_url": self.base_url,
                "local_url": self.local_url,
                "ws_url": self.ws_url,
                "ui_enabled": self.enable_ui,
            }
        )

    async def stop(self) -> None:
        for task in list(self._scenario_tasks.values()):
            task.cancel()
        self._scenario_tasks.clear()
        for queue in list(self._sse_queues):
            if queue.full():  # make room so the sentinel always lands
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait({"kind": "__shutdown__"})
        await self.hub.close_all()
        if self._runner is not None:
            await self._runner.cleanup()
            logger.info(
                {
                    "event": "mock.server.stopped",
                    "host": self.host,
                    "port": self.port,
                }
            )

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/api"

    @property
    def local_url(self) -> str:
        """Return the browser URL for the optional local test UI."""
        return f"http://{self.host}:{self.port}/"

    def _sync_bound_port(self) -> None:
        server = getattr(self._site, "_server", None)
        sockets = getattr(server, "sockets", None)
        if sockets:
            self.port = int(sockets[0].getsockname()[1])
