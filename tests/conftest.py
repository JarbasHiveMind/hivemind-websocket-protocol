"""Shared fixtures for the websocket-protocol suite."""
import pytest

from hivemind_websocket_protocol import HiveMindTornadoWebSocket


@pytest.fixture(autouse=True)
def clear_unauthenticated_rejection_budget():
    """Give every test the full pre-authorization rejection budget.

    The budget is class state on the handler, because the ring it protects is
    shared too. Without this, one test spends the budget of the next.
    """
    HiveMindTornadoWebSocket._unauth_rejections.clear()
    HiveMindTornadoWebSocket._unauth_rejection_by_ip.clear()
    yield
