"""The websocket receive path must not pay for logging it discards.

``LOG.debug``/``LOG.info`` walk ``inspect.stack()`` on every call to label the
record with the caller, *before* the level is consulted, so a dropped DEBUG
record costs as much as an emitted one. ``_handle_inbound_message`` runs on the
single Tornado IOLoop that serves every connected satellite, so anything it
pays there is paid again by every other peer on the node.
"""
import logging
from types import SimpleNamespace

import pytest
from ovos_utils.log import LOG

import hivemind_websocket_protocol as hwp
from hivemind_websocket_protocol import HiveMindTornadoWebSocket


class _CountingMessage:
    """Stands in for a HiveMessage, whose ``__str__`` serializes to JSON."""

    def __init__(self):
        self.msg_type = "bus"
        self.payload = SimpleNamespace(msg_type="recognizer_loop:utterance")
        self.renders = 0

    def __str__(self):
        self.renders += 1
        return '{"msg_type": "bus", "payload": "secret utterance"}'


@pytest.fixture
def handler():
    """A handler wired up just enough to run ``_handle_inbound_message``."""
    h = HiveMindTornadoWebSocket.__new__(HiveMindTornadoWebSocket)
    h.source_ip = "127.0.0.1"
    h.hm_protocol = SimpleNamespace(handle_message=lambda msg, client: None)
    return h


@pytest.fixture(autouse=True)
def _reset_receive_logger():
    """Drop the cached logger so each test resolves its own."""
    hwp._RECEIVE_LOGGER = None
    yield
    hwp._RECEIVE_LOGGER = None


def _deliver(handler, message):
    handler.client = SimpleNamespace(decode=lambda raw: message, peer="tcp4:peer")
    handler._handle_inbound_message("raw-frame")


def test_payload_not_rendered_when_debug_is_disabled(handler):
    """At INFO the envelope is never serialized — that is the whole point."""
    hwp._receive_logger().setLevel(logging.INFO)
    message = _CountingMessage()

    _deliver(handler, message)

    assert message.renders == 0, (
        "the inbound envelope was serialized for a DEBUG record that was "
        "discarded; pass it as a lazy argument instead of formatting it"
    )


def test_payload_is_still_rendered_when_debug_is_enabled(handler):
    """Laziness must not cost the operator the debug output itself."""
    hwp._receive_logger().setLevel(logging.DEBUG)
    message = _CountingMessage()

    _deliver(handler, message)

    # ">= 1" not "== 1": every attached handler formats the record, and pytest
    # adds its own capture handlers on top of the stdout one.
    assert message.renders >= 1


def test_b64_audio_frames_are_not_rendered(handler):
    """Audio frames are already special-cased; keep them that way."""
    hwp._receive_logger().setLevel(logging.DEBUG)
    message = _CountingMessage()
    message.payload = SimpleNamespace(msg_type="recognizer_loop:b64_audio")

    _deliver(handler, message)

    assert message.renders == 0


def test_receive_logger_is_resolved_once(handler):
    """One stack walk per process, not one per inbound frame."""
    assert hwp._receive_logger() is hwp._receive_logger()


def test_receive_logger_follows_log_set_level():
    """Caching must not pin the level: LOG.init/set_level still retargets it."""
    log = hwp._receive_logger()
    assert log.name in LOG._loggers, (
        "the receive logger must be registered with LOG so set_level reaches it"
    )
    previous = LOG.level
    try:
        LOG.set_level("DEBUG")
        assert log.level == logging.DEBUG
        LOG.set_level("WARNING")
        assert log.level == logging.WARNING
    finally:
        LOG.set_level(previous)
