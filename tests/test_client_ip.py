from hivemind_websocket_protocol._client_ip import (
    parse_networks,
    resolve_client_ip,
)


TRUSTED = parse_networks(["10.0.0.0/8", "192.168.0.0/16"])
HEADERS = ("x-forwarded-for", "x-real-ip")


def test_parse_networks_skips_invalid():
    nets = parse_networks(["10.0.0.0/8", "not-a-cidr", "192.168.0.0/16"])
    assert len(nets) == 2


def test_returns_remote_ip_when_no_trusted_networks():
    assert resolve_client_ip("1.2.3.4", {}, (), HEADERS) == "1.2.3.4"


def test_returns_remote_ip_when_peer_not_trusted():
    headers = {"x-forwarded-for": "8.8.8.8"}
    assert resolve_client_ip("1.2.3.4", headers, TRUSTED, HEADERS) == "1.2.3.4"


def test_trusted_peer_uses_xff_header():
    headers = {"x-forwarded-for": "8.8.8.8"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "8.8.8.8"


def test_xff_chain_walked_right_to_left_skipping_trusted():
    headers = {"x-forwarded-for": "8.8.8.8, 192.168.1.1, 10.0.0.5"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "8.8.8.8"


def test_xff_chain_all_trusted_falls_back_to_remote():
    headers = {"x-forwarded-for": "10.0.0.5, 192.168.1.1"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "10.0.0.5"


def test_falls_back_to_next_header_when_first_missing():
    headers = {"x-real-ip": "8.8.8.8"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "8.8.8.8"


def test_bad_ip_in_header_is_skipped():
    # bad value is not in any network, so it's returned as-is
    # (we trust upstream proxies; validation is their job)
    headers = {"x-forwarded-for": "not-an-ip"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "not-an-ip"


def test_empty_header_falls_back():
    headers = {"x-forwarded-for": "   "}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "10.0.0.5"


def test_none_remote_ip():
    assert resolve_client_ip(None, {}, TRUSTED, HEADERS) is None


def test_ipv6_trusted_chain():
    trusted = parse_networks(["fd00::/8"])
    headers = {"x-forwarded-for": "2001:db8::1, fd00::5"}
    assert resolve_client_ip("fd00::5", headers, trusted, HEADERS) == "2001:db8::1"
