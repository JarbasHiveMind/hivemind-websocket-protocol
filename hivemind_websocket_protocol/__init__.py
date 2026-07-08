import asyncio
import dataclasses
import math
import os
import os.path
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from os import makedirs
from os.path import exists, join
from socket import gethostname
from typing import Deque, Dict, Any, Optional, Tuple

import pybase64
from OpenSSL import crypto
from hivemind_plugin_manager.protocols import NetworkProtocol
from ovos_bus_client.session import Session
from ovos_utils.log import LOG
from ovos_utils.xdg_utils import xdg_data_home
from poorman_handshake import PasswordHandShake
from tornado import ioloop
from tornado import web
from tornado.websocket import WebSocketClosedError, WebSocketHandler

from hivemind_bus_client.message import HiveMessageType
try:
    from hivemind_core.config import runtime_password_min_bits
except ImportError:  # released hivemind-core without the helper
    import os

    def runtime_password_min_bits():
        return 0.0 if os.environ.get("HIVEMIND_DISABLE_PASSWORD_STRENGTH_CHECK", "").strip().lower() in ("1", "true", "yes", "on") else 40.0

from hivemind_core.protocol import (
    HiveMindListenerProtocol,
    HiveMindClientConnection,
    HiveMindNodeType
)
from hivemind_plugin_manager.protocols import ClientCallbacks
from hivemind_plugin_manager.database import Client

from hivemind_websocket_protocol._client_ip import (
    parse_networks,
    resolve_client_ip,
)


DEFAULT_TRUSTED_HEADERS = "x-forwarded-for,x-real-ip"
DEFAULT_WEBSOCKET_PING_INTERVAL = 30.0
DEFAULT_WEBSOCKET_PING_TIMEOUT = 20.0
DEFAULT_WEBSOCKET_MESSAGE_WORKERS = 8
DEFAULT_WEBSOCKET_MESSAGE_QUEUE = 64


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


def _positive_int(value: Any, default: int, name: str) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        LOG.warning(f"Ignoring invalid {name}: {value!r}")
        return default
    if parsed <= 0:
        LOG.warning(f"Ignoring non-positive {name}: {value!r}")
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
        HiveMindTornadoWebSocket.configure_message_workers(self.config)

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

        routes: list = [("/", HiveMindTornadoWebSocket)]
        websocket_ping_settings = self._websocket_ping_settings()
        application = web.Application(
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


class HiveMindTornadoWebSocket(WebSocketHandler):
    """
    WebSocket handler for managing HiveMind client connections.

    Attributes:
        hm_protocol (Optional[HiveMindListenerProtocol]): The protocol instance for handling HiveMind messages.
    """
    hm_protocol = None
    source_ip: Optional[str] = None
    _message_executor: Optional[ThreadPoolExecutor] = None
    _message_workers = DEFAULT_WEBSOCKET_MESSAGE_WORKERS
    _message_queue_size = DEFAULT_WEBSOCKET_MESSAGE_QUEUE
    _message_executor_lock = threading.Lock()
    _sync_lock = threading.Lock()
    _last_sync_ts = 0.0
    _last_sync_error: Optional[Exception] = None
    _sync_debounce_s = 1.0

    def initialize(self) -> None:
        self._inbound_messages: Deque[Any] = deque()
        self._inbound_lock = threading.Lock()
        self._inbound_draining = False

    @classmethod
    def configure_message_workers(cls, config: Dict[str, Any]) -> None:
        workers = _positive_int(
            config.get("websocket_message_workers")
            or os.getenv("HIVEMIND_WEBSOCKET_MESSAGE_WORKERS"),
            DEFAULT_WEBSOCKET_MESSAGE_WORKERS,
            "websocket_message_workers",
        )
        queue_size = _positive_int(
            config.get("websocket_message_queue")
            or os.getenv("HIVEMIND_WEBSOCKET_MESSAGE_QUEUE"),
            DEFAULT_WEBSOCKET_MESSAGE_QUEUE,
            "websocket_message_queue",
        )
        with cls._message_executor_lock:
            cls._message_queue_size = queue_size
            if cls._message_executor is None or cls._message_workers != workers:
                old_executor = cls._message_executor
                cls._message_workers = workers
                cls._message_executor = ThreadPoolExecutor(
                    max_workers=workers,
                    thread_name_prefix="hivemind-ws-message",
                )
                if old_executor is not None:
                    old_executor.shutdown(wait=False, cancel_futures=True)

    @classmethod
    def _executor(cls) -> ThreadPoolExecutor:
        with cls._message_executor_lock:
            if cls._message_executor is None:
                cls._message_executor = ThreadPoolExecutor(
                    max_workers=cls._message_workers,
                    thread_name_prefix="hivemind-ws-message",
                )
            return cls._message_executor

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
        with self._inbound_lock:
            if len(self._inbound_messages) >= self._message_queue_size:
                LOG.warning(
                    "closing websocket from "
                    f"{self._current_peer_label()}: "
                    "inbound message queue is full"
                )
                self.close(code=1013, reason="message queue full")
                return
            self._inbound_messages.append(message)
            if self._inbound_draining:
                return
            self._inbound_draining = True
        self._executor().submit(self._drain_inbound_messages)

    def _drain_inbound_messages(self) -> None:
        while True:
            with self._inbound_lock:
                if not self._inbound_messages:
                    self._inbound_draining = False
                    return
                message = self._inbound_messages.popleft()
            try:
                self._handle_inbound_message(message)
            except Exception:
                LOG.exception(
                    "failed to process websocket message from "
                    f"{self._current_peer_label()}"
                )
                self.loop.add_callback(self.close)
                return

    def _handle_inbound_message(self, message: str) -> None:
        message = self.client.decode(message)
        peer = self._peer_label(self.client.peer)
        if (
                message.msg_type == HiveMessageType.BUS
                and message.payload.msg_type == "recognizer_loop:b64_audio"
        ):
            LOG.debug(f"Received {peer} sent base64 audio for STT")
        else:
            LOG.debug(f"Received {peer} message: {message}")
        self.hm_protocol.handle_message(message, self.client)

    def _peer_label(self, peer: str) -> str:
        return f"{peer} ({self.source_ip})" if self.source_ip else peer

    def _current_peer_label(self) -> str:
        client = getattr(self, "client", None)
        return self._peer_label(getattr(client, "peer", "unknown"))

    @classmethod
    def _sync_client_database(cls, db: Any) -> None:
        sync = getattr(db, "sync", None)
        if not callable(sync):
            return
        with cls._sync_lock:
            now = time.monotonic()
            if now - cls._last_sync_ts < cls._sync_debounce_s:
                if cls._last_sync_error is not None:
                    raise cls._last_sync_error
                return
            cls._last_sync_ts = now
            try:
                sync()
            except Exception as exc:
                cls._last_sync_error = exc
                raise
            else:
                cls._last_sync_error = None

    def open(self) -> None:
        """
        Handle a new client connection and perform authorization.
        """
        self.source_ip = self._client_ip()
        auth = self.get_query_argument("authorization", None)
        try:
            useragent, key = self.decode_auth(auth)
        except (ValueError, UnicodeDecodeError) as e:
            LOG.warning(
                f"rejecting websocket from {self.source_ip or self.request.remote_ip}: "
                f"bad authorization ({e.__class__.__name__}: {e}) "
                f"raw={auth!r}"
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
            self.close()
            return

        self.client.name = f"{useragent}::{user.client_id}::{user.name}"
        self.client.crypto_key = user.crypto_key
        self.client.skill_blacklist = user.skill_blacklist or []
        self.client.intent_blacklist = user.intent_blacklist or []
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
            self.close()
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
        LOG.debug(f"disconnecting client: {self._peer_label(client.peer)}")
        self.hm_protocol.handle_client_disconnected(client)

    def check_origin(self, origin) -> bool:
        return True
