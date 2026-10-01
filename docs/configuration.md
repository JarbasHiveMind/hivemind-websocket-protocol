# Configuration Reference

Configuration is passed as a dict in the `hivemind-websocket-plugin` block of
`~/.config/hivemind-core/server.json`. Dict keys always take precedence over
environment variables.

## Connection

| Key | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | `0.0.0.0` | Bind address. Falls back to `identity.default_master`. |
| `port` | `int` | `5678` | Listen port. Falls back to `identity.default_port`. |
| `ssl` | `bool` | `false` | Enable TLS (`wss://`). |
| `cert_dir` | `str` | `$XDG_DATA_HOME/hivemind` | Directory for TLS cert/key files. |
| `cert_name` | `str` | `hivemind` | Base filename. It produces `<name>.crt` and `<name>.key`. |

When `ssl=true` and the key file does not exist, a self-signed 2048-bit RSA
certificate valid for 10 years is generated automatically.

There is no `module` key in `network_protocol`. `hivemind-core` reads every key of that
block as a plugin entry-point name and starts each one, so a `"module"` key is looked up
as a plugin named `module`; that entry fails to load and is logged, and the server
still starts as long as another transport loads. `agent_protocol`, `binary_protocol` and
`database` do use a `module` selector; this block does not.

## Keepalive

| Key | Env var | Default | Description |
|---|---|---|---|
| `websocket_ping_interval` | `HIVEMIND_WEBSOCKET_PING_INTERVAL` | `30.0` | Seconds between Tornado WebSocket keepalive pings. `0` disables them. |
| `websocket_ping_timeout` | `HIVEMIND_WEBSOCKET_PING_TIMEOUT` | `20.0` | Seconds to wait for a pong before Tornado closes the connection. |

Both accept a number or a numeric string. A negative, non-finite or unparsable value is
ignored with a warning and the default is used. These pings are Tornado's WebSocket-level
keepalive; they are unrelated to the HiveMind `PING` message.

## Trusted-proxy IP resolution

| Key | Env var | Default | Description |
|---|---|---|---|
| `trusted_proxy_cidrs` | `HIVEMIND_TRUSTED_PROXY_CIDRS` | _(none, feature disabled)_ | Comma-separated CIDRs of trusted proxy addresses. |
| `trusted_client_ip_headers` | `HIVEMIND_TRUSTED_CLIENT_IP_HEADERS` | `x-forwarded-for,x-real-ip` | Ordered list of headers to inspect for the real client IP. |

Both keys accept a `str`, `list`, or `tuple`. Env vars accept comma-separated
strings. The feature is **inactive** unless at least one CIDR is configured.

When inactive, `remote_ip` from the Tornado request is used as-is.

### Example: nginx on localhost

```bash
export HIVEMIND_TRUSTED_PROXY_CIDRS="127.0.0.1/32"
export HIVEMIND_TRUSTED_CLIENT_IP_HEADERS="x-forwarded-for"
```

### Example: private network proxies via config

```json
{
  "network_protocol": {
    "hivemind-websocket-plugin": {
      "trusted_proxy_cidrs": ["10.0.0.0/8", "192.168.0.0/16"],
      "trusted_client_ip_headers": ["x-forwarded-for", "x-real-ip"]
    }
  }
}
```

See [architecture.md](architecture.md#ip-resolution-flow) for the full algorithm.

## Full example

```json
{
  "network_protocol": {
    "hivemind-websocket-plugin": {
      "host": "0.0.0.0",
      "port": 5678,
      "ssl": true,
      "cert_dir": "/etc/hivemind/ssl",
      "cert_name": "hivemind",
      "trusted_proxy_cidrs": ["127.0.0.1/32"],
      "trusted_client_ip_headers": ["x-forwarded-for"],
      "websocket_ping_interval": 30.0,
      "websocket_ping_timeout": 20.0
    }
  }
}
```

---
[← Architecture](architecture.md) · [Home](index.md) · [Development →](development.md)
