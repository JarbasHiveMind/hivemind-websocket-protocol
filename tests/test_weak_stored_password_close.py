"""A stored password below the strength floor must close with a reason.

``open()`` builds the v3 pre-shared key from the stored credential. When that
credential fails the strength policy, ``WeakPasswordError`` used to escape
``open()``: Tornado tore the socket down with no close reason, which a client
cannot tell from a crash and so retries forever. It now closes with 1008 and
says why, and it does not count against the client (the client sent valid
credentials; the operator's stored record is what failed policy).
"""
from unittest.mock import MagicMock, patch

import hivemind_websocket_protocol as hwp
from hivemind_websocket_protocol import HiveMindTornadoWebSocket

WEAK = "123456"
STRONG = "correct-horse-battery-staple-9271"


def _handler(user):
    handler = object.__new__(HiveMindTornadoWebSocket)
    handler.request = MagicMock(remote_ip="203.0.113.7")
    handler.get_query_argument = lambda name, default=None: "ignored"
    handler.decode_auth = lambda auth: ("test-agent", "access-key")
    handler._client_ip = lambda: "203.0.113.7"
    handler.hm_protocol = MagicMock()
    handler.hm_protocol.db.get_client_by_api_key.return_value = user
    handler.loop = MagicMock()
    handler.close = MagicMock()
    return handler


def _user(password):
    user = MagicMock()
    user.password = password
    user.client_id = 1
    user.name = "kitchen"
    return user


def test_weak_stored_password_closes_1008_with_a_reason():
    handler = _handler(_user(WEAK))
    hwp._PASSWORD_STRENGTH_CACHE.clear()
    with patch.object(hwp, "runtime_password_min_bits", return_value=64):
        handler.open()

    handler.close.assert_called_once_with(
        code=1008, reason="password below strength policy"
    )
    handler.hm_protocol.handle_new_client.assert_not_called()


def test_weak_stored_password_is_not_a_bad_key():
    handler = _handler(_user(WEAK))
    hwp._PASSWORD_STRENGTH_CACHE.clear()
    with patch.object(hwp, "runtime_password_min_bits", return_value=64):
        handler.open()

    handler.hm_protocol.handle_invalid_key_connected.assert_not_called()


def test_the_password_is_never_logged():
    handler = _handler(_user(WEAK))
    hwp._PASSWORD_STRENGTH_CACHE.clear()
    with patch.object(hwp, "runtime_password_min_bits", return_value=64), \
            patch.object(hwp, "LOG") as log:
        handler.open()

    logged = " ".join(str(call) for call in log.method_calls)
    assert logged, "the rejection should be logged"
    assert WEAK not in logged


def test_strong_stored_password_still_admits():
    handler = _handler(_user(STRONG))
    hwp._PASSWORD_STRENGTH_CACHE.clear()
    with patch.object(hwp, "runtime_password_min_bits", return_value=64):
        handler.open()

    handler.close.assert_not_called()
    handler.hm_protocol.handle_new_client.assert_called_once()
