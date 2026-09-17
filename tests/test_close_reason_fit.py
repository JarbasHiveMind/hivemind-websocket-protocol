"""_fit_close_reason keeps a close reason inside one control frame.

A close frame's payload is a 2-byte code plus the UTF-8 reason, 125 bytes at
most (RFC 6455 §5.5), so the reason gets 123 bytes. The cut must not split a
multi-byte character, or the peer receives invalid UTF-8.
"""


def _fit(reason):
    from hivemind_websocket_protocol import _fit_close_reason
    return _fit_close_reason(reason)


def test_a_long_ascii_reason_is_cut_to_123_bytes():
    reason = "x" * 238
    assert _fit(reason) == "x" * 123


def test_a_cut_never_splits_a_multibyte_character():
    reason = "a" * 122 + "é" + "tail"  # é is 2 bytes, starting at byte 122
    fitted = _fit(reason)
    assert fitted == "a" * 122
    assert len(fitted.encode("utf-8")) <= 123


def test_a_reason_that_fits_is_unchanged():
    assert _fit("invalid api key") == "invalid api key"
    assert _fit("é" * 61) == "é" * 61  # 122 bytes


def test_empty_and_none_are_passed_through():
    assert _fit("") == ""
    assert _fit(None) is None


def test_a_bytes_reason_is_decoded_and_cut():
    # Tornado calls reason.encode(); bytes has no encode, so a bytes reason
    # raised AttributeError and the peer got no close frame.
    fitted = _fit(b"x" * 200)
    assert fitted == "x" * 123
    assert _fit("invalid".encode("utf-8")) == "invalid"


def test_a_bytes_reason_with_invalid_utf8_still_encodes():
    fitted = _fit(b"bad \xff byte")
    assert isinstance(fitted, str)
    fitted.encode("utf-8")


def test_a_lone_surrogate_does_not_raise():
    fitted = _fit("bad \udc80 surrogate")
    assert isinstance(fitted, str)
    assert len(fitted.encode("utf-8")) <= 123


def test_a_close_failure_inside_the_ioloop_callback_is_logged():
    from unittest.mock import patch
    from hivemind_websocket_protocol import HiveMindTornadoWebSocket

    handler = object.__new__(HiveMindTornadoWebSocket)

    def boom(code=None, reason=None):
        raise RuntimeError("close failed")

    handler.close = boom
    with patch("hivemind_websocket_protocol.LOG") as log:
        handler._close_in_callback(1008, "reason")  # must not raise
    assert log.warning.call_count == 1
    assert "close failed" in str(log.warning.call_args)
