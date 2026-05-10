"""Wire types shared between MLS providers.

These dataclasses are deliberately minimal: they capture just enough state
for the DAVE controller and the in-process reference provider to round-trip
through the voice gateway. A production-grade MLS provider can use these as
its public surface and store full RFC 9420 structures internally.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class KeyPackage:
    """An MLS key package describing how a member can be added to a group."""

    member_id: str
    """Stable identifier for the member (Discord user id or test handle)."""

    public_key: bytes
    """Long-term identity public key of the member."""

    signature: bytes = b""
    """Optional signature over the key package (empty for the in-process reference)."""

    def to_payload(self) -> dict[str, object]:
        return {
            "member_id": self.member_id,
            "key_package": self.public_key.hex(),
            "signature": self.signature.hex(),
        }


@dataclass(frozen=True, slots=True)
class Welcome:
    """An MLS welcome that adds the local participant to an existing group."""

    epoch: int
    """The epoch index this welcome admits the new member to."""

    group_id: str
    """Stable group identifier (Discord channel id, typically)."""

    epoch_secret: bytes
    """The per-epoch secret that bootstraps frame-key derivation."""

    members: tuple[str, ...] = ()
    """Member ids known to be in the group at the welcome's epoch."""

    def to_payload(self) -> dict[str, object]:
        return {
            "epoch": self.epoch,
            "group_id": self.group_id,
            "epoch_secret": self.epoch_secret.hex(),
            "members": list(self.members),
        }


@dataclass(frozen=True, slots=True)
class Commit:
    """An MLS commit, optionally bundled with welcomes for newly added members."""

    epoch: int
    group_id: str
    add_members: tuple[str, ...] = ()
    remove_members: tuple[str, ...] = ()
    welcomes: tuple[Welcome, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "epoch": self.epoch,
            "group_id": self.group_id,
            "add_members": list(self.add_members),
            "remove_members": list(self.remove_members),
            "welcomes": [w.to_payload() for w in self.welcomes],
        }


@dataclass(slots=True)
class GroupEpoch:
    """Active MLS epoch state used by the reference frame backend."""

    epoch: int
    group_id: str
    epoch_secret: bytes
    members: list[str] = field(default_factory=list)


__all__ = ["KeyPackage", "Welcome", "Commit", "GroupEpoch"]
