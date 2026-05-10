"""Cryptographic primitives used by the DAVE reference backend.

The primitives in this package are pure functions that don't know about
voice gateways, websockets, or the rest of vaidcord. They are designed to be
unit-testable and re-usable in a standalone DAVE library.

The HKDF, ratchet, AEAD, and frame helpers all require the
`cryptography <https://pypi.org/project/cryptography/>`_ package. When
``cryptography`` is missing, importing them raises a clear
:class:`~vaidcord.voice.dave.errors.DaveCryptoError` with installation
instructions instead of a generic ``ImportError`` from somewhere deep in
the call stack.
"""

from __future__ import annotations

from ..errors import DaveCryptoError

try:
    import cryptography  # noqa: F401
except ImportError:  # pragma: no cover - exercised by environments without crypto
    HAS_CRYPTOGRAPHY = False
else:
    HAS_CRYPTOGRAPHY = True


def require_cryptography() -> None:
    """Raise :class:`DaveCryptoError` if the ``cryptography`` package is missing."""
    if not HAS_CRYPTOGRAPHY:
        raise DaveCryptoError(
            "DAVE crypto requires the `cryptography` package. "
            "Install it via `pip install vaidcord[voice]` or "
            "`pip install cryptography>=42.0.0`."
        )


from .aead import (  # noqa: E402
    AES128_KEY_BYTES,
    GCM_NONCE_BYTES,
    GCM_TAG_BYTES,
    FrameAEAD,
    aes128gcm_decrypt,
    aes128gcm_encrypt,
)
from .frame import build_frame_aad, build_frame_nonce, parse_frame_nonce  # noqa: E402
from .kdf import (  # noqa: E402
    DAVE_KDF_BASE_LABEL,
    DAVE_KDF_RATCHET_LABEL,
    DAVE_KDF_SENDER_LABEL,
    hkdf_expand,
    hkdf_expand_label,
    hkdf_extract,
)
from .ratchet import DaveRatchet, RatchetKey  # noqa: E402

__all__ = [
    "HAS_CRYPTOGRAPHY",
    "require_cryptography",
    "DAVE_KDF_BASE_LABEL",
    "DAVE_KDF_RATCHET_LABEL",
    "DAVE_KDF_SENDER_LABEL",
    "hkdf_expand",
    "hkdf_extract",
    "hkdf_expand_label",
    "AES128_KEY_BYTES",
    "GCM_NONCE_BYTES",
    "GCM_TAG_BYTES",
    "FrameAEAD",
    "aes128gcm_decrypt",
    "aes128gcm_encrypt",
    "build_frame_aad",
    "build_frame_nonce",
    "parse_frame_nonce",
    "DaveRatchet",
    "RatchetKey",
]
