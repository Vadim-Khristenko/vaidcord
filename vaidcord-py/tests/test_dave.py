"""Tests for the new dave/ subpackage.

These tests cover:

* Backwards-compat surface: every symbol that used to live in
  ``vaidcord.voice.dave`` (the old single-file module) is still importable
  from the same path and from ``vaidcord``.
* Crypto primitives: HKDF, ratchet, AEAD, frame helpers.
* In-process MLS provider: epoch advancement, key packages, welcomes.
* Reference backend: end-to-end frame roundtrip + integration with the
  controller.
"""

from __future__ import annotations

import pytest

from vaidcord.voice.dave import (
    CLIENT_TO_SERVER,
    DEFAULT_PROTOCOL_VERSION,
    SERVER_TO_CLIENT,
    DaveBackendError,
    DaveCommit,
    DaveCryptoBackend,
    DaveCryptoError,
    DaveError,
    DaveKeyPackage,
    DaveMLSError,
    DaveOpcode,
    DaveOutboundPayload,
    DavePayloadError,
    DaveProtocolController,
    DaveProtocolState,
    DaveSenderInfo,
    DaveTransition,
    DaveUnsupportedError,
    ReferenceDaveBackend,
    UnsupportedDaveBackend,
)
from vaidcord.voice.dave.crypto import (
    AES128_KEY_BYTES,
    DaveRatchet,
    FrameAEAD,
    aes128gcm_decrypt,
    aes128gcm_encrypt,
    build_frame_aad,
    build_frame_nonce,
    hkdf_expand,
    hkdf_expand_label,
    hkdf_extract,
    parse_frame_nonce,
)
from vaidcord.voice.dave.mls import (
    InProcessMLSProvider,
    KeyPackage,
    MLSProvider,
    Welcome,
)

# --------------------------------------------------------------------------- #
# Backwards compatibility                                                     #
# --------------------------------------------------------------------------- #

def test_all_old_symbols_still_exposed():
    # Every symbol that used to be in vaidcord.voice.dave (the single-file
    # module) must still be importable from the same dotted path.
    legacy_names = [
        "DaveBackendError",
        "DaveCommit",
        "DaveCryptoBackend",
        "DaveKeyPackage",
        "DaveOpcode",
        "DaveOutboundPayload",
        "DavePayloadError",
        "DaveProtocolController",
        "DaveProtocolState",
        "DaveTransition",
        "DaveUnsupportedError",
        "UnsupportedDaveBackend",
    ]
    import vaidcord.voice.dave as dave_mod

    for name in legacy_names:
        assert hasattr(dave_mod, name), name


def test_top_level_package_reexports_dave_symbols():
    import vaidcord

    # Access pulls things in via __getattr__; just touch a few.
    assert vaidcord.DaveProtocolController is DaveProtocolController
    assert vaidcord.ReferenceDaveBackend is ReferenceDaveBackend
    assert vaidcord.DaveCryptoError is DaveCryptoError


def test_opcode_subsets_are_disjoint_and_complete():
    assert SERVER_TO_CLIENT.isdisjoint(CLIENT_TO_SERVER)
    assert SERVER_TO_CLIENT | CLIENT_TO_SERVER == set(DaveOpcode)


def test_error_hierarchy_is_specific():
    for exc in (DaveUnsupportedError, DavePayloadError, DaveBackendError,
                DaveCryptoError, DaveMLSError):
        assert issubclass(exc, DaveError)


# --------------------------------------------------------------------------- #
# HKDF + ratchet                                                              #
# --------------------------------------------------------------------------- #

def test_hkdf_extract_then_expand_is_deterministic():
    prk = hkdf_extract(salt=b"salt", ikm=b"input")
    out_a = hkdf_expand(prk=prk, info=b"info", length=32)
    out_b = hkdf_expand(prk=prk, info=b"info", length=32)
    assert out_a == out_b
    assert len(out_a) == 32


def test_hkdf_expand_label_changes_with_context():
    secret = b"\x00" * 32
    a = hkdf_expand_label(secret=secret, label=b"x", context=b"a", length=16)
    b = hkdf_expand_label(secret=secret, label=b"x", context=b"b", length=16)
    assert a != b


def test_ratchet_steps_produce_distinct_keys():
    seed = b"\x11" * 32
    r = DaveRatchet(base_secret=seed)
    keys = [r.derive_next() for _ in range(5)]
    assert len({k.key for k in keys}) == 5
    assert [k.generation for k in keys] == [0, 1, 2, 3, 4]


def test_ratchet_can_replay_skipped_generations():
    r = DaveRatchet(base_secret=b"\x22" * 32)
    target = r.derive_for(3)
    assert target.generation == 3
    # Earlier ones come from the skip cache.
    earlier = r.derive_for(1)
    assert earlier.generation == 1


def test_ratchet_rejects_excessive_skip():
    r = DaveRatchet(base_secret=b"\x33" * 32, max_skip=2)
    with pytest.raises(ValueError):
        r.derive_for(100)


# --------------------------------------------------------------------------- #
# AEAD                                                                        #
# --------------------------------------------------------------------------- #

def test_aead_roundtrip():
    key = b"\x42" * AES128_KEY_BYTES
    nonce = build_frame_nonce(ssrc=1, generation=2, frame_counter=3)
    aad = build_frame_aad(ssrc=1, generation=2, frame_counter=3)
    ct = aes128gcm_encrypt(key=key, nonce=nonce, plaintext=b"hello", aad=aad)
    pt = aes128gcm_decrypt(key=key, nonce=nonce, ciphertext=ct, aad=aad)
    assert pt == b"hello"


def test_aead_rejects_wrong_aad():
    from cryptography.exceptions import InvalidTag

    key = b"\x42" * AES128_KEY_BYTES
    nonce = build_frame_nonce(ssrc=1, generation=2, frame_counter=3)
    aad_a = build_frame_aad(ssrc=1, generation=2, frame_counter=3)
    aad_b = build_frame_aad(ssrc=1, generation=2, frame_counter=4)
    ct = aes128gcm_encrypt(key=key, nonce=nonce, plaintext=b"x", aad=aad_a)
    with pytest.raises(InvalidTag):
        aes128gcm_decrypt(key=key, nonce=nonce, ciphertext=ct, aad=aad_b)


def test_frame_nonce_roundtrip():
    nonce = build_frame_nonce(ssrc=0xCAFEBABE, generation=7, frame_counter=99)
    assert parse_frame_nonce(nonce) == (0xCAFEBABE, 7, 99)


def test_frame_aead_helper_validates_key_length():
    with pytest.raises(ValueError):
        FrameAEAD(key=b"\x00" * 8)


# --------------------------------------------------------------------------- #
# In-process MLS provider                                                     #
# --------------------------------------------------------------------------- #

def test_inproc_provider_starts_without_epoch():
    p = InProcessMLSProvider(member_id="alice")
    assert p.current_epoch is None
    assert p.current_epoch_secret is None


def test_inproc_provider_first_commit_sets_epoch_zero():
    p = InProcessMLSProvider(member_id="alice")
    kp = p.generate_key_package()
    commit = p.propose_add(kp)
    assert commit.epoch == 0
    assert p.current_epoch == 0
    assert p.current_epoch_secret is not None and len(p.current_epoch_secret) == 32


def test_inproc_provider_epoch_advances_each_commit():
    p = InProcessMLSProvider(member_id="alice")
    p.propose_add(p.generate_key_package())
    s0 = p.current_epoch_secret
    p.propose_add(KeyPackage(member_id="bob", public_key=b"\x00" * 32))
    s1 = p.current_epoch_secret
    assert s0 != s1
    assert p.current_epoch == 1


def test_inproc_provider_apply_welcome_overrides_epoch():
    p = InProcessMLSProvider(member_id="alice", group_id="g")
    welcome = Welcome(epoch=42, group_id="g", epoch_secret=b"\xaa" * 32, members=("alice",))
    p.apply_welcome(welcome)
    assert p.current_epoch == 42
    assert p.current_epoch_secret == b"\xaa" * 32


def test_inproc_provider_rejects_welcome_with_wrong_group_id():
    p = InProcessMLSProvider(member_id="alice", group_id="g1")
    welcome = Welcome(epoch=0, group_id="g2", epoch_secret=b"\x00" * 32)
    with pytest.raises(DaveMLSError):
        p.apply_welcome(welcome)


# --------------------------------------------------------------------------- #
# Reference backend                                                           #
# --------------------------------------------------------------------------- #

def _ready_backend() -> ReferenceDaveBackend:
    backend = ReferenceDaveBackend(member_id="alice", group_id="g")
    backend.execute_transition(DaveTransition(transition_id="x", protocol_version=1))
    backend.prepare_epoch(DaveTransition(transition_id="x", protocol_version=1, epoch=1))
    return backend


def test_reference_backend_advertises_default_protocol_version():
    backend = ReferenceDaveBackend()
    assert backend.max_protocol_version == DEFAULT_PROTOCOL_VERSION


def test_reference_backend_roundtrips_a_single_frame():
    backend = _ready_backend()
    ct = backend.encrypt_frame(ssrc=7, frame=b"audio")
    assert ct != b"audio"
    pt = backend.decrypt_frame(ssrc=7, frame=ct)
    assert pt == b"audio"


def test_reference_backend_produces_unique_ciphertext_per_frame():
    backend = _ready_backend()
    ct1 = backend.encrypt_frame(ssrc=7, frame=b"audio")
    ct2 = backend.encrypt_frame(ssrc=7, frame=b"audio")
    assert ct1 != ct2  # different counter => different nonce/key


def test_reference_backend_decrypt_handles_out_of_order_frames():
    backend = _ready_backend()
    cts = [backend.encrypt_frame(ssrc=7, frame=f"f{i}".encode()) for i in range(4)]
    # Decrypt in shuffled order; recv ratchet must still find the right key.
    for i in (3, 1, 0, 2):
        assert backend.decrypt_frame(ssrc=7, frame=cts[i]) == f"f{i}".encode()


def test_reference_backend_prepare_epoch_emits_key_package():
    backend = ReferenceDaveBackend(member_id="alice")
    kp = backend.prepare_epoch(DaveTransition(transition_id="t", protocol_version=1, epoch=1))
    assert isinstance(kp, DaveKeyPackage)
    assert "key_package" in kp.payload
    assert kp.payload["member_id"] == "alice"


def test_reference_backend_handle_proposals_returns_commit():
    backend = ReferenceDaveBackend()
    backend.prepare_epoch(DaveTransition(transition_id="t", protocol_version=1, epoch=1))
    commit = backend.handle_proposals({"proposals": []})
    assert isinstance(commit, DaveCommit)
    assert commit.payload["epoch"] >= 1


def test_reference_backend_decrypt_rejects_short_frame():
    backend = _ready_backend()
    with pytest.raises(DaveBackendError):
        backend.decrypt_frame(ssrc=7, frame=b"\x00" * 4)


# --------------------------------------------------------------------------- #
# Controller integration                                                      #
# --------------------------------------------------------------------------- #

def test_controller_with_reference_backend_negotiates_session():
    sent = []
    controller = DaveProtocolController(
        backend=ReferenceDaveBackend(),
        send_payload=sent.append,
    )
    controller.handle_session_description({"dave_protocol_version": 1})
    assert controller.state.enabled
    assert controller.state.protocol_version == 1


def test_controller_prepare_epoch_round_trips_key_package_and_ready():
    sent: list[DaveOutboundPayload] = []
    controller = DaveProtocolController(
        backend=ReferenceDaveBackend(),
        send_payload=sent.append,
    )
    handled = controller.handle_gateway_payload(
        int(DaveOpcode.PREPARE_EPOCH),
        {"transition_id": "a", "protocol_version": 1, "epoch": 2},
    )
    assert handled
    ops = [p.op for p in sent]
    assert int(DaveOpcode.MLS_KEY_PACKAGE) in ops
    assert int(DaveOpcode.TRANSITION_READY) in ops


def test_controller_returns_false_for_non_dave_opcodes():
    controller = DaveProtocolController(backend=ReferenceDaveBackend())
    assert controller.handle_gateway_payload(0, {}) is False
    assert controller.handle_gateway_payload(8, {}) is False


def test_controller_invalid_payload_type_is_payload_error():
    controller = DaveProtocolController(backend=ReferenceDaveBackend())
    with pytest.raises(DavePayloadError):
        controller.handle_session_description("not-a-mapping")  # type: ignore[arg-type]


def test_unsupported_backend_raises_on_use():
    backend = UnsupportedDaveBackend()
    with pytest.raises(DaveUnsupportedError):
        backend.prepare_transition(DaveTransition(transition_id="x", protocol_version=1))


def test_dave_cryptobackend_runtime_protocol_check():
    assert isinstance(ReferenceDaveBackend(), DaveCryptoBackend)
    assert isinstance(UnsupportedDaveBackend(), DaveCryptoBackend)


def test_mls_provider_runtime_protocol_check():
    assert isinstance(InProcessMLSProvider(member_id="x"), MLSProvider)


def test_dave_sender_info_is_hashable():
    info = DaveSenderInfo(sender_id="alice", base_secret=b"\x00" * 32)
    assert hash(info) is not None
    assert info.sender_id == "alice"


def test_dave_state_snapshot_is_serializable_dict():
    state = DaveProtocolState()
    snap = state.snapshot()
    assert "enabled" in snap
    assert isinstance(snap, dict)
