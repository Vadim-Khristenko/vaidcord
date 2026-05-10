"""AES-128-GCM frame encryption used by the DAVE reference backend.

DAVE uses AEAD with a 12-byte nonce and a 16-byte authentication tag. The
key length is 128 bits to match the protocol's ``AES_128_GCM`` cipher
suite. The :class:`FrameAEAD` helper bundles the cipher with a small
amount of validation so callers don't have to remember tag/nonce sizes.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import require_cryptography

AES128_KEY_BYTES = 16
GCM_NONCE_BYTES = 12
GCM_TAG_BYTES = 16


@dataclass(slots=True)
class FrameAEAD:
    """Bundles a 16-byte AES-128-GCM key with safe encrypt/decrypt helpers."""

    key: bytes

    def __post_init__(self) -> None:
        if len(self.key) != AES128_KEY_BYTES:
            raise ValueError(
                f"FrameAEAD key must be {AES128_KEY_BYTES} bytes, got {len(self.key)}"
            )

    def encrypt(self, *, nonce: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
        return aes128gcm_encrypt(key=self.key, nonce=nonce, plaintext=plaintext, aad=aad)

    def decrypt(self, *, nonce: bytes, ciphertext: bytes, aad: bytes = b"") -> bytes:
        return aes128gcm_decrypt(key=self.key, nonce=nonce, ciphertext=ciphertext, aad=aad)


def aes128gcm_encrypt(*, key: bytes, nonce: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """AES-128-GCM encrypt with the protocol's tag/nonce sizes."""
    require_cryptography()
    _check_aead(key=key, nonce=nonce)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(key).encrypt(nonce, plaintext, aad if aad else None)


def aes128gcm_decrypt(*, key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes = b"") -> bytes:
    """AES-128-GCM decrypt; raises ``InvalidTag`` on failure."""
    require_cryptography()
    _check_aead(key=key, nonce=nonce)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(key).decrypt(nonce, ciphertext, aad if aad else None)


def _check_aead(*, key: bytes, nonce: bytes) -> None:
    if len(key) != AES128_KEY_BYTES:
        raise ValueError(f"AES-128-GCM key must be {AES128_KEY_BYTES} bytes")
    if len(nonce) != GCM_NONCE_BYTES:
        raise ValueError(f"AES-128-GCM nonce must be {GCM_NONCE_BYTES} bytes")


__all__ = [
    "AES128_KEY_BYTES",
    "GCM_NONCE_BYTES",
    "GCM_TAG_BYTES",
    "FrameAEAD",
    "aes128gcm_encrypt",
    "aes128gcm_decrypt",
]
