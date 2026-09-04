"""Combined real-socket proof for transparent multi-frame Noise chunking.

The #45 regression: a HiveMessage larger than the Noise 65535-byte per-message
limit (e.g. >~2s of base64 STT audio) hard-failed on the v3 Noise path with
``NoiseInvalidMessage``. This test stands up the real Tornado WebSocket hub,
connects a real v3 client that completes a Noise handshake, and round-trips a
~300KB base64 audio-shaped bus message end to end over the socket. It must
transmit (split into several Noise transport messages) and arrive intact.
"""
import os
import time

import pybase64
from ovos_bus_client.message import Message

from hivemind_bus_client import HiveMessageBusClient


def _client(server):
    c = HiveMessageBusClient(
        key=server.api_key, password=server.password,
        host=server.host, port=server.port,
        useragent="chunk-e2e", self_signed=False,
        compress=False, binarize=False,
    )
    c.connect()
    assert c.handshake_event.is_set(), "handshake did not complete"
    return c


def test_large_b64_audio_round_trips_over_real_noise_socket(tornado_server):
    c = _client(tornado_server)
    # this is the real regression path: a v3 Noise session must be active
    assert c.noise_transport is not None, "expected a v3 Noise session"

    seen = []
    original = tornado_server.listener.handle_bus_message

    def _capture(message, client):
        seen.append(message)
        return original(message, client)

    tornado_server.listener.handle_bus_message = _capture

    # ~300KB of base64 — comfortably over the single-frame Noise limit, the
    # size of a couple of seconds of STT audio (the actual #45 payload)
    audio_b64 = pybase64.b64encode(os.urandom(225_000)).decode("ascii")
    assert len(audio_b64) > 65_535, "test payload must exceed the Noise limit"

    try:
        c.emit(Message("recognizer_loop:b64_audio", {"audio": audio_b64}))
        deadline = time.monotonic() + 10
        while not seen and time.monotonic() < deadline:
            time.sleep(0.05)
        assert seen, "large message never arrived at the listener"
        got = seen[0]
        assert got.payload.msg_type == "recognizer_loop:b64_audio"
        assert got.payload.data["audio"] == audio_b64, \
            "reassembled audio payload does not match what was sent"
    finally:
        tornado_server.listener.handle_bus_message = original
        c.close()
