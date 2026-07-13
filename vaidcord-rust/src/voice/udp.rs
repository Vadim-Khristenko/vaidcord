//! Voice UDP transport: IP discovery + a thin async socket wrapper.

use tokio::net::UdpSocket;
use tokio::time::Duration;

use crate::error::Error;

/// Size of the IP discovery request/response packets.
pub const IP_DISCOVERY_PACKET_SIZE: usize = 74;

/// Build a 74-byte voice IP discovery request (type 1, length 70, ssrc).
pub fn build_ip_discovery_packet(ssrc: u32) -> [u8; IP_DISCOVERY_PACKET_SIZE] {
    let mut packet = [0u8; IP_DISCOVERY_PACKET_SIZE];
    packet[0..2].copy_from_slice(&1u16.to_be_bytes());
    packet[2..4].copy_from_slice(&70u16.to_be_bytes());
    packet[4..8].copy_from_slice(&ssrc.to_be_bytes());
    packet
}

/// Parse a 74-byte voice IP discovery response into `(address, port)`.
pub fn parse_ip_discovery_response(packet: &[u8]) -> Result<(String, u16), Error> {
    if packet.len() < IP_DISCOVERY_PACKET_SIZE {
        return Err(Error::Voice(
            "voice IP discovery response must be at least 74 bytes".to_string(),
        ));
    }
    let response_type = u16::from_be_bytes([packet[0], packet[1]]);
    let length = u16::from_be_bytes([packet[2], packet[3]]);
    if response_type != 2 || length != 70 {
        return Err(Error::Voice(
            "invalid voice IP discovery response header".to_string(),
        ));
    }
    let raw_address = &packet[8..72];
    let end = raw_address
        .iter()
        .position(|&byte| byte == 0)
        .unwrap_or(raw_address.len());
    let address = std::str::from_utf8(&raw_address[..end])
        .map_err(|_| Error::Voice("non-ASCII address in IP discovery response".to_string()))?
        .to_string();
    let port = u16::from_be_bytes([packet[72], packet[73]]);
    Ok((address, port))
}

/// Connected UDP socket to a Discord voice server.
#[derive(Debug)]
pub struct VoiceUdpSocket {
    socket: UdpSocket,
}

impl VoiceUdpSocket {
    /// Bind an ephemeral local port and connect it to the voice server.
    pub async fn connect(ip: &str, port: u16) -> Result<Self, Error> {
        let socket = UdpSocket::bind("0.0.0.0:0")
            .await
            .map_err(|error| Error::Voice(format!("failed to bind voice UDP socket: {error}")))?;
        socket
            .connect((ip, port))
            .await
            .map_err(|error| Error::Voice(format!("failed to connect voice UDP socket: {error}")))?;
        Ok(Self { socket })
    }

    /// Send one datagram.
    pub async fn send(&self, data: &[u8]) -> Result<(), Error> {
        self.socket
            .send(data)
            .await
            .map_err(|error| Error::Voice(format!("voice UDP send failed: {error}")))?;
        Ok(())
    }

    /// Receive one datagram (up to 4 KiB).
    pub async fn recv(&self) -> Result<Vec<u8>, Error> {
        let mut buffer = vec![0u8; 4096];
        let received = self
            .socket
            .recv(&mut buffer)
            .await
            .map_err(|error| Error::Voice(format!("voice UDP recv failed: {error}")))?;
        buffer.truncate(received);
        Ok(buffer)
    }

    /// Run IP discovery: send the 74-byte probe, await the echo carrying our
    /// external address and port.
    pub async fn discover_ip(&self, ssrc: u32, timeout: Duration) -> Result<(String, u16), Error> {
        self.send(&build_ip_discovery_packet(ssrc)).await?;
        let response = tokio::time::timeout(timeout, self.recv())
            .await
            .map_err(|_| Error::Voice("timed out waiting for IP discovery response".to_string()))??;
        parse_ip_discovery_response(&response)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn discovery_packet_format_is_74_bytes_type1_length70() {
        let packet = build_ip_discovery_packet(0xDEADBEEF);
        assert_eq!(packet.len(), 74);
        assert_eq!(&packet[0..2], &[0, 1]); // type = 1
        assert_eq!(&packet[2..4], &[0, 70]); // length = 70
        assert_eq!(&packet[4..8], &[0xDE, 0xAD, 0xBE, 0xEF]); // ssrc
        assert!(packet[8..].iter().all(|&byte| byte == 0));
    }

    #[test]
    fn discovery_response_roundtrip() {
        // Build a fake response the way Discord does: type 2, length 70,
        // ssrc, NUL-padded ASCII address, trailing BE port.
        let mut response = [0u8; 74];
        response[0..2].copy_from_slice(&2u16.to_be_bytes());
        response[2..4].copy_from_slice(&70u16.to_be_bytes());
        response[4..8].copy_from_slice(&7u32.to_be_bytes());
        response[8..8 + 9].copy_from_slice(b"203.0.113");
        response[72..74].copy_from_slice(&50004u16.to_be_bytes());

        let (address, port) = parse_ip_discovery_response(&response).unwrap();
        assert_eq!(address, "203.0.113");
        assert_eq!(port, 50004);
    }

    #[test]
    fn discovery_response_rejects_bad_header_or_size() {
        assert!(parse_ip_discovery_response(&[0u8; 10]).is_err());
        let mut response = [0u8; 74];
        response[0..2].copy_from_slice(&1u16.to_be_bytes()); // wrong type
        response[2..4].copy_from_slice(&70u16.to_be_bytes());
        assert!(parse_ip_discovery_response(&response).is_err());
    }

    #[tokio::test]
    async fn discover_ip_over_loopback_socket() {
        // A local echo server that answers the discovery probe.
        let server = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let server_addr = server.local_addr().unwrap();
        tokio::spawn(async move {
            let mut buffer = [0u8; 128];
            let (received, peer) = server.recv_from(&mut buffer).await.unwrap();
            let request = &buffer[..received];
            assert_eq!(request.len(), 74);
            let mut response = [0u8; 74];
            response[0..2].copy_from_slice(&2u16.to_be_bytes());
            response[2..4].copy_from_slice(&70u16.to_be_bytes());
            response[4..8].copy_from_slice(&request[4..8]);
            response[8..8 + 9].copy_from_slice(b"127.0.0.1");
            response[72..74].copy_from_slice(&peer.port().to_be_bytes());
            server.send_to(&response, peer).await.unwrap();
        });

        let socket = VoiceUdpSocket::connect("127.0.0.1", server_addr.port())
            .await
            .unwrap();
        let (address, port) = socket
            .discover_ip(321, Duration::from_secs(5))
            .await
            .unwrap();
        assert_eq!(address, "127.0.0.1");
        assert!(port > 0);
    }
}
