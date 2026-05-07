"""Binary frame round-trip across the websocket-protocol envelope."""

from hivemind_bus_client.message import HiveMessage, HiveMessageType
from hivemind_bus_client.serialization import HiveMindBinaryPayloadType

from hivescope.scenarios import single_satellite


FAKE_AUDIO = b"\x00\x01" * 2048
FAKE_FILE = b"hello binary world"
FAKE_TTS = b"\xab\xcd" * 1024
LARGE_PAYLOAD = b"x" * 65_536  # 64 KiB


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


def test_stt_transcribe_round_trip():
    b = single_satellite()
    try:
        b.start_all()
        m0 = b.get_master("M0")
        s0 = b.get_satellite("S0")

        s0.send(HiveMessage(
            HiveMessageType.BINARY,
            payload=FAKE_AUDIO,
            bin_type=HiveMindBinaryPayloadType.STT_AUDIO_TRANSCRIBE,
            metadata={"sample_rate": 16000, "sample_width": 2, "lang": "en-US"},
        ))

        m0.binary_protocol.assert_called("stt_transcribe")
        call = m0.binary_protocol.last_call("stt_transcribe")
        assert call.data == FAKE_AUDIO
        assert call.meta["lang"] == "en-US"
    finally:
        b.stop_all()


def test_tts_audio_round_trip():
    b = single_satellite()
    try:
        b.start_all()
        m0 = b.get_master("M0")
        s0 = b.get_satellite("S0")

        s0.send(HiveMessage(
            HiveMessageType.BINARY,
            payload=FAKE_TTS,
            bin_type=HiveMindBinaryPayloadType.TTS_AUDIO,
            metadata={"utterance": "hello world", "lang": "en-US",
                      "file_name": "out.wav"},
        ))

        m0.binary_protocol.assert_called("receive_tts")
        call = m0.binary_protocol.last_call("receive_tts")
        assert call.data == FAKE_TTS
        assert call.meta["utterance"] == "hello world"
    finally:
        b.stop_all()


def test_large_payload_survives_round_trip():
    b = single_satellite()
    try:
        b.start_all()
        m0 = b.get_master("M0")
        s0 = b.get_satellite("S0")

        s0.send(HiveMessage(
            HiveMessageType.BINARY,
            payload=LARGE_PAYLOAD,
            bin_type=HiveMindBinaryPayloadType.FILE,
            metadata={"file_name": "big.bin"},
        ))

        call = m0.binary_protocol.last_call("receive_file")
        assert len(call.data) == len(LARGE_PAYLOAD)
        assert call.data == LARGE_PAYLOAD
    finally:
        b.stop_all()


def test_multiple_sequential_payloads_recorded():
    b = single_satellite()
    try:
        b.start_all()
        m0 = b.get_master("M0")
        s0 = b.get_satellite("S0")

        for i in range(5):
            s0.send(HiveMessage(
                HiveMessageType.BINARY,
                payload=f"chunk-{i}".encode(),
                bin_type=HiveMindBinaryPayloadType.FILE,
                metadata={"file_name": f"chunk-{i}.bin"},
            ))

        m0.binary_protocol.assert_called("receive_file", count=5)
        names = [c.meta["file_name"] for c in m0.binary_protocol.calls
                 if c.handler == "receive_file"]
        assert names == [f"chunk-{i}.bin" for i in range(5)]
    finally:
        b.stop_all()
