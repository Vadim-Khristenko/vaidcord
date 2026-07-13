# Mock Discord Server

`vaidcord.mock.MockDiscordServer` is a self-hosted, network-free Discord
simulator with a browser ops console. Use it to develop and test bots
end-to-end — REST **and** gateway — without touching Discord.

```bash
uv run python examples/mock_server_ui.py
# open http://127.0.0.1:18080
```

## What it simulates

| Layer | Details |
|---|---|
| REST API | `/api/v10/...` routes for users, guilds, channels, messages (with paging), typing, DMs — with Discord-shaped error bodies and proper snowflakes (timestamp-encoded). |
| **Gateway (WebSocket)** | A real `/gateway` endpoint speaking the actual protocol: op 10 HELLO → op 2 IDENTIFY → READY, op 1 heartbeat → op 11 ACK, op 6 RESUME with buffered-event replay, op 7 reconnect and op 9 invalid-session test hooks. `GET /api/v10/gateway/bot` returns the mock's own ws URL, so a real `Bot` connects end-to-end. Messages created via REST or the control plane are broadcast as `MESSAGE_CREATE` with correct sequence numbers. |
| Rate limits | Opt-in per-route buckets + global limit with `X-RateLimit-*` headers and Discord-shaped `429` bodies (`retry_after`). |
| Chaos | Latency/jitter injection and probabilistic error injection for resilience testing. |
| Scenarios | A timed script runner that injects messages/typing/events on a schedule. |

## Control plane (`/api/mock/*`)

| Endpoint | Purpose |
|---|---|
| `GET /api/mock/state` | Full simulator state (stats, guilds, channels, messages, requests). |
| `POST /api/mock/messages` | Inject an inbound message (as any user). |
| `POST /api/mock/profiles`, `PATCH /api/mock/profiles/{id}` | Create/update user profiles. |
| `PATCH /api/mock/current-user` | Switch the acting bot identity. |
| `POST /api/mock/reset` | Reset all state. |
| `GET /api/mock/events` | Live server-sent event feed (drives the UI). |
| `GET/POST/PATCH /api/mock/chaos` | Latency/error injection settings. |
| `GET/POST/PATCH /api/mock/ratelimit` | Rate-limit simulation settings. |
| `GET/POST /api/mock/permissions` | Simple permission-denial toggles. |
| `GET /api/mock/state/export`, `POST /api/mock/state/import` | Snapshot/restore the whole simulation as JSON. |
| `GET/POST /api/mock/scenario`, `DELETE /api/mock/scenario/{id}` | Run/cancel timed scenario scripts. |
| `GET /api/mock/gateway` | Connected gateway sessions + dispatch stats. |
| `POST /api/mock/gateway/reconnect` / `.../invalidate` | Force op 7 / op 9 onto connected clients to exercise reconnect logic. |

## Ops console UI

A single self-contained page (no external assets): header with live stat
tiles (requests / messages / gateway sessions / dispatches) and
export/import/reset controls; guild & channel sidebar; message timeline
with a composer that can inject as a user or send as the bot; and a tabbed
right panel — request **Inspector** (method/status color coding), **Gateway**
(live sessions + dispatched events), **Chaos**, **Limits**, and **Scenario**
runner.

## In-process test doubles

Unrelated to the network server, `vaidcord.mock` also ships
`MockHTTPClient`, `MockGateway`, `MockBot`, and payload builders for fast
unit tests — see `tests/test_mock.py` for usage patterns.
