"""Pluggable interface for MLS providers used by the DAVE backend.

Implementations of :class:`MLSProvider` are responsible for:

1. Generating a long-lived identity (used to build :class:`KeyPackage` instances).
2. Producing a key package each time the gateway asks for one.
3. Applying welcomes/commits that arrive over the gateway.
4. Producing the per-epoch secret that drives the frame-key ratchet.

The interface is small on purpose. Anything more sophisticated (proposal
batching, deferred ratchet trees, post-quantum suites, etc.) is the
provider's concern and stays hidden from the rest of the DAVE stack.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import Commit, KeyPackage, Welcome


@runtime_checkable
class MLSProvider(Protocol):
    """The minimum surface a DAVE-capable MLS provider must implement."""

    @property
    def member_id(self) -> str:
        """Stable identifier for the local participant."""

    @property
    def current_epoch(self) -> int | None:
        """Current epoch index, or ``None`` if the group hasn't been joined yet."""

    @property
    def current_epoch_secret(self) -> bytes | None:
        """Active epoch secret used to seed sender ratchets."""

    def generate_key_package(self) -> KeyPackage:
        """Produce a fresh :class:`KeyPackage` for the local participant."""

    def apply_welcome(self, welcome: Welcome) -> None:
        """Apply an MLS welcome and adopt the new epoch as current."""

    def apply_commit(self, commit: Commit) -> None:
        """Apply an MLS commit and advance to the new epoch."""

    def propose_add(self, key_package: KeyPackage) -> Commit:
        """Build a commit that admits ``key_package`` to the group."""


__all__ = ["MLSProvider"]
