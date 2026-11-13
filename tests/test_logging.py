

def test_the_authorization_query_parameter_never_reaches_a_log():
    """The credential travels as a query parameter, so both log paths redact.

    `open()` reads it with `get_query_argument("authorization")`. Tornado's
    default request summary is `method uri (remote_ip)`, and its exception
    logger prints `self.request`, whose `__repr__` includes the URI -- so
    without both overrides every connection, and every uncaught exception,
    wrote `?authorization=<base64(name:key)>` to the log.
    """
    from unittest.mock import MagicMock

    import hivemind_websocket_protocol as module
    from hivemind_websocket_protocol import HiveMindTornadoWebSocket

    secret = "c2VjcmV0OnRva2Vu"
    handler = HiveMindTornadoWebSocket.__new__(HiveMindTornadoWebSocket)
    handler.request = MagicMock()
    handler.request.method = "GET"
    handler.request.path = "/"
    handler.request.remote_ip = "203.0.113.7"
    handler.request.uri = f"/?authorization={secret}"
    handler.request.__repr__ = lambda _self: f"HTTPServerRequest(uri='/?authorization={secret}')"

    summary = handler._request_summary()
    assert secret not in summary, summary
    assert "authorization" not in summary, summary

    records = []

    class _Recorder:
        def error(self, message, *args):
            records.append(message % args if args else message)

    original = module.LOG
    module.LOG = _Recorder()
    try:
        handler.log_exception(ValueError, ValueError("boom"), None)
    finally:
        module.LOG = original

    assert records, "the exception was not logged at all"
    joined = "\n".join(records)
    assert secret not in joined, joined
    assert "authorization" not in joined, joined
