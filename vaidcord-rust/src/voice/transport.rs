//! Voice media transport: outbound RTP session, drift-corrected frame
//! pacing, audio sources and the inbound decrypt/demux path.

use std::collections::HashMap;
use std::future::Future;

use tokio::time::{Duration, Instant, Interval, MissedTickBehavior};

use crate::error::Error;

use super::crypto::VoiceBox;
use super::rtp::{OPUS_PAYLOAD_TYPE, RtpPacket, build_rtp_header, is_rtcp_packet};

/// Samples per 20 ms Opus frame at 48 kHz.
pub const SAMPLES_PER_FRAME: u32 = 960;

/// Duration of one voice frame.
pub const FRAME_DURATION: Duration = Duration::from_millis(20);

/// The Opus silence frame (send ~5 after speech to flush decoder state).
pub const SILENCE_FRAME: [u8; 3] = [0xF8, 0xFF, 0xFE];

// --------------------------------------------------------------------- //
// Outbound: RTP session                                                  //
// --------------------------------------------------------------------- //

/// Outbound RTP counters + sealing for one SSRC.
///
/// [`RtpSession::seal_frame`] produces a complete wire packet:
/// `header(12) || ciphertext || nonce4`, then advances sequence (+1),
/// timestamp (+960) and the nonce counter (+1) with wraparound.
#[derive(Debug)]
pub struct RtpSession {
    ssrc: u32,
    payload_type: u8,
    sequence: u16,
    timestamp: u32,
    nonce: u32,
}

impl RtpSession {
    pub fn new(ssrc: u32) -> Self {
        Self {
            ssrc,
            payload_type: OPUS_PAYLOAD_TYPE,
            sequence: 0,
            timestamp: 0,
            nonce: 0,
        }
    }

    pub const fn ssrc(&self) -> u32 {
        self.ssrc
    }

    pub const fn sequence(&self) -> u16 {
        self.sequence
    }

    pub const fn timestamp(&self) -> u32 {
        self.timestamp
    }

    pub const fn nonce(&self) -> u32 {
        self.nonce
    }

    /// Build the RTP header for the *current* counters (without advancing).
    pub fn current_header(&self) -> [u8; 12] {
        build_rtp_header(self.payload_type, self.sequence, self.timestamp, self.ssrc)
    }

    /// Seal one opus packet into a complete RTP datagram and advance the
    /// sequence/timestamp/nonce counters.
    pub fn seal_frame(&mut self, voice_box: &dyn VoiceBox, opus: &[u8]) -> Vec<u8> {
        let header = self.current_header();
        let sealed = voice_box.seal(&header, opus, self.nonce);
        let mut packet = Vec::with_capacity(header.len() + sealed.len());
        packet.extend_from_slice(&header);
        packet.extend_from_slice(&sealed);
        self.advance(SAMPLES_PER_FRAME);
        packet
    }

    fn advance(&mut self, timestamp_step: u32) {
        self.sequence = self.sequence.wrapping_add(1);
        self.timestamp = self.timestamp.wrapping_add(timestamp_step);
        self.nonce = self.nonce.wrapping_add(1);
    }
}

// --------------------------------------------------------------------- //
// Pacing                                                                 //
// --------------------------------------------------------------------- //

/// Drift-corrected 20 ms frame pacer.
///
/// Wraps [`tokio::time::interval`] with [`MissedTickBehavior::Delay`]: a
/// slow frame delays subsequent ticks instead of bursting, and the interval
/// keeps long-run cadence aligned to the frame duration.
#[derive(Debug)]
pub struct FramePacer {
    interval: Interval,
}

impl FramePacer {
    /// A pacer at the standard 20 ms voice cadence.
    pub fn new() -> Self {
        Self::with_period(FRAME_DURATION)
    }

    /// A pacer with a custom period.
    pub fn with_period(period: Duration) -> Self {
        let mut interval = tokio::time::interval(period.max(Duration::from_millis(1)));
        interval.set_missed_tick_behavior(MissedTickBehavior::Delay);
        Self { interval }
    }

    /// Wait until the next frame deadline. The first call fires immediately.
    pub async fn tick(&mut self) -> Instant {
        self.interval.tick().await
    }
}

impl Default for FramePacer {
    fn default() -> Self {
        Self::new()
    }
}

// --------------------------------------------------------------------- //
// Audio sources                                                          //
// --------------------------------------------------------------------- //

/// A source of encoded Opus packets, polled once per 20 ms frame.
///
/// Return `Ok(None)` to signal end-of-stream.
pub trait AudioSource: Send {
    /// The next opus packet, or `None` when the source is exhausted.
    fn next_frame(&mut self) -> impl Future<Output = Result<Option<Vec<u8>>, Error>> + Send;
}

/// Yields `frames` Opus silence packets, then ends.
#[derive(Debug, Clone)]
pub struct SilenceSource {
    remaining: usize,
}

impl SilenceSource {
    /// The conventional 5-frame (100 ms) silence tail.
    pub fn new() -> Self {
        Self { remaining: 5 }
    }

    pub fn with_frames(frames: usize) -> Self {
        Self { remaining: frames }
    }
}

impl Default for SilenceSource {
    fn default() -> Self {
        Self::new()
    }
}

impl AudioSource for SilenceSource {
    async fn next_frame(&mut self) -> Result<Option<Vec<u8>>, Error> {
        if self.remaining == 0 {
            return Ok(None);
        }
        self.remaining -= 1;
        Ok(Some(SILENCE_FRAME.to_vec()))
    }
}

/// Adapts any iterator of pre-encoded opus packets into an [`AudioSource`].
pub struct OpusFrameSource<I> {
    frames: I,
}

impl<I> OpusFrameSource<I>
where
    I: Iterator<Item = Vec<u8>> + Send,
{
    pub fn new(frames: I) -> Self {
        Self { frames }
    }
}

impl<I> AudioSource for OpusFrameSource<I>
where
    I: Iterator<Item = Vec<u8>> + Send,
{
    async fn next_frame(&mut self) -> Result<Option<Vec<u8>>, Error> {
        Ok(self.frames.next())
    }
}

// --------------------------------------------------------------------- //
// Inbound: decrypt + demux                                               //
// --------------------------------------------------------------------- //

/// One decrypted inbound voice frame.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReceivedFrame {
    /// Sender, when the SSRC has been announced via op 5/12.
    pub user_id: Option<u64>,
    pub ssrc: u32,
    pub sequence: u16,
    pub timestamp: u32,
    /// The decrypted opus packet (header-extension words stripped).
    pub opus: Vec<u8>,
}

/// Inbound path: decrypts RTP datagrams and resolves SSRC -> user.
///
/// Feed it raw UDP datagrams via [`VoiceReceiver::process`]; RTCP packets
/// yield `Ok(None)`, undecryptable packets yield `Err` (count them and move
/// on), valid packets yield a `(user, opus)` frame.
pub struct VoiceReceiver {
    voice_box: Box<dyn VoiceBox>,
    ssrc_to_user: HashMap<u32, u64>,
}

impl VoiceReceiver {
    pub fn new(voice_box: Box<dyn VoiceBox>) -> Self {
        Self {
            voice_box,
            ssrc_to_user: HashMap::new(),
        }
    }

    /// Record an SSRC announcement (op 5 speaking / op 12 video).
    pub fn map_ssrc(&mut self, ssrc: u32, user_id: u64) {
        self.ssrc_to_user.insert(ssrc, user_id);
    }

    /// Drop every SSRC owned by a departing user (op 13).
    pub fn forget_user(&mut self, user_id: u64) {
        self.ssrc_to_user.retain(|_, mapped| *mapped != user_id);
    }

    /// Resolve an SSRC.
    pub fn ssrc_to_user(&self, ssrc: u32) -> Option<u64> {
        self.ssrc_to_user.get(&ssrc).copied()
    }

    /// Decrypt one inbound datagram.
    pub fn process(&self, datagram: &[u8]) -> Result<Option<ReceivedFrame>, Error> {
        if is_rtcp_packet(datagram) {
            return Ok(None);
        }
        let (packet, opus): (RtpPacket, Vec<u8>) = self.voice_box.open_packet(datagram)?;
        Ok(Some(ReceivedFrame {
            user_id: self.ssrc_to_user(packet.ssrc),
            ssrc: packet.ssrc,
            sequence: packet.sequence,
            timestamp: packet.timestamp,
            opus,
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::voice::crypto::{MODE_AES256_GCM, MODE_XCHACHA20_POLY1305, create_voice_box};

    fn key() -> Vec<u8> {
        (0u8..32).collect()
    }

    #[test]
    fn rtp_session_seals_and_advances_counters() {
        let voice_box = create_voice_box(MODE_AES256_GCM, &key()).unwrap();
        let mut session = RtpSession::new(321);
        let packet1 = session.seal_frame(voice_box.as_ref(), b"frame-1");
        assert_eq!(session.sequence(), 1);
        assert_eq!(session.timestamp(), SAMPLES_PER_FRAME);
        assert_eq!(session.nonce(), 1);
        let packet2 = session.seal_frame(voice_box.as_ref(), b"frame-2");

        let (parsed1, payload1) = voice_box.open_packet(&packet1).unwrap();
        let (parsed2, payload2) = voice_box.open_packet(&packet2).unwrap();
        assert_eq!(payload1, b"frame-1");
        assert_eq!(payload2, b"frame-2");
        assert_eq!(parsed1.ssrc, 321);
        assert_eq!(parsed2.sequence, parsed1.sequence + 1);
        assert_eq!(parsed2.timestamp, parsed1.timestamp + SAMPLES_PER_FRAME);
    }

    #[test]
    fn rtp_session_counters_wrap() {
        let voice_box = create_voice_box(MODE_AES256_GCM, &key()).unwrap();
        let mut session = RtpSession::new(1);
        session.sequence = u16::MAX;
        session.timestamp = u32::MAX - 100;
        session.nonce = u32::MAX;
        let _ = session.seal_frame(voice_box.as_ref(), b"x");
        assert_eq!(session.sequence(), 0);
        assert_eq!(session.nonce(), 0);
        assert_eq!(session.timestamp(), SAMPLES_PER_FRAME - 101);
    }

    #[test]
    fn receiver_decrypts_and_demuxes_by_user() {
        // Sender side: two users' packets sealed with the shared key.
        let sender_box = create_voice_box(MODE_XCHACHA20_POLY1305, &key()).unwrap();
        let mut session_a = RtpSession::new(100);
        let mut session_b = RtpSession::new(200);
        let packet_a = session_a.seal_frame(sender_box.as_ref(), b"from-a");
        let packet_b = session_b.seal_frame(sender_box.as_ref(), b"from-b");
        let mut rtcp = vec![0x80, 201];
        rtcp.extend_from_slice(&[0u8; 10]);

        let mut receiver =
            VoiceReceiver::new(create_voice_box(MODE_XCHACHA20_POLY1305, &key()).unwrap());
        receiver.map_ssrc(100, 111);
        receiver.map_ssrc(200, 222);

        let frame_a = receiver.process(&packet_a).unwrap().unwrap();
        assert_eq!(frame_a.user_id, Some(111));
        assert_eq!(frame_a.opus, b"from-a");
        let frame_b = receiver.process(&packet_b).unwrap().unwrap();
        assert_eq!(frame_b.user_id, Some(222));
        assert_eq!(frame_b.opus, b"from-b");
        assert_eq!(receiver.process(&rtcp).unwrap(), None); // RTCP dropped

        receiver.forget_user(111);
        let unmapped = receiver.process(&{
            let mut session = RtpSession::new(100);
            session.seal_frame(sender_box.as_ref(), b"late")
        });
        // Note: nonce restarted, but crypto is deterministic per counter so
        // the packet still opens; only the user mapping is gone.
        assert_eq!(unmapped.unwrap().unwrap().user_id, None);
    }

    #[test]
    fn receiver_rejects_undecryptable_packets() {
        let receiver = VoiceReceiver::new(create_voice_box(MODE_AES256_GCM, &key()).unwrap());
        let mut bogus = crate::voice::rtp::make_test_rtp_header(1, 960, 7, false);
        bogus.extend_from_slice(&[0u8; 24]);
        assert!(receiver.process(&bogus).is_err());
    }

    #[tokio::test]
    async fn silence_source_yields_fixed_frames() {
        let mut source = SilenceSource::with_frames(3);
        let mut frames = 0;
        while let Some(frame) = source.next_frame().await.unwrap() {
            assert_eq!(frame, SILENCE_FRAME.to_vec());
            frames += 1;
        }
        assert_eq!(frames, 3);
    }

    #[tokio::test]
    async fn opus_frame_source_wraps_iterators() {
        let mut source = OpusFrameSource::new(vec![vec![1u8], vec![2u8]].into_iter());
        assert_eq!(source.next_frame().await.unwrap(), Some(vec![1]));
        assert_eq!(source.next_frame().await.unwrap(), Some(vec![2]));
        assert_eq!(source.next_frame().await.unwrap(), None);
    }

    #[tokio::test]
    async fn frame_pacer_delays_after_missed_ticks_instead_of_bursting() {
        tokio::time::pause();
        let mut pacer = FramePacer::new();
        pacer.tick().await; // immediate first tick
        // Miss two frame deadlines...
        tokio::time::advance(Duration::from_millis(50)).await;
        let late = pacer.tick().await;
        // ...the next tick after a late one must be a full period later
        // (Delay behavior), not an immediate catch-up burst.
        let next = pacer.tick().await;
        assert!(next.duration_since(late) >= FRAME_DURATION);
    }
}
