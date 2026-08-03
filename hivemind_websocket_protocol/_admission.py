"""Shared admission logic for every websocket backend.

Both the Tornado backend and the webrockets backend admit clients the same
way: decode the base64 ``name:key`` authorization, look the key up in the
database, and build the :class:`HiveMindClientConnection`. That policy lives
here so there is exactly one definition of who gets in.

The backends keep the transport-specific parts — how the connection is
closed, and whatever address information the transport can offer.
"""
from typing import Callable, Optional, Tuple

import pybase64
from hivemind_core.protocol import (
    HiveMindClientConnection,
    HiveMindListenerProtocol,
    HiveMindNodeType,
)
from hivemind_plugin_manager.database import Client
from ovos_bus_client.session import Session
from ovos_utils.log import LOG
from poorman_handshake import PasswordHandShake

try:
    from hivemind_core.config import runtime_password_min_bits
except ImportError:  # released hivemind-core without the helper
    import os

    def runtime_password_min_bits():
        return 0.0 if os.environ.get("HIVEMIND_DISABLE_PASSWORD_STRENGTH_CHECK", "").strip().lower() in ("1", "true", "yes", "on") else 40.0


class ClientRejected(Exception):
    """An authenticated-looking client was refused after inspection.

    The listener protocol has already been notified; the backend only has to
    close the socket. ``client`` is exposed because the Tornado backend has
    to attach it to the handler before closing, so that the disconnect
    bookkeeping still sees it.
    """

    def __init__(self, client: HiveMindClientConnection):
        super().__init__(client.name)
        self.client = client


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


def authorize_client(useragent: str, key: str,
                     hm_protocol: HiveMindListenerProtocol,
                     send_msg: Callable[[str, bool], None],
                     disconnect: Callable[[], None]) -> HiveMindClientConnection:
    """
    Build the client connection for a peer that presented valid credentials.

    Args:
        useragent (str): The name half of the decoded authorization.
        key (str): The api key half of the decoded authorization.
        hm_protocol (HiveMindListenerProtocol): The listener to attach to.
        send_msg (Callable[[str, bool], None]): Transport send callback.
        disconnect (Callable[[], None]): Transport close callback.

    Returns:
        HiveMindClientConnection: The admitted client.

    Raises:
        ClientRejected: The api key is unknown, or crypto is required but the
            client cannot provide it.
    """
    client = HiveMindClientConnection(
        key=key,
        disconnect=disconnect,
        send_msg=send_msg,
        sess=Session(session_id="default"),  # will be re-assigned once client sends handshake
        name=useragent,
        hm_protocol=hm_protocol
    )
    hm_protocol.db.sync()
    user: Client = hm_protocol.db.get_client_by_api_key(key)

    if not user:
        LOG.error("Client provided an invalid api key")
        hm_protocol.handle_invalid_key_connected(client)
        raise ClientRejected(client)

    client.name = f"{useragent}::{user.client_id}::{user.name}"
    client.crypto_key = user.crypto_key
    client.skill_blacklist = user.skill_blacklist or []
    client.intent_blacklist = user.intent_blacklist or []
    client.allowed_types = user.allowed_types
    client.can_broadcast = user.can_broadcast
    client.can_propagate = user.can_propagate
    client.can_escalate = user.can_escalate
    client.is_admin = user.is_admin
    if user.password:
        # pre-shared password to derive aes_key
        client.pswd_handshake = PasswordHandShake(user.password, min_bits=runtime_password_min_bits())

    client.node_type = HiveMindNodeType.NODE  # TODO . placeholder

    if (
            not client.crypto_key
            and not hm_protocol.handshake_enabled
            and hm_protocol.require_crypto
    ):
        LOG.error(
            "No pre-shared crypto key for client and handshake disabled, "
            "but configured to require crypto!"
        )
        # clients requiring handshake support might fail here
        hm_protocol.handle_invalid_protocol_version(client)
        raise ClientRejected(client)

    return client
