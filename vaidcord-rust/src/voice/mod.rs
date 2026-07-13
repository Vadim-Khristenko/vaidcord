//! Voice transport foundations.
//!
//! Layout (mirrors `vaidcord-py/src/vaidcord/voice/`):
//!
//! * [`protocol`] — voice gateway opcode/close-code constants + DAVE config.
//! * [`gateway`] — voice websocket v8: identify/resume/heartbeat with
//!   `seq_ack`, READY, session description, SSRC map, close-code policy.
//! * [`udp`] — UDP socket + 74-byte IP discovery.
//! * [`rtp`] — RTP packet building/parsing (`_rtpsize` unencrypted prefix).
//! * [`crypto`] — transport encryption (`aead_aes256_gcm_rtpsize`,
//!   `aead_xchacha20_poly1305_rtpsize`, `xsalsa20_poly1305_lite_rtpsize`),
//!   wire-compatible with the Python SDK in both directions.
//! * [`transport`] — outbound [`RtpSession`], drift-corrected [`FramePacer`],
//!   [`AudioSource`] + built-in sources, and the inbound [`VoiceReceiver`].
//! * `opus` (feature `opus`) — Opus encode/decode via `audiopus`/libopus.
//!   Without the feature the SDK is opus-passthrough: you supply and receive
//!   encoded opus packets.

pub mod crypto;
pub mod gateway;
#[cfg(feature = "opus")]
pub mod opus;
pub mod protocol;
pub mod rtp;
pub mod transport;
pub mod udp;

pub use crypto::{
    MODE_AES256_GCM, MODE_XCHACHA20_POLY1305, MODE_XSALSA20_POLY1305_LITE, VoiceBox,
    create_voice_box, select_encryption_mode, supported_encryption_modes,
};
pub use gateway::{
    VOICE_GATEWAY_VERSION, VoiceCloseAction, VoiceGatewayClient, VoiceGatewayEvent,
    VoiceGatewayNotice, VoiceGatewayState, VoiceIdentify, VoiceReady, VoiceSessionDescription,
    classify_voice_close_code, speaking_flags, speaking_payload,
};
pub use protocol::{DaveIdentifyConfig, VoiceGatewayCloseCode, VoiceGatewayOpcode};
pub use rtp::{
    OPUS_PAYLOAD_TYPE, RTP_HEADER_SIZE, RtpPacket, build_rtp_header, is_rtcp_packet,
    parse_rtp_packet, strip_header_extension,
};
pub use transport::{
    AudioSource, FRAME_DURATION, FramePacer, OpusFrameSource, ReceivedFrame, RtpSession,
    SAMPLES_PER_FRAME, SILENCE_FRAME, SilenceSource, VoiceReceiver,
};
pub use udp::{
    IP_DISCOVERY_PACKET_SIZE, VoiceUdpSocket, build_ip_discovery_packet,
    parse_ip_discovery_response,
};
