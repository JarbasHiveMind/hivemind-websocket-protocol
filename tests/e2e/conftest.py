"""Shared fixtures for end-to-end tests."""
import pytest

from hivescope.scenarios import single_satellite


@pytest.fixture
def hive():
    """A started single-satellite topology; teardown is automatic.

    Yields a tuple `(master, satellite)` for the common M0/S0 pair.
    Tests that need direct access to the builder can request `hive_builder`.
    """
    builder = single_satellite()
    try:
        builder.start_all()
        yield builder.get_master("M0"), builder.get_satellite("S0")
    finally:
        builder.stop_all()


@pytest.fixture
def hive_builder():
    """Like `hive` but yields the raw builder for tests with custom needs."""
    builder = single_satellite()
    try:
        builder.start_all()
        yield builder
    finally:
        builder.stop_all()
