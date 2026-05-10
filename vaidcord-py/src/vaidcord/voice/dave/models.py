"""Data classes used as values shared between the protocol controller and backend.

All payloads are intentionally small, slotted, and immutable so they can move
between threads (e.g. a network reader and a media encoder) without locking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class DaveOutboundPayload:
    """A voice gateway payload that should be sent back to Discord.

    ``binary`` is honoured by the voice connection wrapper: when ``True`` the
    payload is sent as a binary websocket frame; otherwise it is sent as JSON.
    """

    op: int
    data: dict[str, Any] | bytes
    binary: bool = False


@dataclass(slots=True, frozen=True)
class DaveTransition:
    """A protocol transition advertised by the voice gateway."""

    transition_id: int | str | None
    protocol_version: int | None = None
    epoch: int | None = None


@dataclass(slots=True, frozen=True)
class DaveKeyPackage:
    """An MLS key package produced by the backend.

    For binary key packages the ``payload`` should be a ``dict`` containing
    a ``key_package`` field whose value is a ``bytes`` object; the controller
    forwards it untouched. ``binary`` controls the wire encoding.
    """

    payload: dict[str, Any]
    binary: bool = False


@dataclass(slots=True, frozen=True)
class DaveCommit:
    """An MLS commit/welcome bundle produced by the backend."""

    payload: dict[str, Any]
    binary: bool = False


@dataclass(slots=True, frozen=True)
class DaveSenderInfo:
    """Information about a sender in the active MLS group.

    ``sender_id`` is the Discord user id (or, for testing/self-loop, an
    arbitrary stable identifier). ``base_secret`` is the per-sender secret
    derived from the MLS epoch via HKDF-Expand. The base secret then drives
    a per-frame ratchet (see :mod:`vaidcord.voice.dave.crypto.ratchet`).
    """

    sender_id: str
    base_secret: bytes


__all__ = [
    "DaveOutboundPayload",
    "DaveTransition",
    "DaveKeyPackage",
    "DaveCommit",
    "DaveSenderInfo",
]
