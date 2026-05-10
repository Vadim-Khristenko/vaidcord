"""Reference :class:`DaveCryptoBackend` built on the in-process MLS provider.

This backend is *not* a multi-party DAVE implementation; it is a working
reference that:

* Speaks the full DAVE voice gateway opcode dance (transition / epoch /
  welcome / commit) by delegating to an :class:`MLSProvider`.
* Derives a real per-sender ratchet from the active MLS epoch secret.
* Encrypts and decrypts media frames with AES-128-GCM.

It is intended for unit testing, single-participant deployments, and as a
template for production backends that swap :class:`InProcessMLSProvider`
out for a real MLS library.

Why ship it at all? Without a working reference it's impossible to
exercise the DAVE state machine end-to-end in CI, and downstream users have
no concrete example of how to wire a custom backend into vaidcord.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .backend import DaveCryptoBackend
from .crypto import (
    DAVE_KDF_SENDER_LABEL,
    DaveRatchet,
    FrameAEAD,
    build_frame_aad,
    build_frame_nonce,
    hkdf_expand_label,
    require_cryptography,
)
from .crypto.ratchet import CHAIN_SECRET_BYTES
from .errors import DaveBackendError
from .mls import (
    Commit,
    InProcessMLSProvider,
    MLSProvider,
    Welcome,
)
from .models import DaveCommit, DaveKeyPackage, DaveTransition

DEFAULT_PROTOCOL_VERSION = 1


class ReferenceDaveBackend(DaveCryptoBackend):
    """Working reference :class:`DaveCryptoBackend`.

    Parameters
    ----------
    provider
        :class:`MLSProvider` to drive group state. Defaults to a fresh
        :class:`InProcessMLSProvider`.
    member_id
        Used to seed the in-process provider when ``provider`` is omitted.
        Ignored otherwise.
    group_id
        Voice channel / MLS group identifier; ignored if ``provider`` is
        passed in.
    protocol_version
        DAVE protocol version this backend will advertise via
        :attr:`max_protocol_version`. Defaults to ``1``.
    """

    def __init__(
        self,
        *,
        provider: MLSProvider | None = None,
        member_id: str = "vaidcord-bot",
        group_id: str = "vaidcord-dave-group",
        protocol_version: int = DEFAULT_PROTOCOL_VERSION,
    ) -> None:
        require_cryptography()
        self._provider: MLSProvider = provider or InProcessMLSProvider(
            member_id=member_id,
            group_id=group_id,
        )
        self._protocol_version = int(protocol_version)
        self._generation = 0
        # ssrc -> (ratchet, current AEAD key, generation)
        self._send_ratchets: dict[int, DaveRatchet] = {}
        self._recv_ratchets: dict[int, DaveRatchet] = {}
        self._frame_counter: dict[int, int] = {}
        self._enabled = False

    # ------------------------------------------------------------------ #
    # Backend protocol                                                   #
    # ------------------------------------------------------------------ #

    @property
    def max_protocol_version(self) -> int:
        return self._protocol_version

    @property
    def provider(self) -> MLSProvider:
        return self._provider

    def prepare_transition(self, transition: DaveTransition) -> None:
        # Nothing to pre-compute for the reference backend; the actual
        # epoch advance happens inside prepare_epoch / handle_welcome.
        pass

    def execute_transition(self, transition: DaveTransition) -> None:
        if transition.protocol_version == 0:
            self._enabled = False
            return
        self._enabled = True

    def prepare_epoch(self, transition: DaveTransition) -> DaveKeyPackage | None:
        # Build a key package the gateway will distribute to peers.
        key_package = self._provider.generate_key_package()

        # If the provider has no epoch yet, kick-start the group with a
        # commit-from-self so that we always have a working epoch secret
        # before frame encryption is requested.
        if self._provider.current_epoch is None:
            self._provider.propose_add(key_package)

        self._reseed_ratchets()
        return DaveKeyPackage(payload=key_package.to_payload(), binary=False)

    def set_external_sender(self, payload: Mapping[str, Any]) -> None:
        # The reference provider does not require an external sender; the
        # field is recorded by the controller for diagnostics.
        return None

    def handle_proposals(self, payload: Mapping[str, Any]) -> DaveCommit | None:
        # In a real backend the proposals would be parsed here. The
        # reference backend simply re-commits to advance the epoch and
        # emits a welcome carrying the new secret.
        key_package = self._provider.generate_key_package()
        commit = self._provider.propose_add(key_package)
        self._reseed_ratchets()
        return DaveCommit(payload=_commit_to_payload(commit), binary=False)

    def handle_commit_welcome(self, payload: Mapping[str, Any]) -> None:
        commit = _commit_from_payload(payload)
        if commit is not None:
            self._provider.apply_commit(commit)
            self._reseed_ratchets()

    def handle_welcome(self, payload: Mapping[str, Any]) -> None:
        welcome = _welcome_from_payload(payload)
        if welcome is None:
            raise DaveBackendError("Welcome payload missing required fields")
        self._provider.apply_welcome(welcome)
        self._reseed_ratchets()

    def handle_invalid_commit_welcome(self, payload: Mapping[str, Any]) -> None:
        # Server has rejected our last commit/welcome. The reference backend
        # has no peers, so we just bump the generation to force a fresh
        # ratchet on next prepare_epoch.
        self._send_ratchets.clear()
        self._recv_ratchets.clear()

    def encrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        ratchet = self._get_ratchet(ssrc, sending=True)
        ratchet_key = ratchet.derive_next()
        counter = self._next_frame_counter(ssrc)
        nonce = build_frame_nonce(
            ssrc=ssrc,
            generation=ratchet_key.generation,
            frame_counter=counter,
        )
        aad = build_frame_aad(
            ssrc=ssrc,
            generation=ratchet_key.generation,
            frame_counter=counter,
        )
        aead = FrameAEAD(key=ratchet_key.key)
        ciphertext = aead.encrypt(nonce=nonce, plaintext=frame, aad=aad)
        # Trailer carries generation+counter so the receiver can derive the
        # matching ratchet key. 4+4 bytes appended verbatim.
        trailer = ratchet_key.generation.to_bytes(4, "big") + counter.to_bytes(4, "big")
        return ciphertext + trailer

    def decrypt_frame(self, *, ssrc: int, frame: bytes) -> bytes:
        if len(frame) < 24:  # 16 GCM tag + 8 trailer; plaintext may be empty
            raise DaveBackendError("DAVE frame too short to decrypt")
        trailer = frame[-8:]
        body = frame[:-8]
        generation = int.from_bytes(trailer[:4], "big")
        counter = int.from_bytes(trailer[4:], "big")
        ratchet = self._get_ratchet(ssrc, sending=False)
        ratchet_key = ratchet.derive_for(generation)
        nonce = build_frame_nonce(ssrc=ssrc, generation=generation, frame_counter=counter)
        aad = build_frame_aad(ssrc=ssrc, generation=generation, frame_counter=counter)
        aead = FrameAEAD(key=ratchet_key.key)
        return aead.decrypt(nonce=nonce, ciphertext=body, aad=aad)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _get_ratchet(self, ssrc: int, *, sending: bool) -> DaveRatchet:
        bucket = self._send_ratchets if sending else self._recv_ratchets
        try:
            return bucket[ssrc]
        except KeyError:
            ratchet = self._make_ratchet(ssrc=ssrc, sending=sending)
            bucket[ssrc] = ratchet
            return ratchet

    def _make_ratchet(self, *, ssrc: int, sending: bool) -> DaveRatchet:
        # In a multi-party backend the *sender* identity (not the receiving
        # peer's identity) drives ratchet derivation, so peers can decrypt
        # frames from each sender independently. The reference backend
        # always plays both roles itself, so both directions are seeded
        # from the same (epoch_secret, sender_id, ssrc) tuple.
        epoch_secret = self._provider.current_epoch_secret
        if epoch_secret is None:
            raise DaveBackendError("No active MLS epoch; cannot derive ratchet")
        sender_id = self._provider.member_id.encode("utf-8")
        base = hkdf_expand_label(
            secret=epoch_secret,
            label=DAVE_KDF_SENDER_LABEL,
            context=sender_id + b"|" + int(ssrc).to_bytes(4, "big"),
            length=CHAIN_SECRET_BYTES,
        )
        return DaveRatchet(base_secret=base)

    def _reseed_ratchets(self) -> None:
        self._send_ratchets.clear()
        self._recv_ratchets.clear()
        self._frame_counter.clear()

    def _next_frame_counter(self, ssrc: int) -> int:
        cur = self._frame_counter.get(ssrc, 0)
        self._frame_counter[ssrc] = cur + 1
        return cur


# ---------------------------------------------------------------------- #
# Helpers for converting wire payloads back into MLS dataclasses.        #
# ---------------------------------------------------------------------- #

def _welcome_from_payload(payload: Mapping[str, Any]) -> Welcome | None:
    secret_hex = payload.get("epoch_secret")
    if secret_hex is None:
        return None
    return Welcome(
        epoch=int(payload.get("epoch", 0)),
        group_id=str(payload.get("group_id", "vaidcord-dave-group")),
        epoch_secret=bytes.fromhex(str(secret_hex)),
        members=tuple(payload.get("members") or ()),
    )


def _commit_from_payload(payload: Mapping[str, Any]) -> Commit | None:
    if "epoch" not in payload:
        return None
    welcomes_raw = payload.get("welcomes") or ()
    welcomes: list[Welcome] = []
    for w in welcomes_raw:
        wp = _welcome_from_payload(w)
        if wp is not None:
            welcomes.append(wp)
    return Commit(
        epoch=int(payload["epoch"]),
        group_id=str(payload.get("group_id", "vaidcord-dave-group")),
        add_members=tuple(payload.get("add_members") or ()),
        remove_members=tuple(payload.get("remove_members") or ()),
        welcomes=tuple(welcomes),
    )


def _commit_to_payload(commit: Commit) -> dict[str, Any]:
    return {
        "epoch": commit.epoch,
        "group_id": commit.group_id,
        "add_members": list(commit.add_members),
        "remove_members": list(commit.remove_members),
        "welcomes": [w.to_payload() for w in commit.welcomes],
    }


__all__ = ["ReferenceDaveBackend", "DEFAULT_PROTOCOL_VERSION"]
