"""DAVE Voice Gateway opcodes.

Discord defines an extra range of voice gateway opcodes (21-31) for the DAVE
protocol negotiation. They are documented at
https://github.com/discord/dave-protocol/blob/main/protocol.md and in the
Discord developer docs (Voice Connections > DAVE).
"""

from __future__ import annotations

from enum import IntEnum


class DaveOpcode(IntEnum):
    """Voice gateway opcodes that participate in DAVE negotiation."""

    PREPARE_TRANSITION = 21
    """Server: a downgrade or upgrade is about to happen, prepare local state."""

    EXECUTE_TRANSITION = 22
    """Server: commit the prepared transition; activate the new protocol/epoch."""

    TRANSITION_READY = 23
    """Client: acknowledge that local preparation has completed."""

    PREPARE_EPOCH = 24
    """Server: a new MLS epoch is starting; produce a key package if needed."""

    MLS_EXTERNAL_SENDER = 25
    """Server: external sender credential for the MLS group."""

    MLS_KEY_PACKAGE = 26
    """Client: MLS key package generated locally and uploaded to the group."""

    MLS_PROPOSALS = 27
    """Server: list of MLS proposals to apply or revoke."""

    MLS_COMMIT_WELCOME = 28
    """Client: MLS commit produced locally with embedded welcome messages."""

    MLS_ANNOUNCE_COMMIT_TRANSITION = 29
    """Server: commit announcement that initiates a transition."""

    MLS_WELCOME = 30
    """Server: MLS welcome to a new member."""

    MLS_INVALID_COMMIT_WELCOME = 31
    """Client: notify the server that a commit/welcome could not be applied."""


# Subsets useful for downstream consumers (e.g. tests, documentation generators).
SERVER_TO_CLIENT: frozenset[DaveOpcode] = frozenset({
    DaveOpcode.PREPARE_TRANSITION,
    DaveOpcode.EXECUTE_TRANSITION,
    DaveOpcode.PREPARE_EPOCH,
    DaveOpcode.MLS_EXTERNAL_SENDER,
    DaveOpcode.MLS_PROPOSALS,
    DaveOpcode.MLS_ANNOUNCE_COMMIT_TRANSITION,
    DaveOpcode.MLS_WELCOME,
})


CLIENT_TO_SERVER: frozenset[DaveOpcode] = frozenset({
    DaveOpcode.TRANSITION_READY,
    DaveOpcode.MLS_KEY_PACKAGE,
    DaveOpcode.MLS_COMMIT_WELCOME,
    DaveOpcode.MLS_INVALID_COMMIT_WELCOME,
})


__all__ = ["DaveOpcode", "SERVER_TO_CLIENT", "CLIENT_TO_SERVER"]
