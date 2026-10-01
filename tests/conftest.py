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


def pytest_configure(config):
    """Register hivescope's fixtures when hivescope is installed.

    This used to be ``pytest_plugins`` in a ``conftest.py`` at the repository
    ROOT. pytest accepts that key only in a top-level conftest, and a conftest
    at the root puts the root on ``sys.path``, which shadows the installed
    wheel with the working tree. ``import_plugin`` does the same registration
    from here, and the try/except keeps the old contract: a workflow that does
    not install hivescope still runs the unit cells.
    """
    try:
        import hivescope  # noqa: F401
    except ImportError:
        return
    config.pluginmanager.import_plugin("hivescope.pytest_fixtures")
