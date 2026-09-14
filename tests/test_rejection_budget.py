"""A flood of free rejections must not empty the operator's ring.

The ring in hivemind-core holds the last 100 rejections of every kind. A
connection refused before authorization costs the caller nothing, so without
a limit anyone can push the rows an operator needs out of the ring with
garbage credentials. The unauthenticated kind therefore has its own budget:
at most ``UNAUTHENTICATED_REJECTION_BUDGET`` rows per window, and at most one
row per caller address in that window.

The handler is built with ``object.__new__``, as the other unit tests in this
suite do.
"""
import pytest

import hivemind_websocket_protocol as hwp
from hivemind_websocket_protocol import HiveMindTornadoWebSocket

from tests.test_rejection_recording import BAD_AUTH, _handler, _Recorder


class _Clock:
    """A monotonic clock the test moves by hand."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(hwp.time, "monotonic", c)
    return c


def _reject(recorder, ip):
    _handler(BAD_AUTH, remote_ip=ip, hm_protocol=recorder).open()


class TestOneRowPerAddressPerWindow:
    def test_a_flood_from_one_address_records_once(self, clock):
        recorder = _Recorder()

        for _ in range(50):
            _reject(recorder, "203.0.113.9")

        assert len(recorder.calls) == 1
        assert recorder.calls[0]["peer"] == "203.0.113.9"

    def test_another_address_still_records(self, clock):
        recorder = _Recorder()

        _reject(recorder, "203.0.113.9")
        _reject(recorder, "203.0.113.10")

        assert [c["peer"] for c in recorder.calls] == ["203.0.113.9", "203.0.113.10"]

    def test_the_same_address_records_again_after_the_window(self, clock):
        recorder = _Recorder()

        _reject(recorder, "203.0.113.9")
        clock.now += hwp.UNAUTHENTICATED_REJECTION_WINDOW + 1
        _reject(recorder, "203.0.113.9")

        assert len(recorder.calls) == 2


class TestTheBudgetBoundsWhatAFloodCanEvict:
    def test_a_flood_from_many_addresses_stops_at_the_budget(self, clock):
        recorder = _Recorder()

        for n in range(hwp.UNAUTHENTICATED_REJECTION_BUDGET * 5):
            _reject(recorder, f"198.51.100.{n}")

        assert len(recorder.calls) == hwp.UNAUTHENTICATED_REJECTION_BUDGET

    def test_the_address_map_does_not_grow_without_bound(self, clock):
        recorder = _Recorder()

        for n in range(60):
            _reject(recorder, f"198.51.100.{n}")
        clock.now += hwp.UNAUTHENTICATED_REJECTION_WINDOW + 1
        _reject(recorder, "203.0.113.9")

        assert HiveMindTornadoWebSocket._unauth_rejection_by_ip == {
            "203.0.113.9": clock.now
        }

    def test_the_budget_refills_after_the_window(self, clock):
        recorder = _Recorder()

        for n in range(60):
            _reject(recorder, f"198.51.100.{n}")
        clock.now += hwp.UNAUTHENTICATED_REJECTION_WINDOW + 1
        for n in range(60):
            _reject(recorder, f"192.0.2.{n}")

        assert len(recorder.calls) == hwp.UNAUTHENTICATED_REJECTION_BUDGET * 2


class TestTheCloseNeverDependsOnTheBudget:
    def test_a_refused_connection_is_still_closed_when_the_budget_is_spent(self, clock):
        recorder = _Recorder()
        for n in range(60):
            _reject(recorder, f"198.51.100.{n}")

        handler = _handler(BAD_AUTH, remote_ip="203.0.113.9", hm_protocol=recorder)
        handler.open()

        assert len(recorder.calls) == hwp.UNAUTHENTICATED_REJECTION_BUDGET
        handler.close.assert_called_once()
        _, kwargs = handler.close.call_args
        assert kwargs.get("code") == 1008

    def test_every_refused_connection_is_still_logged(self, clock, monkeypatch):
        """The WARNING that names the caller does not depend on the budget."""
        warnings = []
        monkeypatch.setattr(hwp.LOG, "warning", lambda msg, *a, **kw: warnings.append(msg))
        recorder = _Recorder()

        for _ in range(5):
            _reject(recorder, "203.0.113.9")

        assert len(recorder.calls) == 1
        assert len(warnings) == 5
        assert all("203.0.113.9" in w for w in warnings)


def test_a_core_without_the_ring_spends_no_budget(clock):
    """No row is written, so the budget must not be charged for it."""

    class _OldCore:
        pass

    for n in range(60):
        _handler(BAD_AUTH, remote_ip=f"198.51.100.{n}", hm_protocol=_OldCore()).open()

    recorder = _Recorder()
    _reject(recorder, "203.0.113.9")

    assert len(recorder.calls) == 1
