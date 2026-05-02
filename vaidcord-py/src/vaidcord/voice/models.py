from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntFlag, StrEnum
from typing import Any


class VoiceEncryptionMode(StrEnum):
    AEAD_AES256_GCM_RTPSIZE = "aead_aes256_gcm_rtpsize"
    AEAD_XCHACHA20_POLY1305_RTPSIZE = "aead_xchacha20_poly1305_rtpsize"
    XSALSA20_POLY1305_LITE_RTPSIZE = "xsalsa20_poly1305_lite_rtpsize"


class VoiceSpeakingFlag(IntFlag):
    MICROPHONE = 1 << 0
    SOUNDSHARE = 1 << 1
    PRIORITY = 1 << 2


@dataclass(frozen=True, slots=True)
class VoiceGatewayConfig:
    version: int = 8
    max_dave_protocol_version: int = 0
    dave_backend: Any | None = field(default=None, repr=False, compare=False)
    dave_fail_fast: bool = True
    preferred_modes: tuple[VoiceEncryptionMode, ...] = (
        VoiceEncryptionMode.AEAD_AES256_GCM_RTPSIZE,
        VoiceEncryptionMode.AEAD_XCHACHA20_POLY1305_RTPSIZE,
    )


@dataclass(frozen=True, slots=True)
class VoiceState:
    guild_id: int
    channel_id: int | None
    user_id: int | None = None
    session_id: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class VoiceServerUpdate:
    guild_id: int
    token: str
    endpoint: str
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def websocket_url(self) -> str:
        endpoint = self.endpoint.removeprefix("wss://").removeprefix("https://")
        return f"wss://{endpoint}"


@dataclass(frozen=True, slots=True)
class VoiceReady:
    ssrc: int
    ip: str
    port: int
    modes: tuple[str, ...]
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def select_mode(self, config: VoiceGatewayConfig) -> str:
        available = set(self.modes)
        for mode in config.preferred_modes:
            if mode.value in available:
                return mode.value
        if self.modes:
            return self.modes[0]
        raise RuntimeError("Voice gateway did not provide encryption modes")


@dataclass(frozen=True, slots=True)
class VoiceSessionDescription:
    mode: str
    secret_key: bytes
    dave_protocol_version: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)
