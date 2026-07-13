package vaidcord

type VoiceGatewayOpcode int

const (
	VoiceOpIdentify                    VoiceGatewayOpcode = 0
	VoiceOpSelectProtocol              VoiceGatewayOpcode = 1
	VoiceOpReady                       VoiceGatewayOpcode = 2
	VoiceOpHeartbeat                   VoiceGatewayOpcode = 3
	VoiceOpSessionDescription          VoiceGatewayOpcode = 4
	VoiceOpSpeaking                    VoiceGatewayOpcode = 5
	VoiceOpHeartbeatAck                VoiceGatewayOpcode = 6
	VoiceOpResume                      VoiceGatewayOpcode = 7
	VoiceOpHello                       VoiceGatewayOpcode = 8
	VoiceOpResumed                     VoiceGatewayOpcode = 9
	VoiceOpClientsConnect              VoiceGatewayOpcode = 11
	VoiceOpVideo                       VoiceGatewayOpcode = 12
	VoiceOpClientDisconnect            VoiceGatewayOpcode = 13
	VoiceOpDavePrepareTransition       VoiceGatewayOpcode = 21
	VoiceOpDaveExecuteTransition       VoiceGatewayOpcode = 22
	VoiceOpDaveTransitionReady         VoiceGatewayOpcode = 23
	VoiceOpDavePrepareEpoch            VoiceGatewayOpcode = 24
	VoiceOpDaveMLSExternalSender       VoiceGatewayOpcode = 25
	VoiceOpDaveMLSKeyPackage           VoiceGatewayOpcode = 26
	VoiceOpDaveMLSProposals            VoiceGatewayOpcode = 27
	VoiceOpDaveMLSCommitWelcome        VoiceGatewayOpcode = 28
	VoiceOpDaveMLSAnnounceTransition   VoiceGatewayOpcode = 29
	VoiceOpDaveMLSWelcome              VoiceGatewayOpcode = 30
	VoiceOpDaveMLSInvalidCommitWelcome VoiceGatewayOpcode = 31
)

type VoiceGatewayCloseCode int

const (
	VoiceCloseUnknownOpcode              VoiceGatewayCloseCode = 4001
	VoiceCloseDecodeError                VoiceGatewayCloseCode = 4002
	VoiceCloseNotAuthenticated           VoiceGatewayCloseCode = 4003
	VoiceCloseAuthenticationFailed       VoiceGatewayCloseCode = 4004
	VoiceCloseAlreadyAuthenticated       VoiceGatewayCloseCode = 4005
	VoiceCloseSessionNoLongerValid       VoiceGatewayCloseCode = 4006
	VoiceCloseSessionTimeout             VoiceGatewayCloseCode = 4009
	VoiceCloseServerNotFound             VoiceGatewayCloseCode = 4011
	VoiceCloseUnknownProtocol            VoiceGatewayCloseCode = 4012
	VoiceCloseDisconnected               VoiceGatewayCloseCode = 4014
	VoiceCloseVoiceServerCrashed         VoiceGatewayCloseCode = 4015
	VoiceCloseUnknownEncryptionMode      VoiceGatewayCloseCode = 4016
	VoiceCloseE2EEDaveRequired           VoiceGatewayCloseCode = 4017
	VoiceCloseBadRequest                 VoiceGatewayCloseCode = 4020
	VoiceCloseDisconnectedRateLimited    VoiceGatewayCloseCode = 4021
	VoiceCloseDisconnectedCallTerminated VoiceGatewayCloseCode = 4022
)

func (code VoiceGatewayCloseCode) ShouldReconnect() bool {
	switch code {
	case VoiceCloseDisconnected, VoiceCloseDisconnectedRateLimited, VoiceCloseDisconnectedCallTerminated:
		return false
	default:
		return true
	}
}

// VoiceCloseAction describes what to do when the voice websocket closes with
// a given code. Mirrors the Python SDK's classify_voice_close_code.
type VoiceCloseAction int

const (
	// VoiceCloseActionResume — reconnect and RESUME the voice session.
	VoiceCloseActionResume VoiceCloseAction = iota
	// VoiceCloseActionRejoin — the session is invalid; request a fresh join
	// via the main gateway (op 4) and re-identify.
	VoiceCloseActionRejoin
	// VoiceCloseActionFatal — reconnecting is pointless or forbidden.
	VoiceCloseActionFatal
)

func (a VoiceCloseAction) String() string {
	switch a {
	case VoiceCloseActionResume:
		return "resume"
	case VoiceCloseActionRejoin:
		return "rejoin"
	default:
		return "fatal"
	}
}

// ClassifyVoiceCloseCode maps a voice websocket close code to the reconnect
// policy. Pass a negative code for "closed without a code".
func ClassifyVoiceCloseCode(code int) VoiceCloseAction {
	switch code {
	case 4001, 4002, 4003, 4004, 4005, 4011, 4012, 4014, 4016, 4017:
		return VoiceCloseActionFatal
	case 4006, 4009:
		return VoiceCloseActionRejoin
	default:
		// Unknown/network-level closes (no code, 1000, 1001, 1006, 4015, …)
		// are worth a resume attempt; the server rejects it if the session
		// died.
		return VoiceCloseActionResume
	}
}

type DaveIdentifyConfig struct {
	MaxDaveProtocolVersion int `json:"max_dave_protocol_version"`
}
