"""Coverage for a defect in the b64-audio log-verbosity sniff in
`_handle_inbound_message`.

After a successful `self.client.decode(message)`, the sniff accessed
`message.payload.msg_type` unconditionally for BUS messages. `HiveMessage.
payload` rebuilds a bus `Message` via `Message(self._payload["type"], ...)`
and raises `KeyError` when the inner payload dict has no `"type"` key. That
access ran outside the decode try/except and *before*
`hm_protocol.handle_message()`, where the real graceful guard
(`_payload_is_usable`/`_probe_payload` in hivemind-core) lives. So an
admitted client sending one well-formed-but-typeless BUS frame got an
unguarded `KeyError` escaping Tornado's on_message -- connection dropped,
plus a traceback in the logs -- instead of the intended `hive.policy.denied`
reply with the peer kept connected.

The sniff must be defensive: any exception while probing the payload falls
through to the normal log path, and `handle_message` is still reached so its
own guard can apply.
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


class TestB64AudioSniffGuard:
    def test_typeless_bus_payload_does_not_propagate(self, monkeypatch):
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        handler = _handler()
        typeless_bus_message = HiveMessage(
            HiveMessageType.BUS, payload={"data": {"x": 1}}
        )
        handler.client.decode = MagicMock(return_value=typeless_bus_message)

        # Must not raise - decode succeeded, so this frame is well-formed
        # enough to reach handle_message's own graceful guard.
        handler._handle_inbound_message("frame")

    def test_typeless_bus_payload_is_not_treated_as_decode_failure(self, monkeypatch):
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        handler = _handler()
        typeless_bus_message = HiveMessage(
            HiveMessageType.BUS, payload={"data": {"x": 1}}
        )
        handler.client.decode = MagicMock(return_value=typeless_bus_message)

        handler._handle_inbound_message("frame")

        # decode() succeeded, so this must not be closed with the 1008
        # "invalid message" code the decode-failure path uses.
        handler.close.assert_not_called()

    def test_typeless_bus_payload_reaches_handle_message(self, monkeypatch):
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        handler = _handler()
        typeless_bus_message = HiveMessage(
            HiveMessageType.BUS, payload={"data": {"x": 1}}
        )
        handler.client.decode = MagicMock(return_value=typeless_bus_message)

        handler._handle_inbound_message("frame")

        # The graceful guard (_payload_is_usable/_probe_payload) lives in
        # hm_protocol.handle_message - it must actually be reached so it can
        # reply hive.policy.denied and keep the peer connected.
        handler.hm_protocol.handle_message.assert_called_once_with(
            typeless_bus_message, handler.client
        )
