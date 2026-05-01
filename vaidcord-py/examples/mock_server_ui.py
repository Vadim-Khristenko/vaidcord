"""Run the local mock Discord server with the browser UI enabled."""

from __future__ import annotations

import asyncio
import os

from vaidcord.mock import MockDiscordServer


async def main() -> None:
    port = int(os.environ.get("VAIDCORD_MOCK_PORT", "18080"))
    server = MockDiscordServer(port=port, enable_ui=True)
    await server.start()
    try:
        print(f"Mock REST base: {server.base_url}")
        print(f"Mock UI: {server.local_url}")
        await asyncio.Event().wait()
    finally:
        await server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
