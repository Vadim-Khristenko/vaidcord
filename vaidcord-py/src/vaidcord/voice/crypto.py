"""Transport encryption for Discord voice RTP packets.

Implements the ``_rtpsize`` family of encryption modes as symmetric
seal/open pairs so the same code path serves both sending and receiving:

* ``aead_aes256_gcm_rtpsize`` (via ``cryptography``)
* ``aead_xchacha20_poly1305_rtpsize`` (via PyNaCl)
* ``xsalsa20_poly1305_lite_rtpsize`` (legacy, via PyNaCl)

For every mode the wire format is ``unencrypted RTP prefix || ciphertext ||
4-byte big-endian nonce counter``. The AEAD modes authenticate the
unencrypted prefix as associated data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .rtp import RTPPacket, parse_rtp_packet, strip_header_extension

__all__ = [
    "VoiceBox",
    "VoiceDecryptionError",
    "create_voice_box",
    "supported_encryption_modes",
]


class VoiceDecryptionError(RuntimeError):
    """Raised when an inbound voice packet fails authentication/decryption."""


def _require_pynacl():
    try:
        from nacl import bindings  # type: ignore[import-not-found]
    except ImportError as error:  # pragma: no cover - dependency gate
        from .audio import MissingVoiceDependency

        raise MissingVoiceDependency(
            "This voice encryption mode requires PyNaCl. "
            "Install optional voice deps with `pip install 'vaidcord[voice]'`."
        ) from error
    return bindings


def _require_aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import (
            AESGCM,  # type: ignore[import-not-found]
        )
    except ImportError as error:  # pragma: no cover - dependency gate
        from .audio import MissingVoiceDependency

        raise MissingVoiceDependency(
            "AES256-GCM voice encryption requires `cryptography`. "
            "Install optional voice deps with `pip install 'vaidcord[voice]'`."
        ) from error
    return AESGCM


class VoiceBox(ABC):
    """Seals outbound and opens inbound RTP payloads for one session key."""

    mode: str

    def __init__(self, secret_key: bytes) -> None:
        self.secret_key = bytes(secret_key)

    @abstractmethod
    def seal(self, header: bytes, plaintext: bytes, nonce_counter: int) -> bytes:
        """Encrypt ``plaintext``; returns ``ciphertext || nonce4`` to append after ``header``."""

    @abstractmethod
    def _open(self, header: bytes, ciphertext: bytes, nonce4: bytes) -> bytes:
        ...

    def open_packet(self, data: bytes) -> tuple[RTPPacket, bytes]:
        """Parse and decrypt a full inbound RTP datagram.

        Returns the parsed packet and the decrypted media payload with any
        header-extension words already stripped.
        """
        packet = parse_rtp_packet(data)
        if len(packet.payload) < 4:
            raise VoiceDecryptionError("Encrypted RTP payload too short for nonce suffix")
        ciphertext = packet.payload[:-4]
        nonce4 = packet.payload[-4:]
        plaintext = self._open(packet.header, ciphertext, nonce4)
        return packet, strip_header_extension(packet, plaintext)


class AeadAes256GcmRtpsize(VoiceBox):
    mode = "aead_aes256_gcm_rtpsize"

    def __init__(self, secret_key: bytes) -> None:
        super().__init__(secret_key)
        self._aead = _require_aesgcm()(self.secret_key)

    def seal(self, header: bytes, plaintext: bytes, nonce_counter: int) -> bytes:
        nonce4 = (nonce_counter & 0xFFFFFFFF).to_bytes(4, "big")
        nonce = nonce4 + b"\x00" * 8
        return self._aead.encrypt(nonce, plaintext, header) + nonce4

    def _open(self, header: bytes, ciphertext: bytes, nonce4: bytes) -> bytes:
        try:
            return self._aead.decrypt(nonce4 + b"\x00" * 8, ciphertext, header)
        except Exception as error:
            raise VoiceDecryptionError("AES256-GCM authentication failed") from error


class AeadXChaCha20Poly1305Rtpsize(VoiceBox):
    mode = "aead_xchacha20_poly1305_rtpsize"

    def __init__(self, secret_key: bytes) -> None:
        super().__init__(secret_key)
        self._bindings = _require_pynacl()

    def seal(self, header: bytes, plaintext: bytes, nonce_counter: int) -> bytes:
        nonce4 = (nonce_counter & 0xFFFFFFFF).to_bytes(4, "big")
        nonce = nonce4 + b"\x00" * 20
        sealed = self._bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(
            plaintext, header, nonce, self.secret_key
        )
        return bytes(sealed) + nonce4

    def _open(self, header: bytes, ciphertext: bytes, nonce4: bytes) -> bytes:
        try:
            return bytes(
                self._bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(
                    ciphertext, header, nonce4 + b"\x00" * 20, self.secret_key
                )
            )
        except Exception as error:
            raise VoiceDecryptionError("XChaCha20-Poly1305 authentication failed") from error


class XSalsa20Poly1305LiteRtpsize(VoiceBox):
    mode = "xsalsa20_poly1305_lite_rtpsize"

    def __init__(self, secret_key: bytes) -> None:
        super().__init__(secret_key)
        self._bindings = _require_pynacl()

    def seal(self, header: bytes, plaintext: bytes, nonce_counter: int) -> bytes:
        nonce4 = (nonce_counter & 0xFFFFFFFF).to_bytes(4, "big")
        nonce = nonce4 + b"\x00" * 20
        return self._bindings.crypto_secretbox(plaintext, nonce, self.secret_key) + nonce4

    def _open(self, header: bytes, ciphertext: bytes, nonce4: bytes) -> bytes:
        try:
            return self._bindings.crypto_secretbox_open(
                ciphertext, nonce4 + b"\x00" * 20, self.secret_key
            )
        except Exception as error:
            raise VoiceDecryptionError("XSalsa20-Poly1305 authentication failed") from error


_BOXES: dict[str, type[VoiceBox]] = {
    box.mode: box
    for box in (AeadAes256GcmRtpsize, AeadXChaCha20Poly1305Rtpsize, XSalsa20Poly1305LiteRtpsize)
}


def supported_encryption_modes() -> tuple[str, ...]:
    return tuple(_BOXES)


def create_voice_box(mode: str, secret_key: bytes) -> VoiceBox:
    box = _BOXES.get(mode)
    if box is None:
        raise RuntimeError(f"Unsupported voice encryption mode: {mode}")
    return box(secret_key)
