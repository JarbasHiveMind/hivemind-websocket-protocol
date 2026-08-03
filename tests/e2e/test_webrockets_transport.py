"""End-to-end tests over the optional webrockets transport.

Mirrors the Tornado lifecycle tests: a real HiveMindWebrocketsProtocol on a
real port, with HiveMessageBusClient connecting over the wire. The wire
protocol is the one Tornado already serves, so a stock client works unchanged
— that is the point of these tests.

Skipped when the webrockets extra is not installed.
"""
import importlib.util
import socket
import threading
import time

import pytest
from ovos_bus_client.message import Message

from hivemind_bus_client import HiveMessageBusClient
from hivemind_websocket_protocol.webrockets_backend import HiveMindWebrocketsProtocol
from hivescope.node import MasterNode

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("webrockets") is None,
    reason="webrockets extra not installed",
)

API_KEY = "test-api-key"
PASSWORD = "correct-horse-battery-staple-9$"
ALLOWED = ["recognizer_loop:utterance", "speak"]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


@pytest.fixture
def webrockets_server():
    """A started HiveMindWebrocketsProtocol; yields `(port, master)`."""
    master = MasterNode.create("M0", require_crypto=False, handshake_enabled=True)
    master.register_satellite(API_KEY, password=PASSWORD, allowed_types=ALLOWED)

    port = _free_port()
    protocol = HiveMindWebrocketsProtocol(
        config={"host": "127.0.0.1", "port": port},
        hm_protocol=master.hm_protocol,
    )
    server = protocol.build_server()
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    if not _wait(lambda: server.addr(), timeout=5.0):
        raise RuntimeError("webrockets server failed to start within 5s")
    try:
        yield port, master
    finally:
        server.stop()
        thread.join(timeout=5.0)


def _client(port, *, useragent="e2e", key=API_KEY, password=PASSWORD, **kwargs):
    c = HiveMessageBusClient(
        key=key,
        password=password,
        host="127.0.0.1",
        port=port,
        useragent=useragent,
        self_signed=False,
        compress=False,
        binarize=False,
    )
    c.connect(**kwargs)
    return c


# --- transport: connection lifecycle --------------------------------------

def test_connect_and_handshake_over_webrockets(webrockets_server):
    port, master = webrockets_server
    c = _client(port)
    try:
        assert c.handshake_event.is_set(), "handshake did not complete"
        _wait(lambda: len(master.hm_protocol.clients) == 1)
        assert len(master.hm_protocol.clients) == 1, \
            f"expected 1 client, got {list(master.hm_protocol.clients)}"
    finally:
        c.close()


def test_disconnect_releases_client_on_listener(webrockets_server):
    port, master = webrockets_server
    c = _client(port)
    _wait(lambda: len(master.hm_protocol.clients) == 1)
    c.close()
    _wait(lambda: not master.hm_protocol.clients)
    assert not master.hm_protocol.clients, \
        f"client should be gone after close, still have: {list(master.hm_protocol.clients)}"


def test_multiple_concurrent_clients(webrockets_server):
    # each client needs its own api key: protocol v3 pins the Noise static
    # pubkey of the first connection for a given key
    port, master = webrockets_server
    second_key = "test-api-key-b"
    master.register_satellite(second_key, password=PASSWORD, allowed_types=ALLOWED)
    a = _client(port, useragent="ua-a")
    b = _client(port, useragent="ua-b", key=second_key)
    try:
        _wait(lambda: len(master.hm_protocol.clients) == 2)
        assert len(master.hm_protocol.clients) == 2
    finally:
        a.close()
        b.close()


# --- transport: authorization paths --------------------------------------

def test_bad_api_key_is_rejected(webrockets_server):
    port, master = webrockets_server
    with pytest.raises(RuntimeError):
        _client(port, useragent="bad-key", key="nope-not-a-real-key",
                handshake_max_retries=2)
    _wait(lambda: not master.hm_protocol.clients)
    assert not master.hm_protocol.clients


def test_malformed_authorization_query_rejected(webrockets_server):
    """Garbage in ?authorization= must be refused during the handshake."""
    from webrockets.client import connect

    port, master = webrockets_server
    with pytest.raises(RuntimeError):
        connect(f"ws://127.0.0.1:{port}?authorization=!!!not-base64!!!", timeout=3)
    assert not master.hm_protocol.clients


def test_missing_authorization_query_rejected(webrockets_server):
    """HiveMind clients connect with no path; a bare URL carries no
    credentials and must be refused rather than admitted."""
    from webrockets.client import connect

    port, master = webrockets_server
    with pytest.raises(RuntimeError):
        connect(f"ws://127.0.0.1:{port}", timeout=3)
    assert not master.hm_protocol.clients


# --- transport: BUS message round-trip -----------------------------------

def test_bus_message_round_trip(webrockets_server):
    """A BUS message in the allowlist reaches the listener's bus_msg handler."""
    port, master = webrockets_server
    c = _client(port)
    seen = []
    original = master.hm_protocol.handle_bus_message

    def _capture(message, client_conn):
        seen.append(message)
        return original(message, client_conn)

    master.hm_protocol.handle_bus_message = _capture
    try:
        _wait(lambda: len(master.hm_protocol.clients) == 1)
        c.emit(Message("recognizer_loop:utterance",
                       {"utterances": ["hello hivemind"]}))
        _wait(lambda: bool(seen), timeout=3)
        assert seen, "listener never saw the BUS message"
        assert seen[0].payload.msg_type == "recognizer_loop:utterance"
    finally:
        master.hm_protocol.handle_bus_message = original
        c.close()
