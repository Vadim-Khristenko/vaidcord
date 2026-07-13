//! Voice transport demo (no network needed).
//!
//! Builds, seals and opens voice packets exactly as they would travel over
//! Discord's voice UDP socket, for every supported encryption mode, and
//! shows the IP-discovery packet format plus the SSRC demux receive path.
//!
//! Run with `cargo run --example voice_transport`.

use vaidcord::voice::{
    RtpSession, VoiceReceiver, build_ip_discovery_packet, create_voice_box,
    parse_ip_discovery_response, supported_encryption_modes,
};

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn main() -> Result<(), vaidcord::Error> {
    let secret_key: Vec<u8> = (0u8..32).collect(); // from SESSION DESCRIPTION (op 4)
    let ssrc = 0x0001_5040; // from READY (op 2)

    // --- IP discovery -------------------------------------------------- //
    let probe = build_ip_discovery_packet(ssrc);
    println!("IP discovery probe ({} bytes): {}...", probe.len(), hex(&probe[..12]));
    // Simulate the server echo so the parser can be demonstrated offline.
    let mut echo = probe;
    echo[0..2].copy_from_slice(&2u16.to_be_bytes());
    echo[8..8 + 12].copy_from_slice(b"198.51.100.7");
    echo[72..74].copy_from_slice(&50004u16.to_be_bytes());
    let (external_ip, external_port) = parse_ip_discovery_response(&echo)?;
    println!("discovered external address: {external_ip}:{external_port}\n");

    // --- Seal + open in every mode ------------------------------------- //
    let opus_frame: &[u8] = &[0xF8, 0xFF, 0xFE]; // a real bot feeds encoder output here
    for mode in supported_encryption_modes() {
        let voice_box = create_voice_box(mode, &secret_key)?;
        let mut session = RtpSession::new(ssrc);

        // Outbound: header(12) || ciphertext || 4-byte BE nonce counter.
        let packet = session.seal_frame(voice_box.as_ref(), opus_frame);
        println!("[{mode}]");
        println!("  sealed packet ({} bytes): {}", packet.len(), hex(&packet));

        // Inbound: decrypt + resolve the sender through the SSRC map (op 5).
        let mut receiver = VoiceReceiver::new(create_voice_box(mode, &secret_key)?);
        receiver.map_ssrc(ssrc, 424242);
        let frame = receiver
            .process(&packet)?
            .expect("not an RTCP packet");
        println!(
            "  opened: user={:?} seq={} ts={} opus={}\n",
            frame.user_id,
            frame.sequence,
            frame.timestamp,
            hex(&frame.opus),
        );
        assert_eq!(frame.opus, opus_frame);
    }

    println!("all modes round-tripped the frame byte-for-byte");
    Ok(())
}
