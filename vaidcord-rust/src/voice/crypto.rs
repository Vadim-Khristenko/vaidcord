//! Transport encryption for Discord voice RTP packets.
//!
//! Implements the `_rtpsize` family of encryption modes as symmetric
//! seal/open pairs so the same code path serves both sending and receiving.
//! Wire format (identical to `vaidcord-py/src/vaidcord/voice/crypto.py`):
//!
//! ```text
//! packet = unencrypted RTP prefix || ciphertext || 4-byte BE nonce counter
//! ```
//!
//! * AEAD nonce = the 4-byte counter left-aligned and zero-padded (12 bytes
//!   for AES-GCM, 24 bytes for XChaCha20/XSalsa20).
//! * AEAD AAD = the unencrypted RTP prefix.
//! * After decrypting, `ext_words * 4` bytes are stripped when the RTP
//!   extension bit is set.

use aes_gcm::aead::{Aead, KeyInit, Payload};
use aes_gcm::Aes256Gcm;
use chacha20poly1305::XChaCha20Poly1305;
use crypto_secretbox::XSalsa20Poly1305;

use crate::error::Error;

use super::rtp::{RtpPacket, parse_rtp_packet, strip_header_extension};

/// `aead_aes256_gcm_rtpsize` — Discord's preferred mode.
pub const MODE_AES256_GCM: &str = "aead_aes256_gcm_rtpsize";
/// `aead_xchacha20_poly1305_rtpsize` — required fallback mode.
pub const MODE_XCHACHA20_POLY1305: &str = "aead_xchacha20_poly1305_rtpsize";
/// `xsalsa20_poly1305_lite_rtpsize` — legacy mode.
pub const MODE_XSALSA20_POLY1305_LITE: &str = "xsalsa20_poly1305_lite_rtpsize";

/// Encryption modes supported by [`create_voice_box`], in preference order.
pub fn supported_encryption_modes() -> &'static [&'static str] {
    &[
        MODE_AES256_GCM,
        MODE_XCHACHA20_POLY1305,
        MODE_XSALSA20_POLY1305_LITE,
    ]
}

/// Pick the first mutually supported mode from a server-offered list.
pub fn select_encryption_mode(offered: &[String]) -> Option<&'static str> {
    supported_encryption_modes()
        .iter()
        .find(|mode| offered.iter().any(|offer| offer == *mode))
        .copied()
}

fn nonce_bytes<const N: usize>(nonce_counter: u32) -> [u8; N] {
    let mut nonce = [0u8; N];
    nonce[..4].copy_from_slice(&nonce_counter.to_be_bytes());
    nonce
}

fn decryption_error(mode: &str) -> Error {
    Error::Voice(format!("{mode} authentication failed"))
}

/// Seals outbound and opens inbound RTP payloads for one session key.
pub trait VoiceBox: Send + Sync {
    /// The negotiated encryption mode string.
    fn mode(&self) -> &'static str;

    /// Encrypt `plaintext`; returns `ciphertext || nonce4` to append after
    /// `header` on the wire.
    fn seal(&self, header: &[u8], plaintext: &[u8], nonce_counter: u32) -> Vec<u8>;

    /// Decrypt `ciphertext` (authenticating `header` for the AEAD modes).
    fn open(&self, header: &[u8], ciphertext: &[u8], nonce4: [u8; 4]) -> Result<Vec<u8>, Error>;

    /// Parse and decrypt a full inbound RTP datagram.
    ///
    /// Returns the parsed packet and the decrypted media payload with any
    /// header-extension words already stripped.
    fn open_packet(&self, data: &[u8]) -> Result<(RtpPacket, Vec<u8>), Error> {
        let packet = parse_rtp_packet(data)?;
        if packet.payload.len() < 4 {
            return Err(Error::Voice(
                "encrypted RTP payload too short for nonce suffix".to_string(),
            ));
        }
        let (ciphertext, nonce4) = packet.payload.split_at(packet.payload.len() - 4);
        let nonce4: [u8; 4] = nonce4.try_into().expect("split_at guarantees 4 bytes");
        let plaintext = self.open(&packet.header, ciphertext, nonce4)?;
        let media = strip_header_extension(&packet, &plaintext).to_vec();
        Ok((packet, media))
    }
}

/// `aead_aes256_gcm_rtpsize`.
pub struct AeadAes256GcmRtpsize {
    aead: Aes256Gcm,
}

impl VoiceBox for AeadAes256GcmRtpsize {
    fn mode(&self) -> &'static str {
        MODE_AES256_GCM
    }

    fn seal(&self, header: &[u8], plaintext: &[u8], nonce_counter: u32) -> Vec<u8> {
        let nonce = nonce_bytes::<12>(nonce_counter);
        let mut sealed = self
            .aead
            .encrypt(
                (&nonce).into(),
                Payload {
                    msg: plaintext,
                    aad: header,
                },
            )
            .expect("AES-GCM sealing is infallible for in-memory buffers");
        sealed.extend_from_slice(&nonce[..4]);
        sealed
    }

    fn open(&self, header: &[u8], ciphertext: &[u8], nonce4: [u8; 4]) -> Result<Vec<u8>, Error> {
        let nonce = nonce_bytes::<12>(u32::from_be_bytes(nonce4));
        self.aead
            .decrypt(
                (&nonce).into(),
                Payload {
                    msg: ciphertext,
                    aad: header,
                },
            )
            .map_err(|_| decryption_error("AES256-GCM"))
    }
}

/// `aead_xchacha20_poly1305_rtpsize`.
pub struct AeadXChaCha20Poly1305Rtpsize {
    aead: XChaCha20Poly1305,
}

impl VoiceBox for AeadXChaCha20Poly1305Rtpsize {
    fn mode(&self) -> &'static str {
        MODE_XCHACHA20_POLY1305
    }

    fn seal(&self, header: &[u8], plaintext: &[u8], nonce_counter: u32) -> Vec<u8> {
        let nonce = nonce_bytes::<24>(nonce_counter);
        let mut sealed = self
            .aead
            .encrypt(
                (&nonce).into(),
                Payload {
                    msg: plaintext,
                    aad: header,
                },
            )
            .expect("XChaCha20 sealing is infallible for in-memory buffers");
        sealed.extend_from_slice(&nonce[..4]);
        sealed
    }

    fn open(&self, header: &[u8], ciphertext: &[u8], nonce4: [u8; 4]) -> Result<Vec<u8>, Error> {
        let nonce = nonce_bytes::<24>(u32::from_be_bytes(nonce4));
        self.aead
            .decrypt(
                (&nonce).into(),
                Payload {
                    msg: ciphertext,
                    aad: header,
                },
            )
            .map_err(|_| decryption_error("XChaCha20-Poly1305"))
    }
}

/// `xsalsa20_poly1305_lite_rtpsize` (legacy; no AAD — secretbox has none).
pub struct XSalsa20Poly1305LiteRtpsize {
    secretbox: XSalsa20Poly1305,
}

impl VoiceBox for XSalsa20Poly1305LiteRtpsize {
    fn mode(&self) -> &'static str {
        MODE_XSALSA20_POLY1305_LITE
    }

    fn seal(&self, _header: &[u8], plaintext: &[u8], nonce_counter: u32) -> Vec<u8> {
        let nonce = nonce_bytes::<24>(nonce_counter);
        let mut sealed = self
            .secretbox
            .encrypt((&nonce).into(), plaintext)
            .expect("secretbox sealing is infallible for in-memory buffers");
        sealed.extend_from_slice(&nonce[..4]);
        sealed
    }

    fn open(&self, _header: &[u8], ciphertext: &[u8], nonce4: [u8; 4]) -> Result<Vec<u8>, Error> {
        let nonce = nonce_bytes::<24>(u32::from_be_bytes(nonce4));
        self.secretbox
            .decrypt((&nonce).into(), ciphertext)
            .map_err(|_| decryption_error("XSalsa20-Poly1305"))
    }
}

/// Create the [`VoiceBox`] for a negotiated mode and 32-byte session key.
pub fn create_voice_box(mode: &str, secret_key: &[u8]) -> Result<Box<dyn VoiceBox>, Error> {
    if secret_key.len() != 32 {
        return Err(Error::Voice(format!(
            "voice secret key must be 32 bytes, got {}",
            secret_key.len()
        )));
    }
    match mode {
        MODE_AES256_GCM => Ok(Box::new(AeadAes256GcmRtpsize {
            aead: Aes256Gcm::new(secret_key.into()),
        })),
        MODE_XCHACHA20_POLY1305 => Ok(Box::new(AeadXChaCha20Poly1305Rtpsize {
            aead: XChaCha20Poly1305::new(secret_key.into()),
        })),
        MODE_XSALSA20_POLY1305_LITE => Ok(Box::new(XSalsa20Poly1305LiteRtpsize {
            secretbox: XSalsa20Poly1305::new(secret_key.into()),
        })),
        other => Err(Error::Voice(format!(
            "unsupported voice encryption mode: {other}"
        ))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::voice::rtp::make_test_rtp_header;

    // Ports of the crypto cases in vaidcord-py/tests/test_voice_protocol.py.

    fn key() -> Vec<u8> {
        (0u8..32).collect()
    }

    #[test]
    fn voice_box_seal_open_roundtrip_all_modes() {
        for mode in supported_encryption_modes() {
            let voice_box = create_voice_box(mode, &key()).unwrap();
            let header = make_test_rtp_header(1, 960, 7, false);
            let sealed = voice_box.seal(&header, b"opus data", 1234);
            let mut datagram = header.clone();
            datagram.extend_from_slice(&sealed);
            let (packet, payload) = voice_box.open_packet(&datagram).unwrap();
            assert_eq!(payload, b"opus data", "mode {mode}");
            assert_eq!(packet.ssrc, 7, "mode {mode}");
        }
    }

    #[test]
    fn voice_box_rejects_tampered_header() {
        for mode in [MODE_AES256_GCM, MODE_XCHACHA20_POLY1305] {
            let voice_box = create_voice_box(mode, &key()).unwrap();
            let header = make_test_rtp_header(1, 960, 7, false);
            let sealed = voice_box.seal(&header, b"opus data", 1);
            let mut tampered = header.clone();
            tampered.extend_from_slice(&sealed);
            tampered[8] ^= 0xFF; // flip a bit inside the authenticated SSRC field
            assert!(voice_box.open_packet(&tampered).is_err(), "mode {mode}");
        }
    }

    #[test]
    fn voice_box_rejects_tampered_ciphertext_all_modes() {
        for mode in supported_encryption_modes() {
            let voice_box = create_voice_box(mode, &key()).unwrap();
            let header = make_test_rtp_header(1, 960, 7, false);
            let sealed = voice_box.seal(&header, b"opus data", 1);
            let mut datagram = header.clone();
            datagram.extend_from_slice(&sealed);
            let flip_at = header.len() + 2; // inside the ciphertext
            datagram[flip_at] ^= 0xFF;
            assert!(voice_box.open_packet(&datagram).is_err(), "mode {mode}");
        }
    }

    #[test]
    fn voice_box_strips_encrypted_extension_words() {
        let voice_box = create_voice_box(MODE_AES256_GCM, &key()).unwrap();
        let header = make_test_rtp_header(1, 960, 7, true);
        let mut plaintext = b"EXT!".to_vec();
        plaintext.extend_from_slice(b"opus data");
        let sealed = voice_box.seal(&header, &plaintext, 7);
        let mut datagram = header.clone();
        datagram.extend_from_slice(&sealed);
        let (_, payload) = voice_box.open_packet(&datagram).unwrap();
        assert_eq!(payload, b"opus data");
    }

    #[test]
    fn create_voice_box_unknown_mode() {
        let error = match create_voice_box("xsalsa20_poly1305", &key()) {
            Err(error) => error,
            Ok(_) => panic!("expected unsupported-mode error"),
        };
        assert!(error.to_string().contains("unsupported voice encryption mode"));
    }

    #[test]
    fn create_voice_box_rejects_bad_key_length() {
        assert!(create_voice_box(MODE_AES256_GCM, &[0u8; 16]).is_err());
    }

    #[test]
    fn supported_modes_cover_discord_required_set() {
        let modes = supported_encryption_modes();
        assert!(modes.contains(&MODE_AES256_GCM));
        assert!(modes.contains(&MODE_XCHACHA20_POLY1305));
    }

    #[test]
    fn select_encryption_mode_prefers_gcm() {
        let offered = vec![
            "xsalsa20_poly1305_lite_rtpsize".to_string(),
            "aead_xchacha20_poly1305_rtpsize".to_string(),
            "aead_aes256_gcm_rtpsize".to_string(),
        ];
        assert_eq!(select_encryption_mode(&offered), Some(MODE_AES256_GCM));
        assert_eq!(select_encryption_mode(&["nope".to_string()]), None);
    }

    #[test]
    fn open_packet_requires_nonce_suffix() {
        let voice_box = create_voice_box(MODE_AES256_GCM, &key()).unwrap();
        let mut datagram = make_test_rtp_header(1, 960, 7, false);
        datagram.extend_from_slice(&[0, 1, 2]); // < 4 bytes of payload
        assert!(voice_box.open_packet(&datagram).is_err());
    }

    #[test]
    fn wire_compatible_with_python_sdk_known_answers() {
        // Vectors generated with vaidcord-py (voice/crypto.py):
        // key = bytes(range(32)), header = RTP(seq=0, ts=0, ssrc=0x15040),
        // plaintext = opus silence frame, nonce counter = 0.
        let header = make_test_rtp_header(0, 0, 0x0001_5040, false);
        let plaintext = [0xF8u8, 0xFF, 0xFE];
        for (mode, expected_hex) in [
            (
                MODE_AES256_GCM,
                "f6434bc5c6d4266eb9863f39423afa7ecc8a8100000000",
            ),
            (
                MODE_XCHACHA20_POLY1305,
                "6df972891083289edf6b1d48111a78a7acf7be00000000",
            ),
            (
                MODE_XSALSA20_POLY1305_LITE,
                "2e07c17fbdb7ca8975c0f53642267b7ab2f10e00000000",
            ),
        ] {
            let voice_box = create_voice_box(mode, &key()).unwrap();
            let sealed = voice_box.seal(&header, &plaintext, 0);
            let sealed_hex: String = sealed.iter().map(|byte| format!("{byte:02x}")).collect();
            assert_eq!(sealed_hex, expected_hex, "mode {mode}");
        }
    }

    #[test]
    fn nonce_is_counter_padded_with_zeros() {
        // Same plaintext + counter must produce identical packets across
        // calls (deterministic nonce derivation is what makes the SDKs
        // wire-compatible).
        let voice_box = create_voice_box(MODE_XCHACHA20_POLY1305, &key()).unwrap();
        let header = make_test_rtp_header(9, 8, 7, false);
        let a = voice_box.seal(&header, b"x", 0xA1B2C3D4);
        let b = voice_box.seal(&header, b"x", 0xA1B2C3D4);
        assert_eq!(a, b);
        assert_eq!(&a[a.len() - 4..], &[0xA1, 0xB2, 0xC3, 0xD4]);
    }
}
