//! Opus encode/decode via `audiopus` (system libopus).
//!
//! Only built with the `opus` cargo feature:
//!
//! ```toml
//! vaidcord = { version = "0.1", features = ["opus"] }
//! ```
//!
//! Without the feature the SDK ships opus-passthrough: sources yield
//! pre-encoded opus packets and the receive path yields opus packets.

use audiopus::coder::{Decoder as OpusDecoder, Encoder as OpusEncoder};
use audiopus::{Application, Channels, SampleRate};

use crate::error::Error;

/// Discord voice sample rate.
pub const SAMPLE_RATE: u32 = 48_000;
/// Stereo.
pub const CHANNELS: usize = 2;
/// Samples per channel per 20 ms frame.
pub const SAMPLES_PER_FRAME: usize = 960;
/// i16 samples per interleaved stereo frame.
pub const FRAME_SAMPLES: usize = SAMPLES_PER_FRAME * CHANNELS;

fn opus_error(context: &str, error: audiopus::Error) -> Error {
    Error::Voice(format!("opus {context} failed: {error}"))
}

/// Stereo 48 kHz Opus encoder for 20 ms frames.
pub struct Encoder {
    inner: OpusEncoder,
}

impl Encoder {
    pub fn new() -> Result<Self, Error> {
        let mut inner = OpusEncoder::new(SampleRate::Hz48000, Channels::Stereo, Application::Audio)
            .map_err(|error| opus_error("encoder init", error))?;
        inner
            .set_bitrate(audiopus::Bitrate::BitsPerSecond(128_000))
            .map_err(|error| opus_error("encoder config", error))?;
        Ok(Self { inner })
    }

    /// Encode one interleaved stereo i16 frame (short input is zero-padded
    /// to a full 20 ms frame).
    pub fn encode(&mut self, pcm: &[i16]) -> Result<Vec<u8>, Error> {
        let mut output = vec![0u8; 4000];
        let written = if pcm.len() >= FRAME_SAMPLES {
            self.inner
                .encode(&pcm[..FRAME_SAMPLES], &mut output)
                .map_err(|error| opus_error("encode", error))?
        } else {
            let mut padded = vec![0i16; FRAME_SAMPLES];
            padded[..pcm.len()].copy_from_slice(pcm);
            self.inner
                .encode(&padded, &mut output)
                .map_err(|error| opus_error("encode", error))?
        };
        output.truncate(written);
        Ok(output)
    }
}

/// Stereo 48 kHz Opus decoder.
pub struct Decoder {
    inner: OpusDecoder,
}

impl Decoder {
    pub fn new() -> Result<Self, Error> {
        Ok(Self {
            inner: OpusDecoder::new(SampleRate::Hz48000, Channels::Stereo)
                .map_err(|error| opus_error("decoder init", error))?,
        })
    }

    /// Decode one opus packet into interleaved stereo i16 PCM.
    ///
    /// Pass `None` for packet-loss concealment.
    pub fn decode(&mut self, packet: Option<&[u8]>, fec: bool) -> Result<Vec<i16>, Error> {
        let mut pcm = vec![0i16; FRAME_SAMPLES];
        let samples_per_channel = self
            .inner
            .decode(packet, &mut pcm, fec)
            .map_err(|error| opus_error("decode", error))?;
        pcm.truncate(samples_per_channel * CHANNELS);
        Ok(pcm)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sine_frame(frequency: f64, amplitude: f64) -> Vec<i16> {
        let mut samples = Vec::with_capacity(FRAME_SAMPLES);
        for index in 0..SAMPLES_PER_FRAME {
            let value = (amplitude
                * (2.0 * std::f64::consts::PI * frequency * index as f64 / SAMPLE_RATE as f64)
                    .sin()) as i16;
            samples.push(value);
            samples.push(value);
        }
        samples
    }

    #[test]
    fn opus_encode_decode_roundtrip() {
        let mut encoder = Encoder::new().unwrap();
        let mut decoder = Decoder::new().unwrap();
        let packet = encoder.encode(&sine_frame(440.0, 12_000.0)).unwrap();
        assert!(!packet.is_empty() && packet.len() < 1500);
        let pcm = decoder.decode(Some(&packet), false).unwrap();
        assert_eq!(pcm.len(), FRAME_SAMPLES);
    }

    #[test]
    fn opus_decoder_packet_loss_concealment() {
        let mut decoder = Decoder::new().unwrap();
        let pcm = decoder.decode(None, false).unwrap();
        assert_eq!(pcm.len(), FRAME_SAMPLES);
    }

    #[test]
    fn opus_silence_frame_decodes_quietly() {
        let mut decoder = Decoder::new().unwrap();
        let pcm = decoder
            .decode(Some(&crate::voice::transport::SILENCE_FRAME), false)
            .unwrap();
        assert_eq!(pcm.len(), FRAME_SAMPLES);
        assert!(pcm.iter().all(|sample| sample.unsigned_abs() < 128));
    }

    #[test]
    fn opus_encoder_pads_short_pcm() {
        let mut encoder = Encoder::new().unwrap();
        let packet = encoder.encode(&[0i16; 100]).unwrap();
        assert!(!packet.is_empty());
    }
}
