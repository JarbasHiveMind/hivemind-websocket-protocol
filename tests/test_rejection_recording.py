"""The rejection ring must also see connections refused before authorization.

hivemind-core keeps the last rejected connections with their reason, for the
operator to read in the admin panel. Core fills that ring from its own
handlers, and a websocket with a malformed ``authorization`` argument never
reaches one: it is closed here, before a ``HiveMindClientConnection`` exists.
Without this, an operator watching a satellite that sends a garbled
credential sees an empty ring.

The tests drive ``open()`` on a handler built with ``object.__new__``, as the
other unit tests in this suite do: the authorization branch only touches
``self.request``, ``self.application``, ``self.get_query_argument``,
``self.close`` and ``self.hm_protocol``.
"""
from unittest.mock import MagicMock

import pybase64
import pytest

import hivemind_websocket_protocol as hwp
from hivemind_websocket_protocol import HiveMindTornadoWebSocket


# Encodes to "alice:" - an empty key, which decode_auth rejects.
BAD_AUTH = pybase64.b64encode(b"alice:").decode("ascii")
GOOD_AUTH = pybase64.b64encode(b"sat:s3cr3t-key").decode("ascii")


class _StopHere(Exception):
    """Ends open() once the authorization branch is known to be passed."""


def _stop_here(*args, **kwargs):
    raise _StopHere


class _Recorder:
    """Stands in for the part of core's listener protocol used here."""

    def __init__(self):
        self.calls = []
        self.db = MagicMock()

    def record_rejection(self, client, code, reason):
        if client.rejection_recorded:
            return
        client.rejection_recorded = True
        self.calls.append({"peer": client.peer, "code": code, "reason": reason})


def _handler(auth=BAD_AUTH, *, remote_ip="10.0.0.7", hm_protocol=None):
    handler = object.__new__(HiveMindTornadoWebSocket)
    handler.source_ip = None
    handler.request = MagicMock(remote_ip=remote_ip)
    handler.application = MagicMock(settings={"trusted_networks": ()})
    handler.get_query_argument = MagicMock(return_value=auth)
    handler.close = MagicMock()
    handler.hm_protocol = hm_protocol if hm_protocol is not None else MagicMock()
    return handler


class TestInvalidAuthorizationIsRecorded:
    def test_a_bad_authorization_reaches_record_rejection(self):
        recorder = _Recorder()
        handler = _handler(hm_protocol=recorder)

        handler.open()

        assert recorder.calls == [
            {"peer": "10.0.0.7", "code": 1008, "reason": "invalid_authorization"}
        ]
        _, kwargs = handler.close.call_args
        assert kwargs.get("code") == 1008

    def test_the_peer_is_the_caller_address(self):
        recorder = _Recorder()
        handler = _handler(remote_ip="203.0.113.9", hm_protocol=recorder)

        handler.open()

        assert recorder.calls[0]["peer"] == "203.0.113.9"

    @pytest.mark.parametrize("auth", [None, "not-base64-@@@", ""])
    def test_every_shape_of_bad_authorization_is_recorded(self, auth):
        recorder = _Recorder()
        handler = _handler(auth, hm_protocol=recorder)

        handler.open()

        assert len(recorder.calls) == 1
        assert recorder.calls[0]["reason"] == "invalid_authorization"

    def test_a_good_authorization_records_nothing_here(self, monkeypatch):
        recorder = _Recorder()
        handler = _handler(GOOD_AUTH, hm_protocol=recorder)

        # Past the authorization branch open() builds a real client and needs
        # the node identity, so the build itself ends the call.
        monkeypatch.setattr(hwp, "HiveMindClientConnection", _stop_here)

        with pytest.raises(_StopHere):
            handler.open()

        assert recorder.calls == []


class TestRecordingNeverStopsTheClose:
    def test_a_core_without_the_ring_still_closes(self):
        """An older hivemind-core has no ``record_rejection``."""

        class _OldCore:
            pass

        handler = _handler(hm_protocol=_OldCore())

        handler.open()

        handler.close.assert_called_once()
        _, kwargs = handler.close.call_args
        assert kwargs.get("code") == 1008

    def test_a_failure_to_record_does_not_stop_the_close(self):
        hm_protocol = MagicMock()
        hm_protocol.record_rejection.side_effect = RuntimeError("ring is broken")
        handler = _handler(hm_protocol=hm_protocol)

        handler.open()

        handler.close.assert_called_once()
        _, kwargs = handler.close.call_args
        assert kwargs.get("code") == 1008
