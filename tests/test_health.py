"""Tests for the process-local listener health contract."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from tornado import web
from tornado.testing import AsyncHTTPTestCase

from hivemind_websocket_protocol.health import (
    LOCAL_HEALTH_PATH,
    HiveMindWebApplication,
    LocalHealthHandler,
    _is_loopback_address,
)


class TestLocalHealthHandler(AsyncHTTPTestCase):
    def get_app(self) -> HiveMindWebApplication:
        return HiveMindWebApplication([(LOCAL_HEALTH_PATH, LocalHealthHandler)])

    def test_local_health_is_bodyless_and_quiet(self) -> None:
        with patch.object(web.Application, "log_request") as inherited_logger:
            response = self.fetch(LOCAL_HEALTH_PATH)

        assert response.code == 204
        assert response.body == b""
        assert response.headers["Cache-Control"] == "no-store"
        inherited_logger.assert_not_called()

    def test_forwarded_headers_do_not_grant_access(self) -> None:
        """Access is decided by the socket peer, never by a header.

        Tornado only rewrites ``remote_ip`` from X-Forwarded-For when the
        server is built with ``xheaders=True``, and the listener does not
        enable it. This pins that: if the check is ever rewired to a
        header-derived address (``resolve_client_ip``, say) the endpoint
        becomes reachable from off-box, and nothing else in the suite
        would notice.
        """
        response = self.fetch(
            LOCAL_HEALTH_PATH,
            headers={"X-Forwarded-For": "203.0.113.9", "X-Real-IP": "203.0.113.9"},
        )
        assert response.code == 204


def _handler_with_peer(remote_ip: str) -> LocalHealthHandler:
    """A handler bound to nothing but a request carrying ``remote_ip``."""
    handler = LocalHealthHandler.__new__(LocalHealthHandler)
    handler.request = SimpleNamespace(remote_ip=remote_ip)
    return handler


def test_non_loopback_peer_is_refused() -> None:
    with pytest.raises(web.HTTPError) as excinfo:
        _handler_with_peer("203.0.113.9").prepare()
    # 404, not 403: a refused caller must not learn the endpoint exists.
    assert excinfo.value.status_code == 404


def test_loopback_peer_is_admitted() -> None:
    assert _handler_with_peer("127.0.0.1").prepare() is None


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("127.0.0.1", True),
        ("127.255.255.254", True),
        ("::1", True),
        ("10.42.0.1", False),
        ("2001:db8::1", False),
        ("not-an-address", False),
        (None, False),
    ],
)
def test_loopback_address_validation(address: object, expected: bool) -> None:
    assert _is_loopback_address(address) is expected
