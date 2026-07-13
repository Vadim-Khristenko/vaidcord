//! Voice gateway opcode/close-code constants and the DAVE identify
//! configuration carrier (shared numeric contract across the three SDKs).

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u16)]
pub enum VoiceGatewayOpcode {
    Identify = 0,
    SelectProtocol = 1,
    Ready = 2,
    Heartbeat = 3,
    SessionDescription = 4,
    Speaking = 5,
    HeartbeatAck = 6,
    Resume = 7,
    Hello = 8,
    Resumed = 9,
    ClientsConnect = 11,
    ClientDisconnect = 13,
    DavePrepareTransition = 21,
    DaveExecuteTransition = 22,
    DaveTransitionReady = 23,
    DavePrepareEpoch = 24,
    DaveMlsExternalSender = 25,
    DaveMlsKeyPackage = 26,
    DaveMlsProposals = 27,
    DaveMlsCommitWelcome = 28,
    DaveMlsAnnounceCommitTransition = 29,
    DaveMlsWelcome = 30,
    DaveMlsInvalidCommitWelcome = 31,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u16)]
pub enum VoiceGatewayCloseCode {
    UnknownOpcode = 4001,
    DecodeError = 4002,
    NotAuthenticated = 4003,
    AuthenticationFailed = 4004,
    AlreadyAuthenticated = 4005,
    SessionNoLongerValid = 4006,
    SessionTimeout = 4009,
    ServerNotFound = 4011,
    UnknownProtocol = 4012,
    Disconnected = 4014,
    VoiceServerCrashed = 4015,
    UnknownEncryptionMode = 4016,
    E2eeDaveRequired = 4017,
    BadRequest = 4020,
    DisconnectedRateLimited = 4021,
    DisconnectedCallTerminated = 4022,
}

impl VoiceGatewayCloseCode {
    pub const fn should_reconnect(self) -> bool {
        !matches!(
            self,
            Self::Disconnected | Self::DisconnectedRateLimited | Self::DisconnectedCallTerminated
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct DaveIdentifyConfig {
    pub max_dave_protocol_version: u8,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dave_opcode_values_match_discord_voice_gateway() {
        assert_eq!(VoiceGatewayOpcode::DavePrepareTransition as u16, 21);
        assert_eq!(VoiceGatewayOpcode::DaveMlsWelcome as u16, 30);
    }

    #[test]
    fn voice_close_reconnect_policy_matches_python_sdk() {
        assert_eq!(VoiceGatewayCloseCode::E2eeDaveRequired as u16, 4017);
        assert!(!VoiceGatewayCloseCode::Disconnected.should_reconnect());
        assert!(VoiceGatewayCloseCode::VoiceServerCrashed.should_reconnect());
    }
}
