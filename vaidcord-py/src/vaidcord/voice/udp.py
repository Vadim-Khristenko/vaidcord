from __future__ import annotations

import asyncio
import socket
import struct


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


class VoiceUDPClient:
    def __init__(self, ip: str, port: int) -> None:
        self.ip = ip
        self.port = port
        self._socket: socket.socket | None = None

    async def connect(self) -> None:
        if self._socket is not None:
            return
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setblocking(False)
        self._socket = udp_socket

    async def discover_ip(self, ssrc: int, *, wait_timeout: float = 5.0) -> tuple[str, int]:
        await self.connect()
        if self._socket is None:
            raise RuntimeError("Voice UDP socket is not connected")
        loop = asyncio.get_running_loop()
        await loop.sock_sendto(self._socket, build_ip_discovery_packet(ssrc), (self.ip, self.port))
        packet = await asyncio.wait_for(loop.sock_recv(self._socket, 74), timeout=wait_timeout)
        return parse_ip_discovery_response(packet)

    async def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None
