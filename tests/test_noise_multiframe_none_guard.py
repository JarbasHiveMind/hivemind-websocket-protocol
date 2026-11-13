"""Unit coverage for wsproto's own contribution to multi-frame Noise chunking
(HiveMind-voice-relay#45): the ``None``-guard in ``_handle_inbound_message``.

Protocol-v3 Noise sessions split a HiveMessage that exceeds the Noise
per-message limit across several transport frames. While reassembly is in
progress, ``self.client.decode()`` (which drives the connection's
``noise_transport.decrypt_frame``) returns ``None`` instead of a complete
``HiveMessage`` -- there is nothing to dispatch yet, and the frame must be
silently absorbed rather than crash on ``message.msg_type`` or reach
``hm_protocol.handle_message``.

This test exercises only that guard. It does not depend on hivemind-core
actually reassembling anything -- the full real-socket round trip for a
large base64 payload requires core's reassembly support (core#311) and is
proven there, not in wsproto's own CI.
"""
from unittest.mock import MagicMock

from hivemind_bus_client.message import HiveMessage, HiveMessageType
from hivemind_core.protocol import HiveMindClientConnection

from hivemind_websocket_protocol import HiveMindTornadoWebSocket
import hivemind_websocket_protocol as hwp


def _handler():
    """A bare handler instance, bypassing Tornado's HTTP/websocket setup."""
    handler = object.__new__(HiveMindTornadoWebSocket)
    handler.source_ip = None
    handler.hm_protocol = MagicMock()
    handler.client = HiveMindClientConnection(
        key="s3cr3t-access-key",
        send_msg=lambda *a: None,
        disconnect=lambda *a, **k: None,
        name="e2e",
        handshake=MagicMock(),
    )
    handler.close = MagicMock()
    return handler


class TestNoiseMultiframeNoneGuard:
    def test_in_progress_chunk_is_not_dispatched(self, monkeypatch):
        """decrypt_frame (via decode) returning None must not reach
        hm_protocol.handle_message -- there is no complete message yet."""
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        handler = _handler()
        # simulate a v3 Noise segment that only advanced an in-progress
        # multi-frame reassembly: client.decode() -> noise_transport
        # .decrypt_frame() returns None
        handler.client.decode = MagicMock(return_value=None)

        # must not raise (no message.msg_type access on None) and must not
        # dispatch anything
        handler._handle_inbound_message("frame")

        handler.hm_protocol.handle_message.assert_not_called()

    def test_in_progress_chunk_is_not_treated_as_decode_failure(self, monkeypatch):
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        handler = _handler()
        handler.client.decode = MagicMock(return_value=None)

        handler._handle_inbound_message("frame")

        # decode() succeeded (just produced no complete message yet), so this
        # must not be closed with the 1008 "invalid message" code the
        # decode-failure path uses.
        handler.close.assert_not_called()

    def test_complete_message_is_dispatched_normally(self, monkeypatch):
        """Once decode() returns a real payload (the final chunk completed
        reassembly, or an ordinary unchunked message), dispatch proceeds as
        usual -- the None-guard must not swallow real messages."""
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        handler = _handler()
        complete_message = HiveMessage(
            HiveMessageType.BUS,
            payload={"type": "recognizer_loop:b64_audio", "data": {"audio": "abc"}},
        )
        handler.client.decode = MagicMock(return_value=complete_message)

        handler._handle_inbound_message("frame")

        handler.hm_protocol.handle_message.assert_called_once_with(
            complete_message, handler.client
        )
