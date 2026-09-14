"""Coverage for two credential/payload-leak defects:

1. `_handle_inbound_message` called `self.client.decode(message)` with no
   try/except. `decode()` can raise (NoiseTransportFailed,
   json.JSONDecodeError, TypeError, decrypt failures,
   UnencryptedMessageError, ...) for a frame that may itself be ciphertext
   or otherwise sensitive. An unguarded raise propagates out of Tornado's
   on_message and gets logged with a full traceback, which can include
   frame/payload content. It must instead be caught, close the connection
   with 1008, and log only the exception class name.

2. `open()`'s failed-authorization handler logged `raw={auth!r}` - the raw
   base64 blob, which decodes to `name:secret_key`. That is a credential
   logged in plaintext-recoverable form. It must log only a non-sensitive
   descriptor (length) instead.

`ovos_utils.log.LOG` sets `propagate = False` on its underlying logger, so
these tests patch `hivemind_websocket_protocol.LOG` directly, mirroring
tests/test_close_diagnostics.py.
"""
from unittest.mock import MagicMock

import pybase64
import pytest

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


def _all_logged_messages(log):
    messages = []
    for call in (
        log.warning.call_args_list
        + log.info.call_args_list
        + log.debug.call_args_list
        + log.exception.call_args_list
    ):
        args = call[0]
        if not args:
            continue
        try:
            messages.append(args[0] % args[1:] if len(args) > 1 else args[0])
        except TypeError:
            messages.append(str(args))
    return messages


class TestDecodeGuard:
    def test_decode_failure_does_not_propagate(self, monkeypatch):
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        handler = _handler()
        sensitive_payload = "SUPER-SECRET-CIPHERTEXT-abc123"
        handler.client.decode = MagicMock(
            side_effect=ValueError(f"bad frame: {sensitive_payload}")
        )

        # Must not raise - this is what previously escaped out of
        # Tornado's on_message.
        handler._handle_inbound_message(sensitive_payload)

    def test_decode_failure_closes_with_1008(self, monkeypatch):
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        handler = _handler()
        handler.client.decode = MagicMock(side_effect=ValueError("boom"))

        handler._handle_inbound_message("whatever")

        handler.close.assert_called_once()
        _, kwargs = handler.close.call_args
        assert kwargs.get("code") == 1008

    def test_decode_failure_logs_exception_class_but_not_payload(self, monkeypatch):
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        handler = _handler()
        sensitive_payload = "SUPER-SECRET-CIPHERTEXT-abc123"
        handler.client.decode = MagicMock(
            side_effect=ValueError(f"bad frame: {sensitive_payload}")
        )

        handler._handle_inbound_message(sensitive_payload)

        messages = _all_logged_messages(log)
        assert any("ValueError" in m for m in messages)
        assert not any(sensitive_payload in m for m in messages)

    def test_decode_success_is_unaffected(self, monkeypatch):
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        handler = _handler()
        decoded = MagicMock()
        decoded.msg_type = "not_b64_audio"
        decoded.payload.msg_type = "speak"
        handler.client.decode = MagicMock(return_value=decoded)

        handler._handle_inbound_message("frame")

        handler.close.assert_not_called()
        handler.hm_protocol.handle_message.assert_called_once_with(decoded, handler.client)


class TestAuthFailureLog:
    def _open_handler(self, auth):
        handler = object.__new__(HiveMindTornadoWebSocket)
        handler.source_ip = None
        handler.request = MagicMock(remote_ip="127.0.0.1")
        handler.application = MagicMock(settings={
            "trusted_networks": (),
        })
        handler.get_query_argument = MagicMock(return_value=auth)
        handler.close = MagicMock()
        return handler

    def test_failed_auth_does_not_log_raw_blob(self, monkeypatch):
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        # Encodes to "alice:" - empty key, rejected by decode_auth, but the
        # base64 blob itself is the thing that must never be logged.
        auth = pybase64.b64encode(b"alice:").decode("ascii")
        handler = self._open_handler(auth)

        handler.open()

        messages = _all_logged_messages(log)
        assert any("bad authorization" in m for m in messages)
        assert not any(auth in m for m in messages)
        handler.close.assert_called_once()
        _, kwargs = handler.close.call_args
        assert kwargs.get("code") == 1008

    def test_failed_auth_log_still_carries_a_length_descriptor(self, monkeypatch):
        log = MagicMock()
        monkeypatch.setattr(hwp, "LOG", log)
        auth = pybase64.b64encode(b"alice:").decode("ascii")
        handler = self._open_handler(auth)

        handler.open()

        messages = _all_logged_messages(log)
        assert any(f"len={len(auth)}" in m for m in messages)
