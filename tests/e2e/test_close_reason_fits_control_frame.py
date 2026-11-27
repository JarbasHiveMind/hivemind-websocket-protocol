"""A long close reason must still close the connection.

RFC 6455 §5.5: a control frame's payload is at most 125 bytes, and a close
frame's payload is a 2-byte status code followed by the UTF-8 reason. Tornado
enforces this in ``_write_frame`` and raises
``ValueError("control frame payloads may not exceed 125 bytes")`` instead of
sending the frame. The error happens inside the IOLoop callback that
``do_disconnect`` schedules, so the peer never gets a close frame: the
connection stays open until it times out, with no code and no reason.

hivemind-core passes its abort reasons through unchanged, and some are long.
The pinned-key abort below is 238 bytes; ``f"handshake failure: {e}"`` and
``str(e)`` have no bound at all. The fix lives in the transport, where the
limit belongs, not in core, which serves every transport.
"""
import time

import pybase64
import websocket as ws_client

from hivemind_websocket_protocol import HiveMindTornadoWebSocket

# hivemind-core dev c36270a, protocol.py, the pinned-key abort reason
LONG_REASON = (
    "client Noise static key contradicts the pinned key. If this client was "
    "reinstalled or moved to new hardware, clear the pin with "
    "'hivemind-core reset-noise-pin test-api-key' and let it pair again; "
    "otherwise another node is answering for it"
)


def _wait(predicate, timeout=3.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return predicate()


def test_disconnect_with_a_long_reason_sends_a_close_frame(tornado_server, monkeypatch):
    """The server disconnects a connection with core's 238-byte pinned-key
    reason. The peer must receive a close frame with code 1008 and a reason cut
    to 123 bytes (dev: tornado raises in the IOLoop callback and no close frame
    is sent)."""
    assert len(LONG_REASON.encode("utf-8")) > 123
    handlers = []
    original_open = HiveMindTornadoWebSocket.open

    def capture_open(self, *args, **kwargs):
        result = original_open(self, *args, **kwargs)
        handlers.append(self)
        return result

    # hivemind-core lists a connection in `clients` only once its handshake
    # progresses, so take the server-side connection from the handler instead.
    monkeypatch.setattr(HiveMindTornadoWebSocket, "open", capture_open)

    auth = pybase64.b64encode(f"e2e:{tornado_server.api_key}".encode()).decode("ascii")
    sock = ws_client.create_connection(f"{tornado_server.url}/?authorization={auth}", timeout=3)
    sock.settimeout(3)
    try:
        sock.recv()  # the server's HELLO
        assert _wait(lambda: handlers and getattr(handlers[0], "client", None)), \
            "the server-side handler never opened"
        # the real path: HiveMindClientConnection.disconnect -> do_disconnect
        # -> IOLoop callback -> close(code, reason)
        handlers[0].client.disconnect(1008, LONG_REASON)

        try:
            frame = sock.recv_frame()
            while frame.opcode != ws_client.ABNF.OPCODE_CLOSE:
                frame = sock.recv_frame()
        except ws_client.WebSocketTimeoutException:
            raise AssertionError(
                "no close frame within 3 s: the long reason made tornado raise "
                "'control frame payloads may not exceed 125 bytes'") from None
    finally:
        sock.close()

    code = 256 * frame.data[0] + frame.data[1]
    reason = frame.data[2:]
    assert code == 1008, code
    assert 0 < len(reason) <= 123, len(reason)
    assert LONG_REASON.encode("utf-8").startswith(reason), reason
