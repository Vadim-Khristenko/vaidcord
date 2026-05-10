"""High-level controller that drives the DAVE state machine.

The controller knows how to:

* answer ``IDENTIFY`` (op 0) with the negotiated max protocol version,
* read ``SESSION_DESCRIPTION`` (op 4) to learn the version Discord picked,
* dispatch each gateway opcode in the DAVE range (21-31) to the right
  backend method,
* emit response payloads (``TRANSITION_READY``, ``MLS_KEY_PACKAGE``,
  ``MLS_COMMIT_WELCOME``, ``MLS_INVALID_COMMIT_WELCOME``) through a
  caller-supplied ``send_payload`` callback.

It deliberately does NOT touch sockets or the voice UDP transport — the
voice connection wires it up through callbacks. That keeps the controller
testable and makes it straightforward to embed in a different host.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .backend import DaveCryptoBackend, UnsupportedDaveBackend
from .errors import DaveBackendError, DavePayloadError, DaveUnsupportedError
from .models import DaveOutboundPayload, DaveTransition
from .opcodes import DaveOpcode
from .state import DaveProtocolState


class DaveProtocolController:
    """Discord Voice DAVE controller.

    Parameters
    ----------
    backend
        A :class:`DaveCryptoBackend` implementation. Defaults to
        :class:`UnsupportedDaveBackend` which raises
        :class:`DaveUnsupportedError` whenever DAVE is requested.
    fail_fast
        If ``True`` the controller raises :class:`DaveUnsupportedError` as
        soon as the gateway sends a payload that requires a real backend.
        Set to ``False`` to keep the connection open and surface the error
        through state instead — useful for read-only diagnostics.
    send_payload
        Callback invoked when the controller wants to send a payload to the
        voice gateway (e.g. ``TRANSITION_READY``).
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

    # ------------------------------------------------------------------ #
    # Public protocol entry points                                       #
    # ------------------------------------------------------------------ #

    @property
    def max_protocol_version(self) -> int:
        return self.backend.max_protocol_version

    def identify_fields(self) -> dict[str, Any]:
        """Fields that should be merged into Voice Opcode 0 Identify."""
        return {
            "max_dave_protocol_version": self.max_protocol_version,
        }

    def handle_session_description(self, data: Mapping[str, Any]) -> None:
        """Read DAVE version selected by the voice gateway from session description."""
        payload = _payload_dict(data)
        self.state.protocol_version = _optional_int(payload.get("dave_protocol_version"))
        self.state.negotiated = self.state.protocol_version not in (None, 0)
        self.state.enabled = self.state.negotiated

        if (
            self.fail_fast
            and self.state.requires_backend
            and self.max_protocol_version <= 0
        ):
            raise self._unsupported_error("session_description")

    def handle_gateway_payload(self, op: int, data: Mapping[str, Any] | None) -> bool:
        """Try to handle ``op`` as a DAVE opcode.

        Returns ``True`` if the opcode was a DAVE opcode (whether or not
        the backend handled it cleanly), ``False`` if ``op`` is not in the
        DAVE range and should be processed elsewhere.
        """
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
        except Exception as exc:  # noqa: BLE001 - explicitly re-wrap
            raise DaveBackendError(
                f"DAVE backend failed while handling {opcode.name}"
            ) from exc

        return True

    def encrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        if not self.state.enabled:
            return frame
        return self.backend.encrypt_frame(ssrc=ssrc, frame=frame)

    def decrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        if not self.state.enabled:
            return frame
        return self.backend.decrypt_frame(ssrc=ssrc, frame=frame)

    # ------------------------------------------------------------------ #
    # Opcode dispatch                                                    #
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

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
            "compatible MLS/DAVE backend before sending or receiving encrypted "
            "media. (Voice gateway close code 4017.)"
        )

    @staticmethod
    def _coerce_opcode(op: int) -> DaveOpcode | None:
        try:
            return DaveOpcode(op)
        except ValueError:
            return None


# ---------------------------------------------------------------------- #
# Module-level helpers                                                   #
# ---------------------------------------------------------------------- #

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
        raise DavePayloadError(
            f"DAVE payload must be a mapping, got {type(data).__name__}"
        )
    return dict(data)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DavePayloadError(
            f"Expected integer-compatible value, got {value!r}"
        ) from exc


__all__ = ["DaveProtocolController"]
