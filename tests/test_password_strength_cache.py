"""Admission must not re-run zxcvbn for every connecting satellite.

``PasswordHandShake`` validates the credential on construction, and Core builds
one per admission on the single Tornado IOLoop. Validating the same password
400 times costs ~0.87 s of event loop that no satellite can use.
"""
import threading
from unittest.mock import patch

import pytest
from poorman_handshake import WeakPasswordError

import hivemind_websocket_protocol as hwp

STRONG = "correct-horse-battery-staple-9271"


@pytest.fixture(autouse=True)
def _clear_cache():
    hwp._PASSWORD_STRENGTH_CACHE.clear()
    yield
    hwp._PASSWORD_STRENGTH_CACHE.clear()


def test_repeated_admissions_validate_once():
    with patch.object(hwp, "check_password_strength") as check:
        for _ in range(400):
            hwp._password_handshake(STRONG, min_bits=64)

    assert check.call_count == 1, (
        "each admission re-ran the strength check; a reconnecting fleet pays "
        "this on the IOLoop"
    )


def test_handshake_is_not_shared_between_connections():
    """Only the verdict is cached — handshake state is per connection."""
    first = hwp._password_handshake(STRONG, min_bits=64)
    second = hwp._password_handshake(STRONG, min_bits=64)

    assert first is not second


def test_weak_password_is_rejected_every_time():
    """A rejection must never be remembered as a pass."""
    for _ in range(3):
        with pytest.raises(WeakPasswordError):
            hwp._password_handshake("123456", min_bits=64)

    assert len(hwp._PASSWORD_STRENGTH_CACHE) == 0


def test_a_tightened_policy_revalidates():
    hwp._password_handshake(STRONG, min_bits=40)

    with patch.object(hwp, "check_password_strength") as check:
        hwp._password_handshake(STRONG, min_bits=64)

    assert check.call_count == 1, "min_bits is part of the cache key"


def test_a_rotated_password_revalidates():
    hwp._password_handshake(STRONG, min_bits=64)

    with patch.object(hwp, "check_password_strength") as check:
        hwp._password_handshake(STRONG + "-rotated", min_bits=64)

    assert check.call_count == 1


def test_disabled_policy_does_not_validate_or_cache():
    with patch.object(hwp, "check_password_strength") as check:
        hwp._password_handshake(STRONG, min_bits=0)

    assert check.call_count == 0
    assert len(hwp._PASSWORD_STRENGTH_CACHE) == 0


def test_cache_is_bounded():
    limit = hwp._PASSWORD_STRENGTH_CACHE_SIZE
    with patch.object(hwp, "check_password_strength"):
        for i in range(limit + 50):
            hwp._password_handshake(f"{STRONG}-{i}", min_bits=64)

    assert len(hwp._PASSWORD_STRENGTH_CACHE) <= limit


def test_concurrent_admissions_are_safe():
    """Admission runs from Tornado's loop and executor threads alike."""
    errors = []

    def admit():
        try:
            for _ in range(50):
                hwp._password_handshake(STRONG, min_bits=64)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=admit) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
