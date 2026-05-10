"""DAVE frame nonce/AAD layout helpers.

DAVE encrypts each Opus/H.264 packet with a deterministic nonce that combines
the participant's SSRC, the protocol generation counter, and the per-frame
counter. The same triple is also bound into the AEAD additional data so any
mismatch produces a hard authentication failure instead of garbage audio.

The exact layout used here is::

    nonce  (12 bytes, big-endian) = ssrc(4) | generation(4) | frame_counter(4)
    AAD    (12 bytes, big-endian) = ssrc(4) | generation(4) | frame_counter(4)

This is a deliberate simplification of the DAVE on-the-wire format that keeps
the trailer bytes inside the AEAD so an attacker cannot move ciphertext
between frames.
"""

from __future__ import annotations

NONCE_BYTES = 12


def build_frame_nonce(*, ssrc: int, generation: int, frame_counter: int) -> bytes:
    """Build the per-frame AEAD nonce."""
    return (
        (int(ssrc) & 0xFFFFFFFF).to_bytes(4, "big")
        + (int(generation) & 0xFFFFFFFF).to_bytes(4, "big")
        + (int(frame_counter) & 0xFFFFFFFF).to_bytes(4, "big")
    )


def parse_frame_nonce(nonce: bytes) -> tuple[int, int, int]:
    """Inverse of :func:`build_frame_nonce`. Returns ``(ssrc, generation, counter)``."""
    if len(nonce) != NONCE_BYTES:
        raise ValueError(f"DAVE frame nonce must be {NONCE_BYTES} bytes, got {len(nonce)}")
    return (
        int.from_bytes(nonce[0:4], "big"),
        int.from_bytes(nonce[4:8], "big"),
        int.from_bytes(nonce[8:12], "big"),
    )


def build_frame_aad(*, ssrc: int, generation: int, frame_counter: int, extra: bytes = b"") -> bytes:
    """Build AEAD additional-data for a DAVE frame.

    ``extra`` is appended verbatim, so callers that include the RTP header in
    AAD (recommended for forward-compat with the on-the-wire format) can pass
    it as ``extra=rtp_header``.
    """
    return build_frame_nonce(ssrc=ssrc, generation=generation, frame_counter=frame_counter) + extra


__all__ = [
    "NONCE_BYTES",
    "build_frame_nonce",
    "parse_frame_nonce",
    "build_frame_aad",
]
