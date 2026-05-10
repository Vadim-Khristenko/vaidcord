"""Discord DAVE / MLS voice E2EE protocol stack.

This package implements the Discord DAVE protocol described at
https://github.com/discord/dave-protocol/blob/main/protocol.md and is
intentionally laid out so it can be extracted into a standalone library
without depending on the rest of vaidcord:

* :mod:`.errors` -- exception hierarchy.
* :mod:`.opcodes` -- voice gateway opcodes 21-31.
* :mod:`.models` -- payload dataclasses (``DaveTransition``, ``DaveOutboundPayload``...).
* :mod:`.state` -- :class:`DaveProtocolState`, the observable session state.
* :mod:`.controller` -- :class:`DaveProtocolController`, the gateway-facing state machine.
* :mod:`.backend` -- the :class:`DaveCryptoBackend` protocol and a no-op default.
* :mod:`.crypto` -- HKDF, AEAD, ratchet, and frame helpers.
* :mod:`.mls` -- MLS provider abstraction with an in-process reference.
* :mod:`.reference` -- a :class:`ReferenceDaveBackend` wired to the in-process MLS provider.

Most callers only need the symbols re-exported here; advanced use cases
(custom MLS providers, alternative ratchet schedules) can import directly
from the submodules.
"""

from .backend import DaveCryptoBackend, UnsupportedDaveBackend
from .controller import DaveProtocolController
from .errors import (
    DaveBackendError,
    DaveCryptoError,
    DaveError,
    DaveMLSError,
    DavePayloadError,
    DaveUnsupportedError,
)
from .models import (
    DaveCommit,
    DaveKeyPackage,
    DaveOutboundPayload,
    DaveSenderInfo,
    DaveTransition,
)
from .opcodes import CLIENT_TO_SERVER, SERVER_TO_CLIENT, DaveOpcode
from .reference import DEFAULT_PROTOCOL_VERSION, ReferenceDaveBackend
from .state import DaveProtocolState

__all__ = [
    # Errors
    "DaveError",
    "DaveUnsupportedError",
    "DavePayloadError",
    "DaveBackendError",
    "DaveCryptoError",
    "DaveMLSError",
    # Opcodes
    "DaveOpcode",
    "SERVER_TO_CLIENT",
    "CLIENT_TO_SERVER",
    # Models
    "DaveOutboundPayload",
    "DaveTransition",
    "DaveKeyPackage",
    "DaveCommit",
    "DaveSenderInfo",
    # State machine
    "DaveProtocolState",
    "DaveProtocolController",
    # Backend
    "DaveCryptoBackend",
    "UnsupportedDaveBackend",
    "ReferenceDaveBackend",
    "DEFAULT_PROTOCOL_VERSION",
]
