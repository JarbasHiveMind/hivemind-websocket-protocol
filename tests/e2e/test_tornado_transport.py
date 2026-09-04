"""End-to-end tests over the *real* Tornado WebSocket transport.

The `tornado_server` fixture spins up HiveMindWebsocketProtocol on a real
port; `HiveMessageBusClient` connects to it over WebSocket. Anything that
asserts behaviour of the transport itself (auth, frames over the wire,
on_close cleanup, query-string parsing) belongs here.
"""
import time

import pybase64
import pytest
import websocket as ws_client
from ovos_bus_client.message import Message

from hivemind_bus_client import HiveMessageBusClient


# --- helpers --------------------------------------------------------------

def _client(server, *, useragent="e2e", password=None, key=None):
    c = HiveMessageBusClient(
        key=key or server.api_key,
        password=password if password is not None else server.password,
        host=server.host,
        port=server.port,
        useragent=useragent,
        self_signed=False,
        compress=False,
        binarize=False,
    )
    c.connect()
    assert c.handshake_event.is_set(), "handshake did not complete"
    return c


def _wait(predicate, timeout=3.0, interval=0.05):
    """Poll until predicate() is truthy or timeout. Returns final value."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return predicate()


def _wait_clients(server, expected, timeout=3.0):
    _wait(lambda: len(server.listener.clients) == expected, timeout=timeout)
    return server.listener.clients


# --- transport: connection lifecycle --------------------------------------

def test_connect_and_handshake_over_real_websocket(tornado_server):
    c = _client(tornado_server)
    try:
        clients = _wait_clients(tornado_server, 1)
        assert len(clients) == 1, f"expected 1 client, got {list(clients)}"
    finally:
        c.close()


def test_disconnect_releases_client_on_listener(tornado_server):
    c = _client(tornado_server)
    _wait_clients(tornado_server, 1)
    c.close()
    _wait(lambda: not tornado_server.listener.clients, timeout=3)
    assert not tornado_server.listener.clients, \
        f"client should be gone after close, still have: {list(tornado_server.listener.clients)}"


def test_multiple_concurrent_clients(tornado_server):
    # each client needs its own api key: protocol v3 pins the Noise static
    # pubkey of the first connection for a given key, so a second client
    # sharing the same key would be rejected as an impostor
    second_key = "test-api-key-b"
    tornado_server.master.register_satellite(
        second_key,
        password=tornado_server.password,
        allowed_types=[
            "recognizer_loop:utterance",
            "recognizer_loop:b64_audio",
            "speak",
        ],
    )
    a = _client(tornado_server, useragent="ua-a")
    b = _client(tornado_server, useragent="ua-b", key=second_key)
    try:
        _wait_clients(tornado_server, 2)
        assert len(tornado_server.listener.clients) == 2
    finally:
        a.close()
        b.close()


# --- transport: authorization paths --------------------------------------

def test_bad_api_key_is_rejected(tornado_server):
    """Wrong API key: server accepts the socket but never completes handshake."""
    bad = HiveMessageBusClient(
        key="nope-not-a-real-key",
        password=tornado_server.password,
        host=tornado_server.host,
        port=tornado_server.port,
        useragent="bad-key",
        self_signed=False,
    )
    # bound the handshake retries so a rejected key fails fast instead of
    # reconnecting forever.
    #
    # Accept either exception: hivemind-bus-client used to surface a refused
    # key as a bare RuntimeError, and now raises ConnectionRefusedError from
    # _is_auth_rejection so a satellite can tell "wrong credentials, stop" from
    # "connection dropped, retry". ConnectionRefusedError is an OSError, not a
    # RuntimeError, so pinning either one alone breaks against the other half
    # of the supported client range.
    with pytest.raises((RuntimeError, ConnectionRefusedError)):
        bad.connect(handshake_max_retries=2)
    bad.close()
    _wait(lambda: not tornado_server.listener.clients, timeout=2)
    assert not tornado_server.listener.clients


def test_a_refused_api_key_closes_with_1008_and_says_why(tornado_server):
    """A wrong key must be distinguishable from a network drop.

    A bare close looks exactly like the connection dropping, so a satellite
    treats a permanently invalid key as a transient fault and reconnects
    forever. The status code is what lets the client stop and tell its
    operator the credentials are wrong.
    """
    import pybase64
    auth = pybase64.b64encode(b"bad-key-client:nope-not-a-real-key").decode("ascii")
    sock = ws_client.create_connection(
        f"{tornado_server.url}/?authorization={auth}", timeout=3,
    )
    sock.settimeout(3)
    try:
        frame = sock.recv_frame()
        while frame.opcode != ws_client.ABNF.OPCODE_CLOSE:
            frame = sock.recv_frame()
    finally:
        sock.close()

    code = 256 * frame.data[0] + frame.data[1]
    assert code == 1008, f"a refused key must close with 1008, got {code}"
    assert b"invalid api key" in frame.data[2:], \
        "the close reason must name the cause, not just the code"


def test_malformed_authorization_query_rejected(tornado_server):
    """Garbage in ?authorization= must close with 1008, not crash."""
    sock = ws_client.create_connection(
        f"{tornado_server.url}/?authorization=!!!not-base64!!!",
        timeout=3,
    )
    # Server closes the socket; reading returns empty or raises.
    sock.settimeout(2)
    try:
        sock.recv()
    except Exception:
        pass
    sock.close()
    _wait(lambda: not tornado_server.listener.clients, timeout=1)
    assert not tornado_server.listener.clients


def test_empty_authorization_query_rejected(tornado_server):
    """Missing authorization param must also be rejected cleanly."""
    sock = ws_client.create_connection(
        f"{tornado_server.url}/",
        timeout=3,
    )
    sock.settimeout(2)
    try:
        sock.recv()
    except Exception:
        pass
    sock.close()
    assert not tornado_server.listener.clients


def test_url_encoded_base64_padding(tornado_server):
    """Tornado's get_query_argument must percent-decode '%3D' back to '='."""
    raw_auth = f"e2e:{tornado_server.api_key}"
    b64 = pybase64.b64encode(raw_auth.encode()).decode()
    auth_param = b64.replace("=", "%3D")

    sock = ws_client.create_connection(
        f"{tornado_server.url}/?authorization={auth_param}",
        timeout=3,
    )
    # If decoding failed, the server would have closed immediately.
    # If it worked, the server sent at least one frame (HELLO).
    sock.settimeout(2)
    received = []
    try:
        for _ in range(2):
            received.append(sock.recv())
    except Exception:
        pass
    sock.close()
    assert any(b"hello" in (f if isinstance(f, bytes) else f.encode())
               for f in received), \
        "expected at least a HELLO frame, got nothing — percent-decoding broken?"


# --- transport: BUS message round-trip -----------------------------------

def test_bus_message_round_trip(tornado_server):
    """A BUS message in the allowlist reaches the listener's bus_msg handler."""
    c = _client(tornado_server)
    seen = []
    original = tornado_server.listener.handle_bus_message

    def _capture(message, client_conn):
        seen.append(message)
        return original(message, client_conn)

    tornado_server.listener.handle_bus_message = _capture
    try:
        _wait_clients(tornado_server, 1)
        c.emit(Message("recognizer_loop:utterance",
                       {"utterances": ["hello hivemind"]}))
        _wait(lambda: bool(seen), timeout=3)
        assert seen, "listener never saw the BUS message"
        assert seen[0].payload.msg_type == "recognizer_loop:utterance"
    finally:
        tornado_server.listener.handle_bus_message = original
        c.close()


def test_blocked_message_type_does_not_crash_connection(tornado_server):
    """Non-allowlisted bus types are dropped; client stays connected."""
    c = _client(tornado_server)
    try:
        _wait_clients(tornado_server, 1)
        c.emit(Message("not.in.allowlist", {}))
        time.sleep(0.3)
        assert tornado_server.listener.clients, \
            "client should still be connected after blocked message"
    finally:
        c.close()


def test_recognizer_loop_b64_audio_branch(tornado_server):
    """on_message has a dedicated branch for recognizer_loop:b64_audio.

    Exercising it via the real transport so the branch is covered.
    """
    c = _client(tornado_server)
    seen = []
    original = tornado_server.listener.handle_bus_message

    def _capture(message, client_conn):
        seen.append(message)
        return original(message, client_conn)

    tornado_server.listener.handle_bus_message = _capture
    try:
        _wait_clients(tornado_server, 1)
        c.emit(Message("recognizer_loop:b64_audio", {"audio": "AAAA"}))
        _wait(lambda: bool(seen), timeout=3)
        assert seen and seen[0].payload.msg_type == "recognizer_loop:b64_audio"
    finally:
        tornado_server.listener.handle_bus_message = original
        c.close()


# --- privacy: INFO logs must not leak message payloads --------------------

def test_info_log_does_not_leak_utterance_payload(tornado_server, caplog):
    """recognizer_loop:utterance carries the user's transcribed speech.

    INFO logging is enabled by default, so on_message must never format the
    full HiveMessage (and therefore the utterance text) into an INFO record.
    """
    sentinel = "the quick brown fox sentinel utterance"
    c = _client(tornado_server)
    try:
        _wait_clients(tornado_server, 1)
        with caplog.at_level("INFO"):
            c.emit(Message("recognizer_loop:utterance", {"utterances": [sentinel]}))
            time.sleep(0.3)
        leaked = [r for r in caplog.records
                  if r.levelname == "INFO" and sentinel in r.getMessage()]
        assert not leaked, f"utterance payload leaked into INFO logs: {leaked}"
    finally:
        c.close()


def test_multiple_sequential_messages(tornado_server):
    """Five BUS messages in a row all reach the listener."""
    c = _client(tornado_server)
    seen = []
    original = tornado_server.listener.handle_bus_message

    def _capture(message, client_conn):
        seen.append(message)
        return original(message, client_conn)

    tornado_server.listener.handle_bus_message = _capture
    try:
        _wait_clients(tornado_server, 1)
        for i in range(5):
            c.emit(Message("recognizer_loop:utterance",
                           {"utterances": [f"msg {i}"]}))
        _wait(lambda: len(seen) >= 5, timeout=3)
        assert len(seen) == 5, f"expected 5 messages, got {len(seen)}"
    finally:
        tornado_server.listener.handle_bus_message = original
        c.close()
