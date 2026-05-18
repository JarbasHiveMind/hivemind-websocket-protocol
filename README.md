# HiveMind Websockets protocol

Transport HiveMessages via websockets

This is the reference implementation of HiveMind, but you can theoretically replace websockets with anything

## Trusted client IPs

When the listener runs behind a proxy, it can log the real client IP from a
trusted header:

```shell
HIVEMIND_TRUSTED_PROXY_CIDRS=10.42.0.0/16
HIVEMIND_TRUSTED_CLIENT_IP_HEADERS=x-hivemind-client-ip
```

The header is only used when the direct connection comes from a trusted proxy
CIDR. The proxy should strip any incoming copy of the header and set it itself.
