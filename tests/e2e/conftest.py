"""Shared fixtures for end-to-end tests.

Two flavours:

- `hive`: hivescope's in-process shim — fast, used for assertions about the
  HiveMind listener protocol's routing logic (binary frames, broadcast, etc).
- `tornado_server`: spins up the *actual* HiveMindWebsocketProtocol (Tornado
  on a real port) and yields connection info. Tests that need to exercise
  the websocket transport itself (auth via query string, real frames over
  the wire, on_close cleanup) use this fixture and connect via
  `HiveMessageBusClient`.
"""
import socket
import threading
import time
from dataclasses import dataclass

import pytest
from tornado import ioloop

from hivemind_websocket_protocol import HiveMindTornadoWebSocket
from hivescope.node import MasterNode
from hivescope.scenarios import single_satellite


# ---------------------------------------------------------------------------
# In-process (fast) — for routing/protocol assertions
# ---------------------------------------------------------------------------

@pytest.fixture
def hive():
    """A started single-satellite topology; teardown is automatic.

    Yields `(master, satellite)` for the standard M0/S0 pair.
    """
    builder = single_satellite()
    try:
        builder.start_all()
        yield builder.get_master("M0"), builder.get_satellite("S0")
    finally:
        builder.stop_all()


# ---------------------------------------------------------------------------
# Real Tornado — for transport assertions
# ---------------------------------------------------------------------------

@dataclass
class TornadoServer:
    host: str
    port: int
    api_key: str
    password: str
    master: MasterNode  # provides .hm_protocol, .recorder, .db, etc.

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @property
    def listener(self):
        return self.master.hm_protocol


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def tornado_server():
    """Run HiveMindWebsocketProtocol on a real Tornado server in a thread.

    Yields a `TornadoServer` carrying host/port/api_key/password/master. The
    server is torn down after the test by stopping the ioloop.

    Only one Tornado server can run per process at a time because the handler
    keeps `loop`/`hm_protocol` as class attributes — pytest's default
    function-scope serialises that for us.
    """
    api_key = "test-api-key"
    password = "test-password"

    # Borrow hivescope's wiring for db / agent / binary protocols, then
    # point our Tornado server at its hm_protocol.
    master = MasterNode.create(
        "M0",
        require_crypto=False,
        handshake_enabled=True,
    )
    master.register_satellite(
        api_key,
        password=password,
        allowed_types=["recognizer_loop:utterance", "speak"],
    )

    port = _free_port()
    server_ready = threading.Event()
    server_error = []

    def _run():
        try:
            import asyncio
            from tornado import web
            from tornado.platform.asyncio import AnyThreadEventLoopPolicy
            asyncio.set_event_loop_policy(AnyThreadEventLoopPolicy())
            loop = ioloop.IOLoop()
            loop.make_current()
            HiveMindTornadoWebSocket.loop = loop
            HiveMindTornadoWebSocket.hm_protocol = master.hm_protocol
            app = web.Application([("/", HiveMindTornadoWebSocket)])
            app.listen(port, "127.0.0.1")
            loop.add_callback(server_ready.set)
            loop.start()
        except Exception as exc:
            server_error.append(exc)
            server_ready.set()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    if not server_ready.wait(timeout=5.0):
        raise RuntimeError("Tornado server failed to start within 5s")
    if server_error:
        raise server_error[0]
    time.sleep(0.05)  # let listen() finish binding before first client

    try:
        yield TornadoServer(host="127.0.0.1", port=port,
                            api_key=api_key, password=password, master=master)
    finally:
        loop = HiveMindTornadoWebSocket.loop
        if loop is not None:
            loop.add_callback(loop.stop)
        thread.join(timeout=5.0)
