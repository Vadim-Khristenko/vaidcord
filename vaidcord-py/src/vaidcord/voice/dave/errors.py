"""Exceptions raised by the DAVE protocol stack.

All errors are intentionally specific so that callers can tell apart a
*configuration* problem (no backend available) from a *protocol* problem
(malformed payload from the gateway) from a *backend* problem (cryptographic
operation failed).
"""

from __future__ import annotations


class DaveError(Exception):
    """Base class for all DAVE-related errors."""


class DaveUnsupportedError(DaveError, RuntimeError):
    """Raised when Discord voice requires DAVE/MLS crypto support but no backend is configured."""


class DavePayloadError(DaveError, ValueError):
    """Raised when a DAVE gateway payload has an invalid shape."""


class DaveBackendError(DaveError, RuntimeError):
    """Raised when the configured DAVE backend fails."""


class DaveCryptoError(DaveError, RuntimeError):
    """Raised when a low-level cryptographic operation fails (HKDF, AEAD, ratchet)."""


class DaveMLSError(DaveError, RuntimeError):
    """Raised when the MLS provider rejects a key-package, welcome, or commit."""


__all__ = [
    "DaveError",
    "DaveUnsupportedError",
    "DavePayloadError",
    "DaveBackendError",
    "DaveCryptoError",
    "DaveMLSError",
]
