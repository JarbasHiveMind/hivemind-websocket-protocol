import asyncio
import dataclasses
import math
import os
import os.path
import random
import threading
import time
from os import makedirs
from os.path import exists, join
from socket import gethostname
from typing import Any, Dict, Optional, Tuple

import pybase64
from hivemind_bus_client.message import HiveMessageType
from hivemind_plugin_manager.protocols import NetworkProtocol
from OpenSSL import crypto
from ovos_bus_client.session import Session
from ovos_utils.log import LOG
from ovos_utils.xdg_utils import xdg_data_home
from poorman_handshake import PasswordHandShake
from tornado import ioloop
from tornado import web
from tornado.platform.asyncio import AnyThreadEventLoopPolicy
from tornado.websocket import WebSocketHandler
from tornado.websocket import WebSocketClosedError, WebSocketHandler

try:
    from hivemind_core.config import runtime_password_min_bits
except ImportError:  # released hivemind-core without the helper
    import os

    def runtime_password_min_bits():
        return 0.0 if os.environ.get("HIVEMIND_DISABLE_PASSWORD_STRENGTH_CHECK", "").strip().lower() in ("1", "true", "yes", "on") else 40.0

from hivemind_core.protocol import (
    HiveMindClientConnection,
    HiveMindListenerProtocol,
    HiveMindNodeType,
)
from hivemind_plugin_manager.database import Client
from hivemind_plugin_manager.protocols import ClientCallbacks

from hivemind_websocket_protocol._client_ip import (
    parse_networks,
    resolve_client_ip,
)
from hivemind_websocket_protocol.health import (
    LOCAL_HEALTH_PATH,
    HiveMindWebApplication,
    LocalHealthHandler,
)

DEFAULT_TRUSTED_HEADERS = "x-forwarded-for,x-real-ip"
DEFAULT_WEBSOCKET_PING_INTERVAL = 30.0
DEFAULT_WEBSOCKET_PING_TIMEOUT = 20.0


def _split_csv(value: Any) -> Tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return tuple(v.strip() for v in value.split(",") if v.strip())
    return tuple(str(v).strip() for v in value if str(v).strip())


def _non_negative_float(value: Any, default: float, name: str) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        LOG.warning(f"Ignoring invalid {name}: {value!r}")
        return default
    if not math.isfinite(parsed):
        LOG.warning(f"Ignoring invalid {name}: {value!r}")
        return default
    if parsed < 0:
        LOG.warning(f"Ignoring negative {name}: {value!r}")
        return default
    return parsed


@dataclasses.dataclass
class HiveMindWebsocketProtocol(NetworkProtocol):
    """
    WebSocket handler for managing HiveMind client connections.

    Attributes:
        hm_protocol (Optional[HiveMindListenerProtocol]): The protocol instance for handling HiveMind messages.
    """
    config: Dict[str, Any] = dataclasses.field(default_factory=dict)
    hm_protocol: Optional[HiveMindListenerProtocol] = None
    callbacks: ClientCallbacks = dataclasses.field(default_factory=ClientCallbacks)

    def _websocket_ping_settings(self) -> Dict[str, float]:
        interval = self.config.get(
            "websocket_ping_interval",
            os.getenv("HIVEMIND_WEBSOCKET_PING_INTERVAL"),
        )
        timeout = self.config.get(
            "websocket_ping_timeout",
            os.getenv("HIVEMIND_WEBSOCKET_PING_TIMEOUT"),
        )
        return {
            "websocket_ping_interval": _non_negative_float(
                interval,
                DEFAULT_WEBSOCKET_PING_INTERVAL,
                "websocket_ping_interval",
            ),
            "websocket_ping_timeout": _non_negative_float(
                timeout,
                DEFAULT_WEBSOCKET_PING_TIMEOUT,
                "websocket_ping_timeout",
            ),
        }

    def run(self):
        LOG.debug(f"websocket server config: {self.config}")
        asyncio_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(asyncio_loop)
        loop = ioloop.IOLoop.current()
        HiveMindTornadoWebSocket.loop = loop
        HiveMindTornadoWebSocket.hm_protocol = self.hm_protocol

        if "trusted_proxy_cidrs" in self.config:
            proxy_cidrs = self.config["trusted_proxy_cidrs"]
        else:
            proxy_cidrs = os.getenv("HIVEMIND_TRUSTED_PROXY_CIDRS")

        if "trusted_client_ip_headers" in self.config:
            client_ip_headers = self.config["trusted_client_ip_headers"]
        else:
            client_ip_headers = (
                os.getenv("HIVEMIND_TRUSTED_CLIENT_IP_HEADERS")
                or DEFAULT_TRUSTED_HEADERS
            )
        trusted_networks = parse_networks(_split_csv(proxy_cidrs))
        trusted_headers = tuple(h.lower() for h in _split_csv(client_ip_headers))

        ssl = self.config.get("ssl", False)
        cert_dir: str = self.config.get("cert_dir") or f"{xdg_data_home()}/hivemind"
        cert_name: str = self.config.get("cert_name") or "hivemind"
        host = self.config.get("host") or self.identity.default_master or "0.0.0.0"
        host = host.split("://")[-1]
        port = int(self.config.get("port") or self.identity.default_port or 5678)

        routes: list = [
            (LOCAL_HEALTH_PATH, LocalHealthHandler),
            ("/", HiveMindTornadoWebSocket),
        ]
        websocket_ping_settings = self._websocket_ping_settings()
        application = HiveMindWebApplication(
            routes,
            trusted_networks=trusted_networks,
            trusted_headers=trusted_headers,
            **websocket_ping_settings,
        )
        startup_error: Optional[Exception] = None

        def start_listener() -> None:
            nonlocal startup_error
            try:
                if ssl:
                    cert_file = f"{cert_dir}/{cert_name}.crt"
                    key_file = f"{cert_dir}/{cert_name}.key"
                    if not os.path.isfile(key_file):
                        LOG.info("generating self-signed SSL certificate")
                        cert_file, key_file = self.create_self_signed_cert(
                            cert_dir, cert_name
                        )
                    LOG.debug("using ssl key at " + key_file)
                    LOG.debug("using ssl certificate at " + cert_file)
                    ssl_options = {"certfile": cert_file, "keyfile": key_file}
                    application.listen(port, host, ssl_options=ssl_options)
                    LOG.info("wss listener started")
                else:
                    application.listen(port, host)
                    LOG.info("ws listener started")
            except Exception as e:
                startup_error = e
                LOG.exception("failed to start websocket listener")
                loop.stop()

        loop.add_callback(start_listener)
        loop.start()  # blocking
        if startup_error is not None:
            raise startup_error

    @staticmethod
    def create_self_signed_cert(
            cert_dir: str = f"{xdg_data_home()}/hivemind",
            name: str = "hivemind"
    ) -> Tuple[str, str]:
        """
        Create a self-signed certificate and key pair if they do not already exist.

        Args:
            cert_dir (str): The directory where the certificate and key will be stored.
            name (str): The base name for the certificate and key files.

        Returns:
            Tuple[str, str]: The paths to the created certificate and key files.
        """
        cert_file = name + ".crt"
        key_file = name + ".key"
        cert_path = join(cert_dir, cert_file)
        key_path = join(cert_dir, key_file)
        makedirs(cert_dir, exist_ok=True)

        if not exists(join(cert_dir, cert_file)) or not exists(join(cert_dir, key_file)):
            # create a key pair
            k = crypto.PKey()
            k.generate_key(crypto.TYPE_RSA, 2048)

            # Create a self-signed certificate
            cert = crypto.X509()
            cert.get_subject().C = "PT"
            cert.get_subject().ST = "Europe"
            cert.get_subject().L = "Mountains"
            cert.get_subject().O = "Jarbas AI"
            cert.get_subject().OU = "Powered by HiveMind"
            cert.get_subject().CN = gethostname()
            cert.set_serial_number(random.randint(0, 2000))
            cert.gmtime_adj_notBefore(0)
            cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
            cert.set_issuer(cert.get_subject())
            cert.set_pubkey(k)
            cert.sign(k, "sha256")

            open(cert_path, "wb").write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
            open(key_path, "wb").write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))

        return cert_path, key_path


class ClientDatabaseSync:
    """Collapses concurrent ``db.sync()`` calls into one per ``debounce_s``.

    An api-key miss makes every connection want a fresh database. Without
    this, a burst of unknown keys becomes a burst of syncs. One instance is
    shared by every connection on the server, so the state is deliberately
    process-wide rather than per-handler.

    A failing sync is remembered for the rest of the window and re-raised at
    the callers that arrive during it, rather than each of them retrying a
    database that has just proven unreachable.
    """

    def __init__(self, debounce_s: float = 1.0):
        self.debounce_s = debounce_s
        self._lock = threading.Lock()
        self._last_ts: Optional[float] = None
        self._last_error: Optional[Exception] = None

    def reset(self) -> None:
        with self._lock:
            self._last_ts = None
            self._last_error = None

    def sync(self, db: Any) -> None:
        with self._lock:
            now = time.monotonic()
            if self._last_ts is not None and now - self._last_ts < self.debounce_s:
                if self._last_error is not None:
                    raise self._last_error
                return
            self._last_ts = now
            try:
                db.sync()
            except Exception as exc:
                self._last_error = exc
                raise
            else:
                self._last_error = None


class HiveMindTornadoWebSocket(WebSocketHandler):
    """
    WebSocket handler for managing HiveMind client connections.

    Attributes:
        hm_protocol (Optional[HiveMindListenerProtocol]): The protocol instance for handling HiveMind messages.
    """
    hm_protocol = None
    source_ip: Optional[str] = None
    last_pong: Optional[float] = None
    _sync_lock = threading.Lock()
    _last_sync_ts = 0.0
    _last_sync_error: Optional[Exception] = None
    _sync_debounce_s = 1.0
    db_sync = ClientDatabaseSync()

    def _client_ip(self) -> Optional[str]:
        return resolve_client_ip(
            getattr(self.request, "remote_ip", None),
            self.request.headers,
            self.settings.get("trusted_networks", ()),
            self.settings.get("trusted_headers", ()),
        )

    @staticmethod
    def decode_auth(auth: str) -> Tuple[str, str]:
        """
        Decode the base64 encoded authorization string.

        Args:
            auth (str): The base64 encoded authorization string.

        Returns:
            Tuple[str, str]: The decoded username and key.
        """
        decoded = pybase64.b64decode(auth or "", validate=True).decode("utf-8")
        name, key = decoded.split(":", 1)
        if not name or not key:
            raise ValueError("empty credentials")
        return name, key

    def on_message(self, message: str) -> None:
        self._handle_inbound_message(message)

    def _handle_inbound_message(self, message: str) -> None:
        try:
            message = self.client.decode(message)
        except Exception as e:
            # Never log the raw frame here: decode() failures happen on
            # ciphertext / encoded payloads that can carry credentials or
            # other sensitive content, and an unguarded traceback (the
            # previous behavior, since this propagated out of Tornado's
            # on_message) would put that content in the logs.
            LOG.warning(
                "rejecting inbound message from %s: decode failed (%s)",
                self._peer_label(getattr(self.client, "peer", "unknown")),
                type(e).__name__,
            )
            self.close(code=1008, reason="invalid message")
            return
        peer = self._peer_label(self.client.peer)
        if (
                message.msg_type == HiveMessageType.BUS
                and message.payload.msg_type == "recognizer_loop:b64_audio"
        ):
            LOG.debug(f"Received {peer} sent base64 audio for STT")
        else:
            LOG.info("Received %s message: %s", peer, message.msg_type)
            LOG.debug(f"Received {peer} message: {message}")
        self.hm_protocol.handle_message(message, self.client)

    def _peer_label(self, peer: str) -> str:
        return f"{peer} ({self.source_ip})" if self.source_ip else peer

    def on_pong(self, data: bytes) -> None:
        self.last_pong = time.monotonic()
    def _current_peer_label(self) -> str:
        client = getattr(self, "client", None)
        return self._peer_label(getattr(client, "peer", "unknown"))

    @classmethod
    def _sync_client_database(cls, db: Any) -> None:
        cls.db_sync.sync(db)

    def open(self) -> None:
        """
        Handle a new client connection and perform authorization.
        """
        self.last_pong = time.monotonic()
        self.source_ip = self._client_ip()
        auth = self.get_query_argument("authorization", None)
        try:
            useragent, key = self.decode_auth(auth)
        except (ValueError, UnicodeDecodeError) as e:
            # Never log `auth` itself: it is the base64 "name:secret_key"
            # blob, so logging it in any recoverable form would leak the
            # credential. A length is enough to diagnose truncated/garbled
            # headers without exposing the secret.
            LOG.warning(
                f"rejecting websocket from {self.source_ip or self.request.remote_ip}: "
                f"bad authorization ({e.__class__.__name__}: {e}) "
                f"len={len(auth) if auth is not None else 0}"
            )
            self.close(code=1008, reason="invalid authorization")
            return
        LOG.debug(f"Authorizing client from {self.source_ip or 'unknown'} - {useragent}")

        def do_send(payload: str, is_bin: bool):
            def _write():
                try:
                    self.write_message(payload, is_bin)
                except WebSocketClosedError:
                    LOG.debug(
                        "Websocket already closed while writing to "
                        f"{self._peer_label(getattr(self.client, 'peer', 'unknown'))}"
                    )
                    self.close()
                except Exception as exc:
                    LOG.warning(
                        "Could not write websocket message to "
                        f"{self._peer_label(getattr(self.client, 'peer', 'unknown'))}: "
                        f"{type(exc).__name__}: {exc!r}"
                    )
                    self.close()

            self.loop.add_callback(_write)

        def do_disconnect():
            self.loop.add_callback(self.close)

        self.client = HiveMindClientConnection(
            key=key,
            disconnect=do_disconnect,
            send_msg=do_send,
            sess=Session(session_id="default"),  # will be re-assigned once client sends handshake
            name=useragent,
            hm_protocol=self.hm_protocol
        )
        user: Client = self.hm_protocol.db.get_client_by_api_key(key)
        sync_error = False
        if not user:
            try:
                self._sync_client_database(self.hm_protocol.db)
            except Exception:
                sync_error = True
                LOG.exception("Client database sync failed while retrying api key lookup")
            else:
                user = self.hm_protocol.db.get_client_by_api_key(key)

        if not user:
            if sync_error:
                LOG.error("Client database unavailable during api key lookup")
                self.close(code=1011, reason="client database unavailable")
                return
            LOG.error("Client provided an invalid api key")
            self.hm_protocol.handle_invalid_key_connected(self.client)
            # Say *why*, with the same code a malformed authorization header
            # gets above. A bare close is indistinguishable from a network
            # drop, so a satellite treats a refused key as a transient fault
            # and reconnects forever, printing raw close frames and never
            # telling its operator the credentials are wrong.
            self.close(code=1008, reason="invalid api key")
            return

        self.client.name = f"{useragent}::{user.client_id}::{user.name}"
        self.client.crypto_key = user.crypto_key
        self.client.allowed_types = user.allowed_types
        self.client.can_broadcast = user.can_broadcast
        self.client.can_propagate = user.can_propagate
        self.client.can_escalate = user.can_escalate
        self.client.is_admin = user.is_admin
        if user.password:
            # pre-shared password to derive aes_key
            self.client.pswd_handshake = PasswordHandShake(user.password, min_bits=runtime_password_min_bits())

        self.client.node_type = HiveMindNodeType.NODE  # TODO . placeholder

        if (
                not self.client.crypto_key
                and not self.hm_protocol.handshake_enabled
                and self.hm_protocol.require_crypto
        ):
            LOG.error(
                "No pre-shared crypto key for client and handshake disabled, "
                "but configured to require crypto!"
            )
            # clients requiring handshake support might fail here
            self.hm_protocol.handle_invalid_protocol_version(self.client)
            # Permanent for the same reason a bad key is: neither the server
            # config nor the client's capabilities change between attempts.
            self.close(code=1008, reason="crypto required, no usable key")
            return

        self.hm_protocol.handle_new_client(self.client)
        # self.write_message(Message("connected").serialize())

    def on_close(self):
        client = getattr(self, "client", None)
        if client is None:
            LOG.debug(
                f"closing unauthenticated websocket from {self.request.remote_ip} "
                f"(no client was ever attached)"
            )
            return
        # The age of the last pong cannot tell a ping timeout apart from a
        # client that simply went away: tornado pings at T, waits ping_timeout
        # and then closes, so a real ping timeout shows an age of
        # ping_interval + ping_timeout - round_trip_time, which overlaps the
        # ages seen on ordinary disconnects. close_reason does not help either,
        # since tornado fills it in from the close frame the peer echoes back,
        # and a peer that timed out echoes nothing. Report the numbers and let
        # the operator read them; a guess here would only mislead.
        since_pong = (
            time.monotonic() - self.last_pong if self.last_pong is not None else None
        )
        LOG.info(
            "disconnecting client: %s (close_code=%s, close_reason=%s, "
            "seconds_since_last_pong=%s)",
            self._peer_label(client.peer), self.close_code, self.close_reason,
            f"{since_pong:.1f}" if since_pong is not None else "unknown",
        )
        LOG.debug(f"disconnecting client: {self._peer_label(client.peer)}")
        self.hm_protocol.handle_client_disconnected(client)

    def check_origin(self, origin) -> bool:
        return True
