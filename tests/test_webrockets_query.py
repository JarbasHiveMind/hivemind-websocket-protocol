"""Unit tests for the webrockets query-string parsing.

Every HiveMind client — the ESP32 firmware, the JS client, the python bus
client — connects to the server root with no path and carries its
credentials in the query string. These tests pin that shape down; the module
under test does not import webrockets, so they always run.
"""
import pytest

from hivemind_websocket_protocol.webrockets_backend import query_authorization


class TestQueryAuthorization:
    def test_reads_the_authorization_argument(self):
        assert query_authorization("authorization=dGVzdDp0ZXN0") == "dGVzdDp0ZXN0"

    def test_reads_it_alongside_other_arguments(self):
        assert query_authorization("foo=bar&authorization=abc&baz=1") == "abc"

    @pytest.mark.parametrize("query", [
        "",                  # a client that connected with no query string at all
        "foo=bar",
        "authorisation=abc",
        "authorization=",    # blank value, dropped by parse_qsl
    ])
    def test_missing_authorization_is_none(self, query):
        # decode_auth turns None into a rejection; parsing must not crash
        assert query_authorization(query) is None
