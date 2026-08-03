"""Coverage for the close-diagnostics gap: `on_close` must say *why* a
client went away, distinguishing a server-initiated ping-timeout eviction
(tornado never logs this itself) from an ordinary clean disconnect.

`ovos_utils.log.LOG` sets `propagate = False` on its underlying logger, so
`caplog`'s root-logger capture can silently miss records depending on test
order. These tests instead patch `hivemind_websocket_protocol.LOG` directly
and assert on the calls it receives.
"""
import time
from unittest.mock import MagicMock

from hivemind_core.protocol import HiveMindClientConnection
from hivemind_websocket_protocol import (
    DEFAULT_WEBSOCKET_PING_INTERVAL,
    DEFAULT_WEBSOCKET_PING_TIMEOUT,
    HiveMindTornadoWebSocket,
)
import hivemind_websocket_protocol as hwp


def _handler(*, last_pong, ping_timeout=DEFAULT_WEBSOCKET_PING_TIMEOUT,
             ping_interval=DEFAULT_WEBSOCKET_PING_INTERVAL,
             close_code=1000, close_reason=None):
    """A bare handler instance, bypassing Tornado's HTTP/websocket setup.

    `on_close` only touches `self.client`, `self.settings`, `self.close_code`,
    `self.close_reason` and `self.last_pong` — none of which require a real
    request/application, so constructing one directly keeps these tests fast
    and independent of the e2e Tornado fixtures.
    """
    handler = object.__new__(HiveMindTornadoWebSocket)
    handler.source_ip = None
    handler.last_pong = last_pong
    handler.application = MagicMock(settings={
        "websocket_ping_timeout": ping_timeout,
        "websocket_ping_interval": ping_interval,
    })
    handler.close_code = close_code
    handler.close_reason = close_reason
    handler.hm_protocol = MagicMock()
    handler.client = HiveMindClientConnection(
        key="s3cr3t-access-key",
        send_msg=lambda *a: None,
        disconnect=lambda: None,
        name="e2e",
        handshake=MagicMock(),
    )
    return handler


def test_on_pong_stamps_last_pong():
    handler = object.__new__(HiveMindTornadoWebSocket)
    handler.last_pong = None
    before = time.monotonic()
    handler.on_pong(b"")
    after = time.monotonic()
    assert before <= handler.last_pong <= after


def test_stale_pong_logs_warning_and_names_the_timeout(monkeypatch):
    log = MagicMock()
    monkeypatch.setattr(hwp, "LOG", log)
    ping_interval = 30.0
    ping_timeout = 20.0
    handler = _handler(
        # older than one full ping_interval + ping_timeout: a genuinely stale
        # pong, i.e. the server really did stop hearing back from the client.
        last_pong=time.monotonic() - (ping_interval + ping_timeout + 5),
        ping_interval=ping_interval,
        ping_timeout=ping_timeout,
    )

    handler.on_close()

    assert log.warning.call_count == 1
    assert not log.info.called
    message = log.warning.call_args[0][0] % log.warning.call_args[0][1:]
    assert "ping timeout" in message
    handler.hm_protocol.handle_client_disconnected.assert_called_once_with(handler.client)


def test_clean_disconnect_at_25s_does_not_warn(monkeypatch):
    """Regression for the false-positive bug: with the tornado defaults
    (ping_interval=30, ping_timeout=20) a client that was pinged at t=0 and
    voluntarily disconnects at t=25 has since_pong=25 > ping_timeout=20, but
    that gap is fully explained by the ping cadence — it is not a timeout.
    """
    log = MagicMock()
    monkeypatch.setattr(hwp, "LOG", log)
    handler = _handler(
        last_pong=time.monotonic() - 25,
        ping_interval=DEFAULT_WEBSOCKET_PING_INTERVAL,
        ping_timeout=DEFAULT_WEBSOCKET_PING_TIMEOUT,
    )

    handler.on_close()

    assert not log.warning.called
    assert log.info.call_count == 1


def test_pings_disabled_never_warns(monkeypatch):
    """With ping_interval=0, tornado never pings and last_pong is frozen at
    whatever `open()` set it to, so its age carries no information about the
    disconnect and must never trigger the ping-timeout warning."""
    log = MagicMock()
    monkeypatch.setattr(hwp, "LOG", log)
    handler = _handler(
        last_pong=time.monotonic() - 3600,
        ping_interval=0,
        ping_timeout=DEFAULT_WEBSOCKET_PING_TIMEOUT,
    )

    handler.on_close()

    assert not log.warning.called
    assert log.info.call_count == 1


def test_recent_pong_stays_info(monkeypatch):
    log = MagicMock()
    monkeypatch.setattr(hwp, "LOG", log)
    ping_timeout = 20.0
    handler = _handler(
        last_pong=time.monotonic() - 1,
        ping_timeout=ping_timeout,
    )

    handler.on_close()

    assert not log.warning.called
    assert log.info.call_count == 1
    message = log.info.call_args[0][0] % log.info.call_args[0][1:]
    assert "disconnecting client" in message
    handler.hm_protocol.handle_client_disconnected.assert_called_once_with(handler.client)


def test_on_close_never_logs_payload_or_access_key(monkeypatch):
    log = MagicMock()
    monkeypatch.setattr(hwp, "LOG", log)
    ping_timeout = 20.0
    for last_pong in (time.monotonic() - 1, time.monotonic() - (ping_timeout + 5)):
        handler = _handler(last_pong=last_pong, ping_timeout=ping_timeout)
        handler.on_close()

    for call in log.warning.call_args_list + log.info.call_args_list:
        message = call[0][0] % call[0][1:]
        assert "s3cr3t-access-key" not in message
