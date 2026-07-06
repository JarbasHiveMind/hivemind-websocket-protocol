"""Unit-level coverage for the bits e2e tests don't reach directly.

Targets:
- `HiveMindWebsocketProtocol.run()` for the plain (ssl=False) path,
  including the actual `application.listen()` call.
- `create_self_signed_cert()` certificate / key generation.
- version.py module loading.
"""
import os
import socket
import threading
import time
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace

import pybase64
import pytest
from tornado.platform.asyncio import AnyThreadEventLoopPolicy
import asyncio

from hivemind_websocket_protocol import (
    DEFAULT_WEBSOCKET_PING_INTERVAL,
    DEFAULT_WEBSOCKET_PING_TIMEOUT,
    HiveMindTornadoWebSocket,
    HiveMindWebsocketProtocol,
)
from hivescope.node import MasterNode


# --- version.py module load ------------------------------------------------

def test_version_module_exposes_constants_and_string():
    from hivemind_websocket_protocol import version as v
    assert isinstance(v.VERSION_MAJOR, int)
    assert isinstance(v.VERSION_MINOR, int)
    assert isinstance(v.VERSION_BUILD, int)
    assert isinstance(v.VERSION_ALPHA, int)
    assert isinstance(v.__version__, str)
    assert v.__version__.startswith(
        f"{v.VERSION_MAJOR}.{v.VERSION_MINOR}.{v.VERSION_BUILD}"
    )


# --- websocket ping settings -----------------------------------------------

def test_websocket_ping_settings_default(monkeypatch):
    monkeypatch.delenv("HIVEMIND_WEBSOCKET_PING_INTERVAL", raising=False)
    monkeypatch.delenv("HIVEMIND_WEBSOCKET_PING_TIMEOUT", raising=False)
    proto = HiveMindWebsocketProtocol(config={})

    assert proto._websocket_ping_settings() == {
        "websocket_ping_interval": DEFAULT_WEBSOCKET_PING_INTERVAL,
        "websocket_ping_timeout": DEFAULT_WEBSOCKET_PING_TIMEOUT,
    }


def test_websocket_ping_settings_from_env(monkeypatch):
    monkeypatch.setenv("HIVEMIND_WEBSOCKET_PING_INTERVAL", "25")
    monkeypatch.setenv("HIVEMIND_WEBSOCKET_PING_TIMEOUT", "15")
    proto = HiveMindWebsocketProtocol(config={})

    assert proto._websocket_ping_settings() == {
        "websocket_ping_interval": 25.0,
        "websocket_ping_timeout": 15.0,
    }


def test_websocket_ping_settings_config_wins_over_env(monkeypatch):
    monkeypatch.setenv("HIVEMIND_WEBSOCKET_PING_INTERVAL", "25")
    monkeypatch.setenv("HIVEMIND_WEBSOCKET_PING_TIMEOUT", "15")
    proto = HiveMindWebsocketProtocol(
        config={"websocket_ping_interval": 10, "websocket_ping_timeout": 5}
    )

    assert proto._websocket_ping_settings() == {
        "websocket_ping_interval": 10.0,
        "websocket_ping_timeout": 5.0,
    }


def test_websocket_ping_settings_invalid_values_fall_back(monkeypatch):
    monkeypatch.setenv("HIVEMIND_WEBSOCKET_PING_INTERVAL", "-1")
    monkeypatch.setenv("HIVEMIND_WEBSOCKET_PING_TIMEOUT", "nope")
    proto = HiveMindWebsocketProtocol(config={})

    assert proto._websocket_ping_settings() == {
        "websocket_ping_interval": DEFAULT_WEBSOCKET_PING_INTERVAL,
        "websocket_ping_timeout": DEFAULT_WEBSOCKET_PING_TIMEOUT,
    }


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_websocket_ping_settings_non_finite_values_fall_back(monkeypatch, value):
    monkeypatch.setenv("HIVEMIND_WEBSOCKET_PING_INTERVAL", value)
    monkeypatch.setenv("HIVEMIND_WEBSOCKET_PING_TIMEOUT", value)
    proto = HiveMindWebsocketProtocol(config={})

    assert proto._websocket_ping_settings() == {
        "websocket_ping_interval": DEFAULT_WEBSOCKET_PING_INTERVAL,
        "websocket_ping_timeout": DEFAULT_WEBSOCKET_PING_TIMEOUT,
    }


# --- open() auth path ------------------------------------------------------

def _auth_user(client_id=1, name="unit-client"):
    return SimpleNamespace(
        client_id=client_id,
        name=name,
        crypto_key=None,
        skill_blacklist=[],
        intent_blacklist=[],
        allowed_types=["recognizer_loop:utterance"],
        can_broadcast=True,
        can_propagate=True,
        can_escalate=True,
        is_admin=False,
        password=None,
    )


def _open_handler(db, key="api-key", seen_clients=None,
                  invalid_clients=None, closes=None):
    seen_clients = seen_clients if seen_clients is not None else []
    invalid_clients = invalid_clients if invalid_clients is not None else []
    closes = closes if closes is not None else []
    hm_protocol = SimpleNamespace(
        db=db,
        identity=SimpleNamespace(private_key=None),
        handshake_enabled=True,
        require_crypto=False,
        handle_new_client=seen_clients.append,
        handle_invalid_key_connected=invalid_clients.append,
        handle_invalid_protocol_version=lambda client: None,
    )

    handler = HiveMindTornadoWebSocket.__new__(HiveMindTornadoWebSocket)
    handler.hm_protocol = hm_protocol
    handler.request = SimpleNamespace(remote_ip="127.0.0.1", headers={})
    handler.application = SimpleNamespace(settings={})
    handler.loop = SimpleNamespace(
        install=lambda: None,
        add_callback=lambda callback, *args, **kwargs: callback(*args, **kwargs),
    )
    handler.write_message = lambda payload, is_bin=False: None
    handler.close = lambda *args, **kwargs: closes.append(
        {"args": args, "kwargs": kwargs}
    )
    handler.get_query_argument = lambda name, default=None: pybase64.b64encode(
        f"agent:{key}".encode("utf-8")
    ).decode("ascii")
    return handler


def test_open_schedules_downstream_writes_on_ioloop():
    user = _auth_user()
    scheduled = []
    writes = []
    handler = _open_handler(
        SimpleNamespace(get_client_by_api_key=lambda key: user),
        seen_clients=[],
    )
    handler.loop = SimpleNamespace(
        add_callback=lambda callback, *args, **kwargs: scheduled.append(
            (callback, args, kwargs)
        )
    )
    handler.write_message = lambda payload, is_bin=False: writes.append((payload, is_bin))

    handler.open()
    handler.client.send_msg("payload", True)

    assert writes == []
    assert len(scheduled) == 1
    callback, args, kwargs = scheduled.pop()
    callback(*args, **kwargs)
    assert writes == [("payload", True)]


def test_open_uses_direct_api_key_lookup_without_sync():
    user = _auth_user()

    def fail_sync():
        raise AssertionError("db.sync must not run on websocket open")

    seen_clients = []
    db = SimpleNamespace(
        sync=fail_sync,
        get_client_by_api_key=lambda key: user if key == "api-key" else None,
    )
    handler = _open_handler(db, seen_clients=seen_clients)

    handler.open()

    assert len(seen_clients) == 1
    assert seen_clients[0].name == "agent::1::unit-client"


def test_open_syncs_once_after_api_key_miss():
    HiveMindTornadoWebSocket._last_sync_ts = 0.0
    user = _auth_user(client_id=2, name="fresh-client")

    state = {"synced": False, "syncs": 0}

    def sync():
        state["syncs"] += 1
        state["synced"] = True

    def lookup(key):
        if key == "fresh-key" and state["synced"]:
            return user
        return None

    seen_clients = []
    invalid_clients = []
    db = SimpleNamespace(sync=sync, get_client_by_api_key=lookup)
    handler = _open_handler(
        db,
        key="fresh-key",
        seen_clients=seen_clients,
        invalid_clients=invalid_clients,
    )

    handler.open()

    assert state["syncs"] == 1
    assert len(invalid_clients) == 0
    assert len(seen_clients) == 1
    assert seen_clients[0].name == "agent::2::fresh-client"


def test_open_debounces_sync_after_recent_api_key_miss():
    HiveMindTornadoWebSocket._last_sync_ts = 0.0
    user = _auth_user(client_id=3, name="synced-client")
    state = {"synced": False, "syncs": 0}

    def sync():
        state["syncs"] += 1
        state["synced"] = True

    def lookup(key):
        if key == "fresh-key" and state["synced"]:
            return user
        return None

    db = SimpleNamespace(sync=sync, get_client_by_api_key=lookup)
    seen_clients = []
    invalid_clients = []
    _open_handler(db, key="fresh-key",
                  seen_clients=seen_clients).open()
    _open_handler(db, key="missing-key",
                  invalid_clients=invalid_clients).open()

    assert state["syncs"] == 1
    assert len(seen_clients) == 1
    assert len(invalid_clients) == 1


def test_open_reports_sync_failure_as_server_error():
    HiveMindTornadoWebSocket._last_sync_ts = 0.0

    def fail_sync():
        raise RuntimeError("redis unavailable")

    invalid_clients = []
    closes = []
    db = SimpleNamespace(
        sync=fail_sync,
        get_client_by_api_key=lambda key: None,
    )
    handler = _open_handler(
        db,
        key="fresh-key",
        invalid_clients=invalid_clients,
        closes=closes,
    )

    handler.open()

    assert invalid_clients == []
    assert closes[-1]["kwargs"] == {
        "code": 1011,
        "reason": "client database unavailable",
    }


def test_open_debounces_failed_sync_after_api_key_miss():
    HiveMindTornadoWebSocket._last_sync_ts = 0.0
    state = {"syncs": 0}

    def fail_sync():
        state["syncs"] += 1
        raise RuntimeError("redis unavailable")

    db = SimpleNamespace(
        sync=fail_sync,
        get_client_by_api_key=lambda key: None,
    )
    _open_handler(db, key="fresh-key", closes=[]).open()
    _open_handler(db, key="fresh-key", invalid_clients=[]).open()

    assert state["syncs"] == 1


# --- self-signed cert generation ------------------------------------------

def test_create_self_signed_cert_writes_files(tmp_path):
    cert, key = HiveMindWebsocketProtocol.create_self_signed_cert(
        cert_dir=str(tmp_path), name="hwp-test"
    )
    assert Path(cert).exists()
    assert Path(key).exists()
    assert Path(cert).read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")
    assert b"PRIVATE KEY" in Path(key).read_bytes()


def test_create_self_signed_cert_idempotent(tmp_path):
    """Second call with the same dir/name reuses the existing files."""
    c1, k1 = HiveMindWebsocketProtocol.create_self_signed_cert(
        cert_dir=str(tmp_path), name="hwp-test"
    )
    mtime = os.path.getmtime(c1)
    # Sleep so a rewrite would change the mtime.
    time.sleep(0.05)
    c2, k2 = HiveMindWebsocketProtocol.create_self_signed_cert(
        cert_dir=str(tmp_path), name="hwp-test"
    )
    assert c1 == c2 and k1 == k2
    assert os.path.getmtime(c1) == mtime, "should not have been rewritten"


# --- run() lifecycle -------------------------------------------------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_run_starts_and_serves_on_plain_ws():
    """Calling proto.run() binds the port and serves local liveness."""
    master = MasterNode.create("MX", require_crypto=False, handshake_enabled=True)
    port = _free_port()
    proto = HiveMindWebsocketProtocol(
        config={"host": "127.0.0.1", "port": port, "ssl": False},
        hm_protocol=master.hm_protocol,
    )

    # Earlier tests (tornado_server fixture) leave a stale class-level loop
    # reference pointing at a stopped loop. Clear it so our polling loop
    # only signals on a fresh one.
    if hasattr(HiveMindTornadoWebSocket, "loop"):
        del HiveMindTornadoWebSocket.loop

    started = threading.Event()

    def _run():
        # run() calls IOLoop.current() inside; needs the policy on this thread.
        asyncio.set_event_loop_policy(AnyThreadEventLoopPolicy())
        started.set()
        proto.run()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    assert started.wait(2)
    try:
        for _ in range(100):
            connection = HTTPConnection("127.0.0.1", port, timeout=1)
            try:
                connection.request("GET", "/_healthz")
                response = connection.getresponse()
                assert response.status == 204
                assert response.read() == b""
                break
            except OSError:
                time.sleep(0.02)
            finally:
                connection.close()
        else:
            raise AssertionError("listener health endpoint did not become ready")
    finally:
        loop = getattr(HiveMindTornadoWebSocket, "loop", None)
        if loop is not None:
            loop.add_callback(loop.stop)

    t.join(timeout=5)
    assert not t.is_alive(), "run() did not return after ioloop.stop()"


def test_run_raises_when_listener_bind_fails():
    """Bind failures should propagate instead of looking like clean exits."""
    master = MasterNode.create("MF", require_crypto=False, handshake_enabled=True)
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    proto = HiveMindWebsocketProtocol(
        config={"host": "127.0.0.1", "port": port, "ssl": False},
        hm_protocol=master.hm_protocol,
    )
    if hasattr(HiveMindTornadoWebSocket, "loop"):
        del HiveMindTornadoWebSocket.loop

    try:
        with pytest.raises(OSError):
            proto.run()
    finally:
        blocker.close()


def test_run_ssl_path_uses_existing_cert(tmp_path):
    """SSL branch in run(): existing cert is picked up; no regeneration."""
    cert, key = HiveMindWebsocketProtocol.create_self_signed_cert(
        cert_dir=str(tmp_path), name="ssl-test"
    )
    master = MasterNode.create("MS", require_crypto=False, handshake_enabled=True)
    port = _free_port()
    proto = HiveMindWebsocketProtocol(
        config={"host": "127.0.0.1", "port": port, "ssl": True,
                "cert_dir": str(tmp_path), "cert_name": "ssl-test"},
        hm_protocol=master.hm_protocol,
    )
    if hasattr(HiveMindTornadoWebSocket, "loop"):
        del HiveMindTornadoWebSocket.loop

    started = threading.Event()

    def _stop_when_ready():
        for _ in range(200):
            loop = getattr(HiveMindTornadoWebSocket, "loop", None)
            if loop is not None and getattr(loop, "asyncio_loop", None) is not None:
                time.sleep(0.1)
                loop.add_callback(loop.stop)
                return
            time.sleep(0.05)

    def _run():
        asyncio.set_event_loop_policy(AnyThreadEventLoopPolicy())
        threading.Thread(target=_stop_when_ready, daemon=True).start()
        started.set()
        proto.run()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    assert started.wait(2)
    t.join(timeout=5)
    assert not t.is_alive()


def test_run_ssl_path_generates_missing_cert(tmp_path):
    """SSL branch in run(): if cert/key are missing, they're generated."""
    master = MasterNode.create("MS2", require_crypto=False, handshake_enabled=True)
    port = _free_port()
    cert_dir = tmp_path / "fresh"
    proto = HiveMindWebsocketProtocol(
        config={"host": "127.0.0.1", "port": port, "ssl": True,
                "cert_dir": str(cert_dir), "cert_name": "gen-me"},
        hm_protocol=master.hm_protocol,
    )
    if hasattr(HiveMindTornadoWebSocket, "loop"):
        del HiveMindTornadoWebSocket.loop

    started = threading.Event()

    def _stop_when_ready():
        for _ in range(200):
            loop = getattr(HiveMindTornadoWebSocket, "loop", None)
            if loop is not None and getattr(loop, "asyncio_loop", None) is not None:
                time.sleep(0.1)
                loop.add_callback(loop.stop)
                return
            time.sleep(0.05)

    def _run():
        asyncio.set_event_loop_policy(AnyThreadEventLoopPolicy())
        threading.Thread(target=_stop_when_ready, daemon=True).start()
        started.set()
        proto.run()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    assert started.wait(2)
    t.join(timeout=5)
    assert not t.is_alive()
    assert (cert_dir / "gen-me.crt").exists()
    assert (cert_dir / "gen-me.key").exists()
