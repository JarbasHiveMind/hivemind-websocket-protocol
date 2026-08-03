"""Unit tests for the admission logic shared by every backend.

Both the Tornado backend and the webrockets backend go through
`_admission`, so this is the single place that defines who gets in.
"""
import pybase64
import pytest

from hivemind_websocket_protocol import HiveMindTornadoWebSocket
from hivemind_websocket_protocol._admission import decode_auth


def _encode(s: str) -> str:
    return pybase64.b64encode(s.encode("utf-8")).decode("ascii")


class TestSharedDecodeAuth:
    def test_tornado_reuses_the_shared_decoder(self):
        # the handler must not grow a second definition of the credential format
        assert HiveMindTornadoWebSocket.decode_auth is decode_auth

    def test_simple_name_and_key(self):
        assert decode_auth(_encode("alice:secret")) == ("alice", "secret")

    @pytest.mark.parametrize("bad", [None, "", "not_base64!@#", _encode("alice:")])
    def test_rejects_malformed(self, bad):
        with pytest.raises((ValueError, UnicodeDecodeError)):
            decode_auth(bad)
