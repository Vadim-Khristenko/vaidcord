"""Backend interface for DAVE crypto and a no-op default implementation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from .errors import DaveUnsupportedError
from .models import DaveCommit, DaveKeyPackage, DaveTransition


@runtime_checkable
class DaveCryptoBackend(Protocol):
    """Backend interface for real DAVE/MLS support.

    The interface is intentionally narrow so that completely different
    backends — the in-process reference implementation, a pure-Python MLS
    library, or a native ``libdave`` binding — can be plugged in without the
    controller having to learn about each one.

    Backends MUST be safe to call from a single asyncio task, but they are
    not required to be thread-safe. The voice connection guarantees that all
    DAVE callbacks are dispatched serially.
    """

    @property
    def max_protocol_version(self) -> int:
        """Highest DAVE protocol version supported by this backend."""

    def prepare_transition(self, transition: DaveTransition) -> None:
        """Prepare local state for a protocol transition.

        Called when the gateway sends ``PREPARE_TRANSITION`` (op 21). The
        backend should pre-compute any ratchets that the new protocol version
        requires but must NOT activate them yet.
        """

    def execute_transition(self, transition: DaveTransition) -> None:
        """Activate the transition prepared previously."""

    def prepare_epoch(self, transition: DaveTransition) -> DaveKeyPackage | None:
        """Prepare a new MLS epoch and optionally return a key package.

        Returning a :class:`DaveKeyPackage` causes the controller to forward
        it to the gateway as a ``MLS_KEY_PACKAGE`` (op 26).
        """

    def set_external_sender(self, payload: Mapping[str, Any]) -> None:
        """Store the MLS external sender credential delivered by the gateway."""

    def handle_proposals(self, payload: Mapping[str, Any]) -> DaveCommit | None:
        """Handle MLS proposals; optionally produce a commit/welcome to send."""

    def handle_commit_welcome(self, payload: Mapping[str, Any]) -> None:
        """Handle the gateway echoing our commit/welcome to the group."""

    def handle_welcome(self, payload: Mapping[str, Any]) -> None:
        """Handle an MLS welcome that adds us to a new group epoch."""

    def handle_invalid_commit_welcome(self, payload: Mapping[str, Any]) -> None:
        """Handle a notification that our commit/welcome was rejected."""

    def encrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        """Encrypt an outgoing media frame for the active epoch."""

    def decrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        """Decrypt an incoming media frame for the active epoch."""


class UnsupportedDaveBackend:
    """Default backend used when no DAVE crypto implementation is configured.

    Every method raises :class:`DaveUnsupportedError`. Configurations that
    don't need DAVE (most bots) keep this default and simply never reach the
    error paths because Discord won't ask them for E2EE.
    """

    max_protocol_version = 0

    def prepare_transition(self, transition: DaveTransition) -> None:
        self._raise()

    def execute_transition(self, transition: DaveTransition) -> None:
        self._raise()

    def prepare_epoch(self, transition: DaveTransition) -> DaveKeyPackage | None:
        self._raise()

    def set_external_sender(self, payload: Mapping[str, Any]) -> None:
        self._raise()

    def handle_proposals(self, payload: Mapping[str, Any]) -> DaveCommit | None:
        self._raise()

    def handle_commit_welcome(self, payload: Mapping[str, Any]) -> None:
        self._raise()

    def handle_welcome(self, payload: Mapping[str, Any]) -> None:
        self._raise()

    def handle_invalid_commit_welcome(self, payload: Mapping[str, Any]) -> None:
        self._raise()

    def encrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        self._raise()

    def decrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        self._raise()

    @staticmethod
    def _raise() -> None:
        raise DaveUnsupportedError(
            "Discord voice requires DAVE/MLS support, but no compatible "
            "DAVE crypto backend is configured."
        )


__all__ = ["DaveCryptoBackend", "UnsupportedDaveBackend"]
