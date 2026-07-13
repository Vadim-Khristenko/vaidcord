//! RTP/RTCP packet building and parsing for the Discord voice UDP transport.
//!
//! Wire-compatible with `vaidcord-py/src/vaidcord/voice/rtp.py`: the
//! "unencrypted prefix" of a packet is the fixed 12-byte header, any CSRC
//! entries, and — when the extension bit is set — the 4-byte extension
//! profile/length preamble.

use crate::error::Error;

/// Size of the fixed RTP header.
pub const RTP_HEADER_SIZE: usize = 12;

/// Discord's Opus payload type.
pub const OPUS_PAYLOAD_TYPE: u8 = 0x78;

/// A parsed (still encrypted) RTP packet.
///
/// `header` is the unencrypted prefix as defined by the `_rtpsize`
/// encryption modes; `payload` is everything after it (ciphertext + nonce
/// suffix for encrypted transports).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RtpPacket {
    pub version: u8,
    pub padding: bool,
    pub extension: bool,
    pub marker: bool,
    pub payload_type: u8,
    pub sequence: u16,
    pub timestamp: u32,
    pub ssrc: u32,
    pub csrcs: Vec<u32>,
    pub header: Vec<u8>,
    pub payload: Vec<u8>,
}

/// Whether a datagram is an RTCP packet (SR=200 ... APP=204).
pub fn is_rtcp_packet(data: &[u8]) -> bool {
    data.len() >= 2 && (200..=204).contains(&data[1])
}

/// Build a fixed 12-byte RTP header (version 2, no padding/extension/CSRC).
pub fn build_rtp_header(payload_type: u8, sequence: u16, timestamp: u32, ssrc: u32) -> [u8; 12] {
    let mut header = [0u8; 12];
    header[0] = 0x80;
    header[1] = payload_type & 0x7F;
    header[2..4].copy_from_slice(&sequence.to_be_bytes());
    header[4..8].copy_from_slice(&timestamp.to_be_bytes());
    header[8..12].copy_from_slice(&ssrc.to_be_bytes());
    header
}

/// Parse an RTP datagram into its unencrypted prefix and payload.
pub fn parse_rtp_packet(data: &[u8]) -> Result<RtpPacket, Error> {
    if data.len() < RTP_HEADER_SIZE {
        return Err(Error::Voice(format!(
            "RTP packet too short: {} bytes",
            data.len()
        )));
    }
    let first = data[0];
    let second = data[1];
    let sequence = u16::from_be_bytes([data[2], data[3]]);
    let timestamp = u32::from_be_bytes([data[4], data[5], data[6], data[7]]);
    let ssrc = u32::from_be_bytes([data[8], data[9], data[10], data[11]]);

    let version = first >> 6;
    let padding = first & 0x20 != 0;
    let extension = first & 0x10 != 0;
    let csrc_count = (first & 0x0F) as usize;
    let marker = second & 0x80 != 0;
    let payload_type = second & 0x7F;

    let mut offset = RTP_HEADER_SIZE;
    if data.len() < offset + csrc_count * 4 {
        return Err(Error::Voice(
            "RTP packet truncated inside CSRC list".to_string(),
        ));
    }
    let mut csrcs = Vec::with_capacity(csrc_count);
    for _ in 0..csrc_count {
        csrcs.push(u32::from_be_bytes([
            data[offset],
            data[offset + 1],
            data[offset + 2],
            data[offset + 3],
        ]));
        offset += 4;
    }
    if extension {
        if data.len() < offset + 4 {
            return Err(Error::Voice(
                "RTP packet truncated inside extension preamble".to_string(),
            ));
        }
        offset += 4;
    }

    Ok(RtpPacket {
        version,
        padding,
        extension,
        marker,
        payload_type,
        sequence,
        timestamp,
        ssrc,
        csrcs,
        header: data[..offset].to_vec(),
        payload: data[offset..].to_vec(),
    })
}

/// Drop the decrypted header-extension words from `plaintext`.
///
/// In the `_rtpsize` modes the 4-byte extension preamble stays in the clear
/// (as part of [`RtpPacket::header`]) while the extension words themselves
/// are encrypted at the start of the payload.
pub fn strip_header_extension<'a>(packet: &RtpPacket, plaintext: &'a [u8]) -> &'a [u8] {
    if !packet.extension {
        return plaintext;
    }
    let header = &packet.header;
    let ext_words =
        u16::from_be_bytes([header[header.len() - 2], header[header.len() - 1]]) as usize;
    plaintext.get(ext_words * 4..).unwrap_or(&[])
}

#[cfg(test)]
pub(crate) fn make_test_rtp_header(sequence: u16, timestamp: u32, ssrc: u32, extension: bool) -> Vec<u8> {
    let mut header = build_rtp_header(OPUS_PAYLOAD_TYPE, sequence, timestamp, ssrc).to_vec();
    if extension {
        header[0] |= 0x10;
        // one 4-byte extension word: profile 0xBEDE, length 1
        header.extend_from_slice(&0xBEDEu16.to_be_bytes());
        header.extend_from_slice(&1u16.to_be_bytes());
    }
    header
}

#[cfg(test)]
mod tests {
    use super::*;

    // Port of tests from vaidcord-py/tests/test_voice_protocol.py so the two
    // SDKs are verified against the same wire format.

    #[test]
    fn parse_rtp_packet_basic_fields() {
        let mut data = make_test_rtp_header(42, 1920, 99, false);
        data.extend_from_slice(b"payload");
        let packet = parse_rtp_packet(&data).unwrap();
        assert_eq!(packet.version, 2);
        assert_eq!(packet.payload_type, 0x78);
        assert_eq!(packet.sequence, 42);
        assert_eq!(packet.timestamp, 1920);
        assert_eq!(packet.ssrc, 99);
        assert_eq!(packet.header, &data[..12]);
        assert_eq!(packet.payload, b"payload");
    }

    #[test]
    fn parse_rtp_packet_with_extension_preamble() {
        let mut data = make_test_rtp_header(1, 960, 7, true);
        data.extend_from_slice(b"rest");
        let packet = parse_rtp_packet(&data).unwrap();
        assert!(packet.extension);
        assert_eq!(packet.header.len(), 16);
        assert_eq!(packet.payload, b"rest");
        // one extension word (4 bytes) is stripped from the decrypted payload
        assert_eq!(strip_header_extension(&packet, b"WORDopus"), b"opus");
    }

    #[test]
    fn rtcp_detection() {
        let mut rtcp = vec![0x80, 201];
        rtcp.extend_from_slice(&[0; 6]);
        assert!(is_rtcp_packet(&rtcp));
        let mut rtp = make_test_rtp_header(1, 960, 7, false);
        rtp.push(b'x');
        assert!(!is_rtcp_packet(&rtp));
    }

    #[test]
    fn parse_rtp_packet_rejects_short_input() {
        assert!(parse_rtp_packet(&[0x80, 0x78]).is_err());
    }

    #[test]
    fn parse_rtp_packet_rejects_truncated_csrc_list() {
        let mut data = make_test_rtp_header(1, 960, 7, false);
        data[0] |= 0x02; // csrc_count = 2, but no CSRC bytes present
        assert!(parse_rtp_packet(&data).is_err());
    }

    #[test]
    fn build_rtp_header_roundtrips() {
        let header = build_rtp_header(OPUS_PAYLOAD_TYPE, 0xABCD, 0xDEADBEEF, 0x01020304);
        let packet = parse_rtp_packet(&header).unwrap();
        assert_eq!(packet.sequence, 0xABCD);
        assert_eq!(packet.timestamp, 0xDEADBEEF);
        assert_eq!(packet.ssrc, 0x01020304);
        assert!(!packet.extension);
        assert!(packet.payload.is_empty());
    }
}
