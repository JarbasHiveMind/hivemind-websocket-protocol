"""Coverage for the close-diagnostics gap: tornado logs nothing when a
client goes away, so `on_close` must report the facts an operator needs -
the close code, the close reason and how old the last pong was.

It deliberately does *not* guess whether the disconnect was a
server-initiated ping-timeout eviction: tornado pings at T, waits
`ping_timeout` and only then closes, so a real eviction shows a pong age of
`ping_interval + ping_timeout - round_trip_time`, which overlaps the ages
seen on ordinary disconnects. `close_reason` cannot settle it either,
because tornado fills it in from the close frame the peer echoes back, and
a peer that timed out echoes nothing.

`ovos_utils.log.LOG` sets `propagate = False` on its underlying logger, so
`caplog`'s root-logger capture can silently miss records depending on test
order. These tests instead patch the module's cached hot-path logger
(`_RECEIVE_LOGGER`, returned by `_receive_logger()`) and assert on the calls
it receives.
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


def _logged(log):
    """The single line the handler logged, with its arguments applied."""
    assert not log.warning.called
    assert log.info.call_count == 1
    return log.info.call_args[0][0] % log.info.call_args[0][1:]


def test_on_pong_stamps_last_pong():
    handler = object.__new__(HiveMindTornadoWebSocket)
    handler.last_pong = None
    before = time.monotonic()
    handler.on_pong(b"")
    after = time.monotonic()
    assert before <= handler.last_pong <= after


def test_close_reports_code_reason_and_pong_age(monkeypatch):
    log = MagicMock()
    monkeypatch.setattr(hwp, "_RECEIVE_LOGGER", log)
    monkeypatch.setattr(hwp, "_RECEIVE_LOGGER_KEY",
                        (hwp.LOG.name, hwp.LOG.base_path))
    handler = _handler(
        last_pong=time.monotonic() - 12,
        close_code=1006,
        close_reason="abnormal closure",
    )

    handler.on_close()

    message = _logged(log)
    assert "close_code=1006" in message
    assert "close_reason=abnormal closure" in message
    assert "seconds_since_last_pong=12.0" in message
    handler.hm_protocol.handle_client_disconnected.assert_called_once_with(handler.client)


def test_a_real_ping_timeout_is_reported_with_its_pong_age(monkeypatch):
    """Tornado pings at T, sleeps `ping_timeout`, then closes, and the pong
    answering the previous ping landed one round trip after it was sent. A
    real eviction therefore shows an age of interval + timeout - rtt, which
    is what the log must report - no threshold separates it from an ordinary
    disconnect."""
    log = MagicMock()
    monkeypatch.setattr(hwp, "_RECEIVE_LOGGER", log)
    monkeypatch.setattr(hwp, "_RECEIVE_LOGGER_KEY",
                        (hwp.LOG.name, hwp.LOG.base_path))
    round_trip = 0.3
    age = DEFAULT_WEBSOCKET_PING_INTERVAL + DEFAULT_WEBSOCKET_PING_TIMEOUT - round_trip
    handler = _handler(last_pong=time.monotonic() - age)

    handler.on_close()

    assert f"seconds_since_last_pong={age:.1f}" in _logged(log)


def test_no_pong_age_ever_triggers_a_verdict(monkeypatch):
    """Every pong age, from fresh to hours old, is reported the same way:
    one factual line, never a guess about the cause."""
    for age in (0.5, 25, 49.7, 50, 120, 3600):
        log = MagicMock()
        monkeypatch.setattr(hwp, "_RECEIVE_LOGGER", log)
        monkeypatch.setattr(hwp, "_RECEIVE_LOGGER_KEY",
                            (hwp.LOG.name, hwp.LOG.base_path))
        handler = _handler(last_pong=time.monotonic() - age)

        handler.on_close()

        assert f"seconds_since_last_pong={age:.1f}" in _logged(log)


def test_client_that_never_ponged_reports_unknown_age(monkeypatch):
    log = MagicMock()
    monkeypatch.setattr(hwp, "_RECEIVE_LOGGER", log)
    monkeypatch.setattr(hwp, "_RECEIVE_LOGGER_KEY",
                        (hwp.LOG.name, hwp.LOG.base_path))
    handler = _handler(last_pong=None)

    handler.on_close()

    assert "seconds_since_last_pong=unknown" in _logged(log)


def test_on_close_never_logs_payload_or_access_key(monkeypatch):
    log = MagicMock()
    monkeypatch.setattr(hwp, "_RECEIVE_LOGGER", log)
    monkeypatch.setattr(hwp, "_RECEIVE_LOGGER_KEY",
                        (hwp.LOG.name, hwp.LOG.base_path))
    for last_pong in (time.monotonic() - 1, time.monotonic() - 3600):
        handler = _handler(last_pong=last_pong)
        handler.on_close()

    for call in log.warning.call_args_list + log.info.call_args_list:
        message = call[0][0] % call[0][1:]
        assert "s3cr3t-access-key" not in message
