"""End-to-end demo of the DAVE/MLS voice reference backend.

This example does **not** connect to a real Discord voice gateway. Instead
it drives the new :mod:`vaidcord.voice.dave` subpackage through the same
opcode flow that Discord would and exercises the cryptographic round-trip
locally.

Run::

    uv run python examples/voice_dave_reference.py

Expected output: a sequence of opcodes the controller would emit back to
Discord (`TRANSITION_READY`, `MLS_KEY_PACKAGE`), followed by encrypted /
decrypted frame samples confirming the AEAD pipeline works.

Why care? When Discord ships a voice channel with E2EE enabled, your bot
will receive opcodes 21-31 on the voice gateway. Without a backend, frames
travel in cleartext and Discord eventually disconnects with close code
4017. The :class:`ReferenceDaveBackend` shipped here implements the
client-side state machine, MLS provider, ratchet, and AEAD so the full
state machine can be tested in CI and a real production backend (a wrapper
around an MLS library) only has to implement the same protocol.
"""

from __future__ import annotations

from vaidcord.voice.dave import (
    DaveOpcode,
    DaveOutboundPayload,
    DaveProtocolController,
    DaveTransition,
    ReferenceDaveBackend,
)


def main() -> None:
    backend = ReferenceDaveBackend(member_id="vaidcord-bot", group_id="ch-42")

    sent: list[DaveOutboundPayload] = []
    controller = DaveProtocolController(
        backend=backend,
        send_payload=sent.append,
    )

    # Step 1 - Discord sends Voice Opcode 4 with the picked DAVE version.
    print("\n[1] handle_session_description (server picks DAVE v1)")
    controller.handle_session_description({"dave_protocol_version": 1})
    print(f"    state: enabled={controller.state.enabled} version={controller.state.protocol_version}")

    # Step 2 - The gateway announces a transition. We acknowledge with op 23.
    print("\n[2] PREPARE_TRANSITION (op 21) -> TRANSITION_READY (op 23)")
    controller.handle_gateway_payload(
        int(DaveOpcode.PREPARE_TRANSITION),
        {"transition_id": "tx-1", "protocol_version": 1},
    )

    # Step 3 - The gateway opens a new MLS epoch. We respond with a key
    # package (op 26) and ack readiness (op 23).
    print("\n[3] PREPARE_EPOCH (op 24) -> MLS_KEY_PACKAGE (op 26) + TRANSITION_READY (op 23)")
    controller.handle_gateway_payload(
        int(DaveOpcode.PREPARE_EPOCH),
        {"transition_id": "tx-1", "protocol_version": 1, "epoch": 1},
    )
    for payload in sent:
        op_name = DaveOpcode(payload.op).name
        print(f"    out: op={payload.op:>2} ({op_name}) data={payload.data}")
    sent.clear()

    # Step 4 - The transition is committed. Frame encryption is now active.
    print("\n[4] EXECUTE_TRANSITION (op 22) - frame encryption is now live")
    controller.handle_gateway_payload(
        int(DaveOpcode.EXECUTE_TRANSITION),
        {"transition_id": "tx-1", "protocol_version": 1},
    )

    # Step 5 - Encrypt and decrypt a few frames.
    print("\n[5] AES-128-GCM frame round-trip via the active sender ratchet")
    for index, payload in enumerate(["hello", "world", "vaidcord"]):
        cipher = backend.encrypt_frame(ssrc=12345, frame=payload.encode())
        plain = backend.decrypt_frame(ssrc=12345, frame=cipher)
        print(f"    frame#{index}: cipher={cipher.hex()[:32]}... ({len(cipher)}b) -> {plain!r}")

    # Step 6 - Switching off DAVE.
    print("\n[6] EXECUTE_TRANSITION with version=0 disables DAVE again")
    controller.handle_gateway_payload(
        int(DaveOpcode.EXECUTE_TRANSITION),
        {"transition_id": "tx-2", "protocol_version": 0},
    )
    print(f"    state: enabled={controller.state.enabled} version={controller.state.protocol_version}")

    # The reference backend is replaceable: drop in any DaveCryptoBackend
    # (libdave wrapper, mls-rs-based MLSProvider, etc.) and the controller
    # will keep speaking the same opcode protocol on the wire. See
    # vaidcord/voice/dave/mls/provider.py and ./reference.py for the
    # extension points.
    transition = DaveTransition(transition_id="post", protocol_version=1, epoch=2)
    print(f"\n[7] DaveTransition value semantics: {transition!r}")


if __name__ == "__main__":
    main()
