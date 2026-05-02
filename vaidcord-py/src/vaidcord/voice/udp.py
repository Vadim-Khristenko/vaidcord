from __future__ import annotations

import asyncio
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceDatagram:
    data: bytes
    address: tuple[str, int]


def build_ip_discovery_packet(ssrc: int) -> bytes:
    packet = bytearray(74)
    struct.pack_into(">HHI", packet, 0, 1, 70, ssrc)
    return bytes(packet)


def parse_ip_discovery_response(packet: bytes) -> tuple[str, int]:
    if len(packet) < 74:
        raise ValueError("Voice IP discovery response must be at least 74 bytes")
    response_type, length, _ = struct.unpack_from(">HHI", packet, 0)
    if response_type != 2 or length != 70:
        raise ValueError("Invalid voice IP discovery response header")
    raw_address = packet[8:72].split(b"\x00", 1)[0]
    address = raw_address.decode("ascii")
    port = struct.unpack_from(">H", packet, 72)[0]
    return address, port


class _VoiceDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.ready = asyncio.Event()
        self.closed = asyncio.Event()
        self.queue: asyncio.Queue[VoiceDatagram] = asyncio.Queue()
        self.error: Exception | None = None
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        self.ready.set()

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.queue.put_nowait(VoiceDatagram(data=data, address=addr))

    def error_received(self, exc: Exception) -> None:
        self.error = exc
        self.closed.set()

    def connection_lost(self, exc: Exception | None) -> None:
        self.error = exc
        self.closed.set()


class VoiceUDPClient:
    def __init__(self, ip: str, port: int) -> None:
        self.ip = ip
        self.port = port
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _VoiceDatagramProtocol | None = None

    @property
    def is_connected(self) -> bool:
        return self._transport is not None and not self._transport.is_closing()

    async def connect(self) -> None:
        if self.is_connected:
            return
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            _VoiceDatagramProtocol,
            remote_addr=(self.ip, self.port),
        )
        self._transport = transport  # type: ignore[assignment]
        self._protocol = protocol  # type: ignore[assignment]
        await self._protocol.ready.wait()

    async def send(self, data: bytes) -> None:
        await self.connect()
        if self._transport is None:
            raise RuntimeError("Voice UDP transport is not connected")
        self._transport.sendto(data)

    async def receive(self, *, wait_timeout: float | None = None) -> VoiceDatagram:
        await self.connect()
        if self._protocol is None:
            raise RuntimeError("Voice UDP transport is not connected")
        if self._protocol.error is not None:
            raise self._protocol.error
        if wait_timeout is None:
            return await self._protocol.queue.get()
        return await asyncio.wait_for(self._protocol.queue.get(), timeout=wait_timeout)

    async def packets(self) -> AsyncIterator[VoiceDatagram]:
        while self.is_connected:
            yield await self.receive()

    async def discover_ip(self, ssrc: int, *, wait_timeout: float = 5.0) -> tuple[str, int]:
        await self.send(build_ip_discovery_packet(ssrc))
        packet = await self.receive(wait_timeout=wait_timeout)
        return parse_ip_discovery_response(packet.data)

    async def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self._protocol = None
