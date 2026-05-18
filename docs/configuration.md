# Configuration Reference

Configuration is supplied as a dict to `HiveMindWebsocketProtocol(config={...})`.
Dict keys always take precedence over environment variables.

## Connection

| Key | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | `0.0.0.0` | Bind address. Falls back to `identity.default_master`. |
| `port` | `int` | `5678` | Listen port. Falls back to `identity.default_port`. |
| `ssl` | `bool` | `false` | Enable TLS. |
| `cert_dir` | `str` | `$XDG_DATA_HOME/hivemind` | Directory for TLS cert and key files. |
| `cert_name` | `str` | `hivemind` | Base filename; produces `<name>.crt` and `<name>.key`. |

When `ssl=true` and the key file does not exist, a self-signed 2048-bit RSA
certificate valid for 10 years is generated automatically.
`HiveMindWebsocketProtocol.create_self_signed_cert()` — `__init__.py:113`

## Trusted-proxy IP resolution

| Key | Env var | Default | Description |
|---|---|---|---|
| `trusted_proxy_cidrs` | `HIVEMIND_TRUSTED_PROXY_CIDRS` | _(none — feature disabled)_ | Comma-separated CIDR ranges of trusted proxy addresses. |
| `trusted_client_ip_headers` | `HIVEMIND_TRUSTED_CLIENT_IP_HEADERS` | `x-forwarded-for,x-real-ip` | Ordered comma-separated list of headers to inspect. |

Both keys accept a `str`, `list`, or `tuple`; env vars accept a
comma-separated string. The feature is inactive unless at least one CIDR is
configured — when `trusted_proxy_cidrs` is empty or absent, headers are never
consulted and the raw `remote_ip` is used as-is.

Supplying an explicit empty list (`trusted_proxy_cidrs: []`) in the config
dict disables the feature even if the env var is set. The config key presence
is checked with `in`, not truthiness — `__init__.py:67-70`.

### Header inspection order

Headers in `trusted_client_ip_headers` are inspected left-to-right; the
first header present with a usable value wins. Within a single
`X-Forwarded-For` chain the walk is right-to-left (rightmost hop is the
closest proxy), and the first address that is not itself in a trusted CIDR is
returned.

See [architecture.md](architecture.md#ip-resolution-flow) for the full
algorithm.

### Example — nginx reverse proxy on localhost

```bash
HIVEMIND_TRUSTED_PROXY_CIDRS=127.0.0.1/32
HIVEMIND_TRUSTED_CLIENT_IP_HEADERS=x-forwarded-for
```

### Example — internal private network proxies

```python
config = {
    "trusted_proxy_cidrs": ["10.0.0.0/8", "192.168.0.0/16"],
    "trusted_client_ip_headers": ["x-forwarded-for", "x-real-ip"],
}
```
