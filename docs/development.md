# Development

## Project layout

```
hivemind_websocket_protocol/
    __init__.py             # HiveMindWebsocketProtocol, HiveMindTornadoWebSocket
    _admission.py           # decode_auth(), authorize_client() — shared by both backends
    _client_ip.py           # parse_networks(), resolve_client_ip()
    webrockets_backend.py   # HiveMindWebrocketsProtocol (optional extra)
    version.py              # VERSION_MAJOR / MINOR / BUILD / ALPHA constants
tests/
    test_client_ip.py       # unit tests for IP resolution logic (~50 cases)
    test_decode_auth.py     # unit tests for Base64 auth decoding
    test_admission.py       # unit tests for the shared admission logic
    test_webrockets_query.py # unit tests for webrockets query-string parsing
    e2e/                    # end-to-end tests (require a running hivemind-core)
```

## Running tests

```bash
pip install pytest
pytest tests/
```

The unit tests in `test_client_ip.py` and `test_decode_auth.py` have no
network dependencies and run offline. The `e2e/` suite requires a live
`hivemind-core` instance.

## Entry-point

The plugin registers under the `hivemind.network.protocol` group:

```
hivemind-websocket-plugin  = hivemind_websocket_protocol:HiveMindWebsocketProtocol
hivemind-webrockets-plugin = hivemind_websocket_protocol.webrockets_backend:HiveMindWebrocketsProtocol
```

The second entry-point is the optional webrockets backend. It only starts if the
`webrockets` extra is installed; its e2e tests skip otherwise.

`hivemind-core` discovers and instantiates it automatically via
`hivemind-plugin-manager`.

---
[← Configuration](configuration.md) · [Home](index.md) · [Operations →](operations.md)
