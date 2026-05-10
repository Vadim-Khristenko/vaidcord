"""Mutable, observable state for an in-flight DAVE protocol session."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .opcodes import DaveOpcode


@dataclass(slots=True)
class DaveProtocolState:
    """Diagnostic and negotiation state for Discord DAVE voice sessions.

    Instances of this class live for the duration of a single voice
    connection. They are mutated by :class:`~vaidcord.voice.dave.controller.DaveProtocolController`
    in response to gateway opcodes and are read by the voice connection,
    metrics, and tests.
    """

    seen: bool = False
    enabled: bool = False
    negotiated: bool = False

    protocol_version: int | None = None
    epoch: int | None = None
    transition_id: int | str | None = None

    pending_transition: dict[str, Any] | None = None
    pending_epoch: dict[str, Any] | None = None
    external_sender: dict[str, Any] | None = None
    key_package: dict[str, Any] | None = None
    commit_welcome: dict[str, Any] | None = None
    welcome: dict[str, Any] | None = None
    announced_commit_transition: dict[str, Any] | None = None

    proposals: list[dict[str, Any]] = field(default_factory=list)
    invalid_commit_welcomes: list[dict[str, Any]] = field(default_factory=list)

    last_opcode: DaveOpcode | None = None

    @property
    def requires_backend(self) -> bool:
        """Whether the current state requires a real DAVE crypto backend."""
        return self.protocol_version not in (None, 0) or self.pending_epoch is not None

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot for logging or admin endpoints.

        Only stable, side-effect-free fields are included. Sensitive payloads
        such as MLS welcomes are reported as boolean presence flags.
        """
        return {
            "seen": self.seen,
            "enabled": self.enabled,
            "negotiated": self.negotiated,
            "protocol_version": self.protocol_version,
            "epoch": self.epoch,
            "transition_id": self.transition_id,
            "has_pending_transition": self.pending_transition is not None,
            "has_pending_epoch": self.pending_epoch is not None,
            "has_external_sender": self.external_sender is not None,
            "has_key_package": self.key_package is not None,
            "has_commit_welcome": self.commit_welcome is not None,
            "has_welcome": self.welcome is not None,
            "proposals_count": len(self.proposals),
            "invalid_commit_welcomes_count": len(self.invalid_commit_welcomes),
            "last_opcode": self.last_opcode.name if self.last_opcode else None,
        }


__all__ = ["DaveProtocolState"]
