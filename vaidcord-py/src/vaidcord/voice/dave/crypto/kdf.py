"""HKDF helpers used to derive epoch / sender / ratchet keys.

The DAVE protocol derives every per-frame encryption key from the active MLS
group epoch secret using an HKDF chain (RFC 5869). Labels are scoped to the
DAVE protocol so that derived keys can never collide with keys derived for a
different purpose by the same MLS provider.
"""

from __future__ import annotations

from . import require_cryptography

DAVE_KDF_BASE_LABEL = b"DAVE-base"
"""HKDF info label for deriving a sender's per-epoch base secret."""

DAVE_KDF_SENDER_LABEL = b"DAVE-sender"
"""HKDF info label for the sender's identity-bound chain key."""

DAVE_KDF_RATCHET_LABEL = b"DAVE-ratchet"
"""HKDF info label used by :class:`~vaidcord.voice.dave.crypto.ratchet.DaveRatchet`."""


def hkdf_extract(*, salt: bytes | None, ikm: bytes) -> bytes:
    """HKDF-Extract using SHA-256.

    Returns a 32-byte pseudo-random key suitable for feeding into
    :func:`hkdf_expand`. Mirrors RFC 5869 section 2.2.
    """
    require_cryptography()
    from cryptography.hazmat.primitives import hashes, hmac

    digest_size = hashes.SHA256.digest_size
    if not salt:
        salt = b"\x00" * digest_size
    h = hmac.HMAC(salt, hashes.SHA256())
    h.update(ikm)
    return h.finalize()


def hkdf_expand(*, prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand using SHA-256.

    Mirrors RFC 5869 section 2.3 and is implemented via
    :class:`cryptography.hazmat.primitives.kdf.hkdf.HKDFExpand`.
    """
    require_cryptography()
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

    if length <= 0:
        raise ValueError("hkdf_expand: length must be positive")
    expander = HKDFExpand(algorithm=hashes.SHA256(), length=length, info=info)
    return expander.derive(prk)


def hkdf_expand_label(*, secret: bytes, label: bytes, context: bytes, length: int) -> bytes:
    """MLS-style HKDF-Expand-Label.

    The structured ``info`` parameter is the same shape MLS uses (see RFC 9420
    section 8) so that DAVE-derived keys remain compatible with future MLS
    backends that already speak the label/context convention.
    """
    require_cryptography()
    info = (
        length.to_bytes(2, "big")
        + len(label).to_bytes(1, "big")
        + label
        + len(context).to_bytes(2, "big")
        + context
    )
    return hkdf_expand(prk=secret, info=info, length=length)


__all__ = [
    "DAVE_KDF_BASE_LABEL",
    "DAVE_KDF_SENDER_LABEL",
    "DAVE_KDF_RATCHET_LABEL",
    "hkdf_extract",
    "hkdf_expand",
    "hkdf_expand_label",
]
