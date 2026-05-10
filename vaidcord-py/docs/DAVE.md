# DAVE / MLS voice protocol

The `vaidcord.voice.dave` subpackage implements the Discord
[DAVE protocol](https://github.com/discord/dave-protocol/blob/main/protocol.md)
state machine, frame ratchet, and AEAD pipeline. It is laid out so that it
can be lifted into a standalone library — the package has no imports from
the rest of vaidcord and a single optional dependency on
[`cryptography`](https://pypi.org/project/cryptography/).

## Public surface

```text
vaidcord.voice.dave
├── errors.py       DaveError, DaveUnsupportedError, DavePayloadError,
│                   DaveBackendError, DaveCryptoError, DaveMLSError
├── opcodes.py      DaveOpcode (21-31), SERVER_TO_CLIENT, CLIENT_TO_SERVER
├── models.py       DaveTransition, DaveOutboundPayload, DaveKeyPackage,
│                   DaveCommit, DaveSenderInfo
├── state.py        DaveProtocolState (.snapshot() for diagnostics)
├── backend.py      DaveCryptoBackend Protocol, UnsupportedDaveBackend
├── controller.py   DaveProtocolController (gateway-facing state machine)
├── crypto/
│   ├── kdf.py      HKDF Extract/Expand/Expand-Label (SHA-256)
│   ├── aead.py     AES-128-GCM, FrameAEAD wrapper
│   ├── ratchet.py  DaveRatchet — forward-secure per-sender chain
│   └── frame.py    Frame nonce / AAD layout helpers
├── mls/
│   ├── types.py    KeyPackage, Welcome, Commit, GroupEpoch
│   ├── provider.py MLSProvider Protocol
│   └── inproc.py   InProcessMLSProvider — single-party reference
└── reference.py    ReferenceDaveBackend wiring everything together
```

## Quick start (single-party loopback)

```python
from vaidcord.voice.dave import (
    DaveOpcode, DaveProtocolController, DaveTransition, ReferenceDaveBackend,
)

backend = ReferenceDaveBackend(member_id="my-bot", group_id="ch-42")
controller = DaveProtocolController(
    backend=backend,
    send_payload=lambda payload: print("send", payload),
)

controller.handle_session_description({"dave_protocol_version": 1})
controller.handle_gateway_payload(
    int(DaveOpcode.PREPARE_EPOCH),
    {"transition_id": "tx-1", "protocol_version": 1, "epoch": 1},
)
controller.handle_gateway_payload(
    int(DaveOpcode.EXECUTE_TRANSITION),
    {"transition_id": "tx-1", "protocol_version": 1},
)

cipher = backend.encrypt_frame(ssrc=42, frame=b"hello")
plain  = backend.decrypt_frame(ssrc=42, frame=cipher)
assert plain == b"hello"
```

The example at `examples/voice_dave_reference.py` runs the full opcode
flow end-to-end with annotated output.

## Wiring a real MLS backend

The DAVE controller talks only to the `DaveCryptoBackend` protocol. To
plug in a multi-party MLS implementation, implement that protocol —
typically by providing a custom `MLSProvider` and wrapping it in a
backend similar to `ReferenceDaveBackend`:

```python
class MyMLSProvider:
    """Wraps mls-rs / openmls / libdave under the MLSProvider protocol."""
    member_id: str
    current_epoch: int | None
    current_epoch_secret: bytes | None
    def generate_key_package(self): ...
    def apply_welcome(self, welcome): ...
    def apply_commit(self, commit): ...
    def propose_add(self, key_package): ...

backend = ReferenceDaveBackend(provider=MyMLSProvider(...))
```

`ReferenceDaveBackend` will use your provider for group state and reuse
the shipped HKDF / ratchet / AEAD stack for frame encryption.

## Compatibility with the legacy single-file module

The previous `vaidcord/voice/dave.py` module exported these names:

`DaveOpcode`, `DaveTransition`, `DaveOutboundPayload`, `DaveKeyPackage`,
`DaveCommit`, `DaveProtocolState`, `DaveProtocolController`,
`DaveCryptoBackend`, `UnsupportedDaveBackend`,
`DaveUnsupportedError`, `DavePayloadError`, `DaveBackendError`.

Every one of those is still importable from `vaidcord.voice.dave` and
from the top-level `vaidcord` package; existing code continues to work
unmodified.

## Testing

The DAVE subpackage carries its own test module
(`tests/test_dave.py`) covering:

* Backwards compatibility — every legacy symbol still resolves.
* HKDF determinism, label/context binding.
* Ratchet forward secrecy + skip cache.
* AEAD round-trip, AAD binding, key/nonce length validation.
* In-process MLS provider epoch advancement and welcomes.
* Reference backend frame round-trip + out-of-order replay.
* Controller integration (PREPARE_EPOCH triggers MLS_KEY_PACKAGE +
  TRANSITION_READY; non-DAVE opcodes are ignored).
