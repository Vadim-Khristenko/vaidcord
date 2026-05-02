from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Protocol


class DaveUnsupportedError(RuntimeError):
    """Raised when Discord voice requires DAVE/MLS crypto support."""


class DavePayloadError(ValueError):
    """Raised when a DAVE gateway payload has an invalid shape."""


class DaveBackendError(RuntimeError):
    """Raised when the configured DAVE backend fails."""


class DaveOpcode(IntEnum):
    PREPARE_TRANSITION = 21
    EXECUTE_TRANSITION = 22
    TRANSITION_READY = 23
    PREPARE_EPOCH = 24
    MLS_EXTERNAL_SENDER = 25
    MLS_KEY_PACKAGE = 26
    MLS_PROPOSALS = 27
    MLS_COMMIT_WELCOME = 28
    MLS_ANNOUNCE_COMMIT_TRANSITION = 29
    MLS_WELCOME = 30
    MLS_INVALID_COMMIT_WELCOME = 31


@dataclass(slots=True, frozen=True)
class DaveOutboundPayload:
    """A voice gateway payload that should be sent back to Discord."""

    op: int
    data: dict[str, Any] | bytes
    binary: bool = False


@dataclass(slots=True, frozen=True)
class DaveTransition:
    transition_id: int | str | None
    protocol_version: int | None = None
    epoch: int | None = None


@dataclass(slots=True, frozen=True)
class DaveKeyPackage:
    """MLS key package payload produced by a DAVE backend."""

    payload: dict[str, Any]
    binary: bool = False


@dataclass(slots=True, frozen=True)
class DaveCommit:
    """MLS commit/welcome payload produced by a DAVE backend."""

    payload: dict[str, Any]
    binary: bool = False


@dataclass(slots=True)
class DaveProtocolState:
    """Diagnostic and negotiation state for Discord DAVE voice sessions."""

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
        return self.protocol_version not in (None, 0) or self.pending_epoch is not None

    def snapshot(self) -> dict[str, Any]:
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


class DaveCryptoBackend(Protocol):
    """Backend interface for real DAVE/MLS support.

    Implementations may wrap Discord libdave, a native MLS implementation,
    or another compatible backend.
    """

    @property
    def max_protocol_version(self) -> int:
        """Highest DAVE protocol version supported by this backend."""

    def prepare_transition(self, transition: DaveTransition) -> None:
        """Prepare local state for a protocol transition."""

    def execute_transition(self, transition: DaveTransition) -> None:
        """Commit the prepared transition locally."""

    def prepare_epoch(self, transition: DaveTransition) -> DaveKeyPackage | None:
        """Prepare MLS epoch and optionally produce a key package."""

    def set_external_sender(self, payload: Mapping[str, Any]) -> None:
        """Store MLS external sender data from the voice gateway."""

    def handle_proposals(self, payload: Mapping[str, Any]) -> DaveCommit | None:
        """Handle MLS proposals and optionally produce a commit/welcome."""

    def handle_commit_welcome(self, payload: Mapping[str, Any]) -> None:
        """Handle MLS commit welcome from the voice gateway."""

    def handle_welcome(self, payload: Mapping[str, Any]) -> None:
        """Handle MLS welcome from the voice gateway."""

    def handle_invalid_commit_welcome(self, payload: Mapping[str, Any]) -> None:
        """Handle invalid commit/welcome notification."""

    def encrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        """Encrypt an encoded audio/video frame."""

    def decrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        """Decrypt an encoded audio/video frame."""


class UnsupportedDaveBackend:
    """Default backend used when VaidCord has no DAVE crypto implementation."""

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


class DaveProtocolController:
    """Discord Voice DAVE controller.

    This class handles DAVE Voice Gateway negotiation and delegates real
    cryptographic work to DaveCryptoBackend.
    """

    def __init__(
        self,
        *,
        backend: DaveCryptoBackend | None = None,
        fail_fast: bool = True,
        send_payload: Callable[[DaveOutboundPayload], None] | None = None,
    ) -> None:
        self.backend: DaveCryptoBackend = backend or UnsupportedDaveBackend()
        self.state = DaveProtocolState()
        self.fail_fast = fail_fast
        self._send_payload = send_payload

    @property
    def max_protocol_version(self) -> int:
        return self.backend.max_protocol_version

    def identify_fields(self) -> dict[str, Any]:
        """Fields that should be merged into Voice Opcode 0 Identify.

        Discord documents `max_dave_protocol_version` as the way for clients
        to indicate the highest DAVE protocol version they support.
        """
        return {
            "max_dave_protocol_version": self.max_protocol_version,
        }

    def handle_session_description(self, data: Mapping[str, Any]) -> None:
        """Read DAVE version selected by the voice gateway from Session Description.

        Discord says the voice gateway sends the initial selected version as
        `dave_protocol_version` in Voice Opcode 4 Session Description.
        """
        payload = _payload_dict(data)
        self.state.protocol_version = _optional_int(payload.get("dave_protocol_version"))
        self.state.negotiated = self.state.protocol_version not in (None, 0)
        self.state.enabled = self.state.negotiated

        if self.fail_fast and self.state.requires_backend and self.max_protocol_version <= 0:
            raise self._unsupported_error("session_description")

    def handle_gateway_payload(self, op: int, data: Mapping[str, Any] | None) -> bool:
        opcode = self._coerce_opcode(op)
        if opcode is None:
            return False

        payload = _payload_dict(data)

        self.state.seen = True
        self.state.last_opcode = opcode

        try:
            self._handle_dave_opcode(opcode, payload)
        except DaveUnsupportedError:
            raise
        except Exception as exc:
            raise DaveBackendError(f"DAVE backend failed while handling {opcode.name}") from exc

        return True

    def encrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        if not self.state.enabled:
            return frame
        return self.backend.encrypt_frame(ssrc=ssrc, frame=frame)

    def decrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        if not self.state.enabled:
            return frame
        return self.backend.decrypt_frame(ssrc=ssrc, frame=frame)

    def _handle_dave_opcode(self, opcode: DaveOpcode, payload: dict[str, Any]) -> None:
        if opcode is DaveOpcode.PREPARE_TRANSITION:
            self._prepare_transition(payload)
            return

        if opcode is DaveOpcode.EXECUTE_TRANSITION:
            self._execute_transition(payload)
            return

        if opcode is DaveOpcode.TRANSITION_READY:
            return

        if opcode is DaveOpcode.PREPARE_EPOCH:
            self._prepare_epoch(payload)
            return

        if opcode is DaveOpcode.MLS_EXTERNAL_SENDER:
            self.state.external_sender = payload
            self._require_backend(opcode)
            self.backend.set_external_sender(payload)
            return

        if opcode is DaveOpcode.MLS_KEY_PACKAGE:
            self.state.key_package = payload
            return

        if opcode is DaveOpcode.MLS_PROPOSALS:
            self.state.proposals.append(payload)
            self._require_backend(opcode)
            commit = self.backend.handle_proposals(payload)
            if commit is not None:
                self._send(DaveOutboundPayload(
                    op=int(DaveOpcode.MLS_COMMIT_WELCOME),
                    data=commit.payload,
                    binary=commit.binary,
                ))
            return

        if opcode is DaveOpcode.MLS_COMMIT_WELCOME:
            self.state.commit_welcome = payload
            self._require_backend(opcode)
            self.backend.handle_commit_welcome(payload)
            return

        if opcode is DaveOpcode.MLS_ANNOUNCE_COMMIT_TRANSITION:
            self.state.announced_commit_transition = payload
            return

        if opcode is DaveOpcode.MLS_WELCOME:
            self.state.welcome = payload
            self._require_backend(opcode)
            self.backend.handle_welcome(payload)
            return

        if opcode is DaveOpcode.MLS_INVALID_COMMIT_WELCOME:
            self.state.invalid_commit_welcomes.append(payload)
            self._require_backend(opcode)
            self.backend.handle_invalid_commit_welcome(payload)
            return

    def _prepare_transition(self, payload: dict[str, Any]) -> None:
        transition = _transition_from_payload(payload)

        self.state.pending_transition = payload
        self.state.transition_id = transition.transition_id
        self.state.protocol_version = transition.protocol_version

        if transition.protocol_version in (None, 0):
            self._send_transition_ready(transition)
            return

        self._require_backend(DaveOpcode.PREPARE_TRANSITION)
        self.backend.prepare_transition(transition)
        self._send_transition_ready(transition)

    def _execute_transition(self, payload: dict[str, Any]) -> None:
        transition = _transition_from_payload(payload)

        self.state.transition_id = transition.transition_id

        if transition.protocol_version == 0:
            self.state.enabled = False
            self.state.protocol_version = 0
            return

        self._require_backend(DaveOpcode.EXECUTE_TRANSITION)
        self.backend.execute_transition(transition)

        if transition.protocol_version is not None:
            self.state.protocol_version = transition.protocol_version

        self.state.enabled = self.state.protocol_version not in (None, 0)

    def _prepare_epoch(self, payload: dict[str, Any]) -> None:
        transition = _transition_from_payload(payload)

        self.state.pending_epoch = payload
        self.state.transition_id = transition.transition_id
        self.state.protocol_version = transition.protocol_version
        self.state.epoch = transition.epoch

        self._require_backend(DaveOpcode.PREPARE_EPOCH)

        key_package = self.backend.prepare_epoch(transition)
        if key_package is not None:
            self._send(DaveOutboundPayload(
                op=int(DaveOpcode.MLS_KEY_PACKAGE),
                data=key_package.payload,
                binary=key_package.binary,
            ))

        self._send_transition_ready(transition)

    def _send_transition_ready(self, transition: DaveTransition) -> None:
        payload: dict[str, Any] = {}

        if transition.transition_id is not None:
            payload["transition_id"] = transition.transition_id

        self._send(DaveOutboundPayload(
            op=int(DaveOpcode.TRANSITION_READY),
            data=payload,
        ))

    def _send(self, payload: DaveOutboundPayload) -> None:
        if self._send_payload is not None:
            self._send_payload(payload)

    def _require_backend(self, opcode: DaveOpcode) -> None:
        if self.max_protocol_version <= 0:
            if self.fail_fast:
                raise self._unsupported_error(opcode.name)
            return

    def _unsupported_error(self, source: str) -> DaveUnsupportedError:
        return DaveUnsupportedError(
            "Discord voice requested DAVE/MLS end-to-end encryption "
            f"while handling {source}. "
            "VaidCord recognized the DAVE Voice Gateway flow, but no production "
            "DAVE crypto backend is configured. Integrate libdave or another "
            "compatible MLS/DAVE backend before sending or receiving encrypted media."
        )

    @staticmethod
    def _coerce_opcode(op: int) -> DaveOpcode | None:
        try:
            return DaveOpcode(op)
        except ValueError:
            return None


def _transition_from_payload(payload: Mapping[str, Any]) -> DaveTransition:
    return DaveTransition(
        transition_id=payload.get("transition_id"),
        protocol_version=_optional_int(
            payload.get("protocol_version", payload.get("dave_protocol_version"))
        ),
        epoch=_optional_int(payload.get("epoch")),
    )


def _payload_dict(data: Mapping[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {}

    if not isinstance(data, Mapping):
        raise DavePayloadError(f"DAVE payload must be a mapping, got {type(data).__name__}")

    return dict(data)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DavePayloadError(f"Expected integer-compatible value, got {value!r}") from exc
