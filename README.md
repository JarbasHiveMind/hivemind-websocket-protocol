# HiveMind WebSocket Protocol

WebSocket transport for HiveMind messages. This is the reference network
protocol implementation; the `hivemind-core` plugin system allows it to be
replaced with any other transport.

## Install

```bash
pip install hivemind-websocket-protocol
```

## Quick Start

The package registers itself as a `hivemind.network.protocol` entry-point
(`hivemind-websocket-plugin`). `hivemind-core` loads it automatically; you do
not instantiate `HiveMindWebsocketProtocol` directly in normal usage.

## Configuration

Pass a config dict when constructing `HiveMindWebsocketProtocol`, or set the
corresponding environment variables. Config dict keys take precedence over env
vars.

### Connection

| Config key | Env var | Default | Description |
|---|---|---|---|
| `host` | — | `0.0.0.0` | Bind address (falls back to identity `default_master`) |
| `port` | — | `5678` | Listen port (falls back to identity `default_port`) |
| `ssl` | — | `false` | Enable TLS (`wss://`). A self-signed cert is generated if none exists. |
| `cert_dir` | — | `$XDG_DATA_HOME/hivemind` | Directory for TLS cert/key files |
| `cert_name` | — | `hivemind` | Base name for `<cert_name>.crt` / `<cert_name>.key` |

### Trusted-proxy IP resolution

When HiveMind runs behind a reverse proxy, the real client IP must be read
from a forwarded header. These options are ignored (headers never consulted)
unless the direct peer address falls inside a configured CIDR.

| Config key | Env var | Default | Description |
|---|---|---|---|
| `trusted_proxy_cidrs` | `HIVEMIND_TRUSTED_PROXY_CIDRS` | _(none)_ | Comma-separated CIDRs of trusted proxy addresses |
| `trusted_client_ip_headers` | `HIVEMIND_TRUSTED_CLIENT_IP_HEADERS` | `x-forwarded-for,x-real-ip` | Ordered list of headers to inspect |

Both config keys accept a string (`"10.0.0.0/8,192.168.0.0/16"`), a list, or
a tuple. The env vars accept comma-separated strings.

See [docs/configuration.md](docs/configuration.md) for the full reference and
[docs/architecture.md](docs/architecture.md) for the IP-resolution algorithm.

## License

Apache-2.0
