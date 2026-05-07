"""Binary frame round-trip across the websocket-protocol envelope."""

from hivemind_bus_client.message import HiveMessage, HiveMessageType
from hivemind_bus_client.serialization import HiveMindBinaryPayloadType

from hivescope.scenarios import single_satellite


FAKE_AUDIO = b"\x00\x01" * 2048
FAKE_FILE = b"hello binary world"


def test_raw_audio_round_trip():
    b = single_satellite()
    try:
        b.start_all()
        m0 = b.get_master("M0")
        s0 = b.get_satellite("S0")

        s0.send(HiveMessage(
            HiveMessageType.BINARY,
            payload=FAKE_AUDIO,
            bin_type=HiveMindBinaryPayloadType.RAW_AUDIO,
            metadata={"sample_rate": 16000, "sample_width": 2},
        ))

        m0.binary_protocol.assert_called("microphone_input")
        call = m0.binary_protocol.last_call("microphone_input")
        assert call.data == FAKE_AUDIO
        assert call.meta["sample_rate"] == 16000
    finally:
        b.stop_all()


def test_file_payload_round_trip():
    b = single_satellite()
    try:
        b.start_all()
        m0 = b.get_master("M0")
        s0 = b.get_satellite("S0")

        s0.send(HiveMessage(
            HiveMessageType.BINARY,
            payload=FAKE_FILE,
            bin_type=HiveMindBinaryPayloadType.FILE,
            metadata={"file_name": "greeting.txt"},
        ))

        m0.binary_protocol.assert_called("receive_file")
        call = m0.binary_protocol.last_call("receive_file")
        assert call.data == FAKE_FILE
        assert call.meta["file_name"] == "greeting.txt"
    finally:
        b.stop_all()
