"""Per-sender forward-secure ratchet used by the reference DAVE backend.

A ratchet keeps a single 32-byte ``chain_secret`` and, on demand, derives a
``RatchetKey`` consisting of a 16-byte AES-128-GCM key plus a 12-byte nonce
seed. Each step replaces the chain secret with a fresh value derived from
the previous one, giving forward secrecy: an attacker who later compromises
the chain cannot decrypt any frame whose key has already been forgotten.

The ratchet uses HKDF-Expand-Label twice per step, once to derive the key
material and once to advance the chain. The labels live in
:mod:`vaidcord.voice.dave.crypto.kdf` so that downstream MLS providers can
share them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .aead import AES128_KEY_BYTES
from .kdf import DAVE_KDF_RATCHET_LABEL, hkdf_expand_label

CHAIN_SECRET_BYTES = 32
NONCE_SEED_BYTES = 12


@dataclass(frozen=True, slots=True)
class RatchetKey:
    """A frame-encryption key produced by :class:`DaveRatchet`."""

    generation: int
    """Strictly monotonic counter incremented on every ratchet step."""

    key: bytes
    """16-byte AES-128-GCM key."""

    nonce_seed: bytes
    """12-byte nonce seed; XOR with the per-frame counter before AEAD."""


class DaveRatchet:
    """Forward-secure key ratchet bound to a single (sender, epoch) pair.

    The ratchet is *not* thread-safe. Callers should serialize access from
    a single asyncio task or guard it with their own lock if used elsewhere.
    """

    __slots__ = ("_chain", "_generation", "_max_skip", "_skipped")

    def __init__(self, *, base_secret: bytes, max_skip: int = 32) -> None:
        if len(base_secret) != CHAIN_SECRET_BYTES:
            raise ValueError(
                f"base_secret must be {CHAIN_SECRET_BYTES} bytes, got {len(base_secret)}"
            )
        self._chain: bytes = bytes(base_secret)
        self._generation = 0
        self._max_skip = int(max_skip)
        self._skipped: dict[int, RatchetKey] = {}

    @property
    def generation(self) -> int:
        """The next generation that :meth:`derive_next` will produce."""
        return self._generation

    def derive_next(self) -> RatchetKey:
        """Produce the key for the current generation and advance the chain."""
        return self._step()

    def derive_for(self, generation: int) -> RatchetKey:
        """Return the key for ``generation``, advancing the chain as needed.

        If ``generation`` is in the past it is fetched from the bounded skip
        cache; if it is in the future the ratchet is stepped forward and any
        intermediate keys are stashed in the skip cache so out-of-order
        receivers can still decrypt them.
        """
        if generation < self._generation:
            try:
                return self._skipped.pop(generation)
            except KeyError as exc:
                raise KeyError(
                    f"Ratchet generation {generation} is no longer available"
                ) from exc

        if generation - self._generation > self._max_skip:
            raise ValueError(
                f"Refusing to skip {generation - self._generation} generations "
                f"(max_skip={self._max_skip})"
            )

        last: RatchetKey | None = None
        while self._generation <= generation:
            last = self._step()
            if self._generation - 1 < generation:
                # Stash the skipped key for delayed receivers.
                if len(self._skipped) >= self._max_skip:
                    # Drop oldest skipped key to bound memory.
                    oldest = min(self._skipped)
                    del self._skipped[oldest]
                self._skipped[self._generation - 1] = last
        assert last is not None
        return last

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _step(self) -> RatchetKey:
        # Derive AEAD key and nonce seed from the current chain.
        derived = hkdf_expand_label(
            secret=self._chain,
            label=DAVE_KDF_RATCHET_LABEL + b"-key",
            context=self._generation.to_bytes(4, "big"),
            length=AES128_KEY_BYTES + NONCE_SEED_BYTES,
        )
        key = derived[:AES128_KEY_BYTES]
        nonce_seed = derived[AES128_KEY_BYTES:]
        result = RatchetKey(generation=self._generation, key=key, nonce_seed=nonce_seed)

        # Advance the chain.
        self._chain = hkdf_expand_label(
            secret=self._chain,
            label=DAVE_KDF_RATCHET_LABEL + b"-chain",
            context=self._generation.to_bytes(4, "big"),
            length=CHAIN_SECRET_BYTES,
        )
        self._generation += 1
        return result


__all__ = ["DaveRatchet", "RatchetKey", "CHAIN_SECRET_BYTES", "NONCE_SEED_BYTES"]
