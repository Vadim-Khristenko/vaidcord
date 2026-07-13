"""RTP/RTCP packet parsing for the Discord voice UDP transport."""

from __future__ import annotations

import struct
from dataclasses import dataclass

__all__ = [
    "RTP_HEADER_SIZE",
    "RTPPacket",
    "is_rtcp_packet",
    "parse_rtp_packet",
    "strip_header_extension",
]

RTP_HEADER_SIZE = 12

# RTCP packet types occupy the full second byte (SR=200 … APP=204).
_RTCP_TYPES = frozenset(range(200, 205))


@dataclass(frozen=True, slots=True)
class RTPPacket:
    """A parsed (still encrypted) RTP packet.

    ``header`` is the unencrypted prefix as defined by the ``_rtpsize``
    encryption modes: the fixed 12-byte header, any CSRC entries, and — when
    the extension bit is set — the 4-byte extension profile/length preamble.
    ``payload`` is everything after that prefix (ciphertext + nonce suffix
    for encrypted transports).
    """

    version: int
    padding: bool
    extension: bool
    marker: bool
    payload_type: int
    sequence: int
    timestamp: int
    ssrc: int
    csrcs: tuple[int, ...]
    header: bytes
    payload: bytes


def is_rtcp_packet(data: bytes) -> bool:
    return len(data) >= 2 and data[1] in _RTCP_TYPES


def parse_rtp_packet(data: bytes) -> RTPPacket:
    if len(data) < RTP_HEADER_SIZE:
        raise ValueError(f"RTP packet too short: {len(data)} bytes")
    first, second, sequence, timestamp, ssrc = struct.unpack_from(">BBHII", data, 0)
    version = first >> 6
    padding = bool(first & 0x20)
    extension = bool(first & 0x10)
    csrc_count = first & 0x0F
    marker = bool(second & 0x80)
    payload_type = second & 0x7F

    offset = RTP_HEADER_SIZE
    if len(data) < offset + csrc_count * 4:
        raise ValueError("RTP packet truncated inside CSRC list")
    csrcs = struct.unpack_from(f">{csrc_count}I", data, offset) if csrc_count else ()
    offset += csrc_count * 4
    if extension:
        if len(data) < offset + 4:
            raise ValueError("RTP packet truncated inside extension preamble")
        offset += 4

    return RTPPacket(
        version=version,
        padding=padding,
        extension=extension,
        marker=marker,
        payload_type=payload_type,
        sequence=sequence,
        timestamp=timestamp,
        ssrc=ssrc,
        csrcs=tuple(csrcs),
        header=data[:offset],
        payload=data[offset:],
    )


def strip_header_extension(packet: RTPPacket, plaintext: bytes) -> bytes:
    """Drop the decrypted header-extension words from ``plaintext``.

    In the ``_rtpsize`` modes the 4-byte extension preamble stays in the
    clear (as part of :attr:`RTPPacket.header`) while the extension words
    themselves are encrypted at the start of the payload.
    """
    if not packet.extension:
        return plaintext
    ext_words = struct.unpack_from(">H", packet.header, len(packet.header) - 2)[0]
    return plaintext[ext_words * 4 :]
