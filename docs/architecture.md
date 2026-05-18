# Architecture

## Transport overview

`HiveMindWebsocketProtocol` is a `NetworkProtocol` plugin loaded by
`hivemind-core` via the `hivemind.network.protocol` entry-point. Its `run()`
method (`__init__.py:61`) is the blocking server loop:

1. Resolve config and env vars for proxy CIDRs and trusted headers.
2. Build a Tornado `Application` with a single route `/ ->
   HiveMindTornadoWebSocket`, passing `trusted_networks` and
   `trusted_headers` in `Application.settings`.
3. Optionally wrap the listener in TLS (self-signed cert auto-generated if
   absent — `create_self_signed_cert()` at `__init__.py:113`).
4. Start the `IOLoop` (blocking).

## Handler lifecycle

`HiveMindTornadoWebSocket` (`__init__.py:161`) handles one WebSocket
connection per instance.

### `open()` — `__init__.py:211`

1. Resolve the real client IP via `_client_ip()` and store it as
   `self.source_ip`.
2. Read the `?authorization=` query parameter.
3. Decode it with `decode_auth()` — Base64, format `name:key` — and close
   with code `1008` on any decode error.
4. Look up the API key in `hm_protocol.db`. Close if not found.
5. Populate `HiveMindClientConnection` with permissions from the database
   record.
6. Verify crypto requirements. Close if crypto is required but unavailable.
7. Call `hm_protocol.handle_new_client()`.

### `on_message()` — `__init__.py:196`

Decodes the frame via `client.decode()`, logs with `_peer_label()`, and
dispatches to `hm_protocol.handle_message()`.

### `on_close()` — `__init__.py:287`

Guards against connections that never completed `open()` (unauthenticated
clients where `self.client` was never set), then calls
`hm_protocol.handle_client_disconnected()`.

## Authorization

Clients connect with a URL query parameter:

```
ws://host:port/?authorization=<base64(name:key)>
```

`decode_auth()` (`__init__.py:180`) decodes the Base64 value and splits on
the first `:`. Both `name` and `key` must be non-empty; otherwise the
connection is rejected with close code `1008`.

## IP resolution flow

`_client_ip()` (`__init__.py:171`) delegates to `resolve_client_ip()`
(`_client_ip.py:28`):

1. If `remote_ip` is `None` or not in any `trusted_networks` CIDR, return
   `remote_ip` unchanged.
2. Iterate `trusted_headers` in order. For each present header, split the
   value on commas and walk the list **right-to-left**.
3. Return the first candidate that is a valid IP address and is **not** in
   `trusted_networks`.
4. If all candidates are trusted (or the header is absent/malformed), fall
   back to `remote_ip`.

IPv4 and IPv6 are both handled. Tokens that are not valid IP addresses
(e.g. `unknown`, port-suffixed values) are silently skipped per RFC 7239
intent. `parse_networks()` (`_client_ip.py:10`) uses `strict=False` so host
bits in a CIDR are silently masked.

`trusted_networks` and `trusted_headers` are passed into the Tornado
`Application` settings at startup (`__init__.py:90-94`) and read by each
handler instance via `self.settings`.
