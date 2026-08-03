"""Optional webrockets backend.

Same wire protocol as the default Tornado backend — clients still connect to
the server root and authenticate with a base64 ``name:key`` in the
``authorization`` query argument. Admission is shared with Tornado (see
:mod:`hivemind_websocket_protocol._admission`); only the transport differs.

webrockets is an optional dependency. Install it with::

    pip install hivemind-websocket-protocol[webrockets]

Two things this backend cannot do, by design:

- No client IP. webrockets does not expose the peer address, so log lines
  here carry the client name only. The address was diagnostic anyway.
- No TLS. webrockets terminates plain websockets; put it behind a reverse
  proxy for ``wss://``. Use the Tornado backend if you want the listener to
  serve TLS itself.
"""
import dataclasses
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl

from hivemind_bus_client.message import HiveMessageType
from hivemind_core.protocol import HiveMindListenerProtocol
from hivemind_plugin_manager.protocols import ClientCallbacks, NetworkProtocol
from ovos_utils.log import LOG

from hivemind_websocket_protocol._admission import (
    ClientRejected,
    authorize_client,
    decode_auth,
)


def query_authorization(query_string: str) -> Optional[str]:
    """Read the authorization argument out of a raw query string."""
    return dict(parse_qsl(query_string)).get("authorization")


@dataclasses.dataclass
class HiveMindWebrocketsProtocol(NetworkProtocol):
    """
    webrockets based listener for HiveMind client connections.

    Attributes:
        hm_protocol (Optional[HiveMindListenerProtocol]): The protocol instance for handling HiveMind messages.
    """
    config: Dict[str, Any] = dataclasses.field(default_factory=dict)
    hm_protocol: Optional[HiveMindListenerProtocol] = None
    callbacks: ClientCallbacks = dataclasses.field(default_factory=ClientCallbacks)

    def build_server(self):
        """
        Create the webrockets server with the HiveMind route already wired.

        Returns:
            WebsocketServer: A server that still needs to be started.
        """
        from webrockets import WebsocketServer
        from webrockets.auth import AuthenticationFailed

        host = self.config.get("host") or self.identity.default_master or "0.0.0.0"
        host = host.split("://")[-1]
        port = int(self.config.get("port") or self.identity.default_port or 5678)

        server = WebsocketServer(host=host, port=port)
        # HiveMind clients connect to the server root with no path at all;
        # webrockets normalises that to "/" before routing.
        route = server.create_route("")

        @route.connect(when="before")
        def authenticate(conn) -> None:
            auth = query_authorization(conn.query_string)
            try:
                decode_auth(auth)
            except (ValueError, UnicodeDecodeError) as e:
                LOG.warning(
                    f"rejecting websocket: bad authorization "
                    f"({e.__class__.__name__}: {e}) raw={auth!r}"
                )
                # webrockets refuses the handshake outright, so the peer sees an
                # HTTP error rather than a websocket close code
                raise AuthenticationFailed("invalid authorization") from e

        @route.connect(when="after")
        def connected(conn) -> None:
            useragent, key = decode_auth(query_authorization(conn.query_string))
            LOG.info(f"Authorizing client - {useragent}:{key}")

            def do_send(payload: str, is_bin: bool):
                # sends arrive from foreign threads — the agent bus thread, the
                # upstream slave thread. conn.send hands the frame to the rust
                # runtime, which owns the queueing, so no marshalling is needed
                # here. The frame type follows the payload type.
                conn.send(payload)

            try:
                client = authorize_client(useragent, key, self.hm_protocol,
                                          send_msg=do_send, disconnect=conn.close)
            except ClientRejected:
                conn.close()
                return

            conn.user = client
            self.hm_protocol.handle_new_client(client)

        @route.receive
        def received(conn, payload) -> None:
            client = conn.user
            message = client.decode(payload)
            if (
                    message.msg_type == HiveMessageType.BUS
                    and message.payload.msg_type == "recognizer_loop:b64_audio"
            ):
                LOG.info(f"Received {client.peer} sent base64 audio for STT")
            else:
                LOG.info(f"Received {client.peer} message: {message}")
            self.hm_protocol.handle_message(message, client)

        @route.disconnect
        def disconnected(conn, code, reason) -> None:
            client = conn.user
            if client is None:
                LOG.debug("closing unauthenticated websocket (no client was ever attached)")
                return
            LOG.info(f"disconnecting client: {client.peer}")
            self.hm_protocol.handle_client_disconnected(client)

        return server

    def run(self):
        LOG.debug(f"webrockets server config: {self.config}")
        server = self.build_server()
        LOG.info("ws listener started")
        server.start()  # blocking
