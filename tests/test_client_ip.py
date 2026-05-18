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


# --- Header precedence ---------------------------------------------------

def test_xff_preferred_over_real_ip_when_both_present():
    headers = {"x-forwarded-for": "8.8.8.8", "x-real-ip": "9.9.9.9"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "8.8.8.8"


def test_falls_through_to_real_ip_when_xff_all_trusted():
    headers = {"x-forwarded-for": "10.0.0.1, 192.168.1.1", "x-real-ip": "9.9.9.9"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "9.9.9.9"


def test_header_order_respects_config_tuple():
    headers = {"x-forwarded-for": "8.8.8.8", "x-real-ip": "9.9.9.9"}
    reordered = ("x-real-ip", "x-forwarded-for")
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, reordered) == "9.9.9.9"


def test_empty_trusted_headers_falls_back_to_remote():
    headers = {"x-forwarded-for": "8.8.8.8"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, ()) == "10.0.0.5"


# --- Chain parsing -------------------------------------------------------

def test_single_ip_no_chain():
    headers = {"x-forwarded-for": "8.8.8.8"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "8.8.8.8"


def test_chain_with_extra_whitespace():
    headers = {"x-forwarded-for": "  8.8.8.8 ,   192.168.1.1  ,  10.0.0.5  "}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "8.8.8.8"


def test_chain_with_empty_entries():
    headers = {"x-forwarded-for": "8.8.8.8,,,10.0.0.5"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "8.8.8.8"


def test_chain_with_trailing_comma():
    headers = {"x-forwarded-for": "8.8.8.8,"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "8.8.8.8"


# --- CIDR boundaries -----------------------------------------------------

def test_cidr_lower_boundary_inclusive():
    headers = {"x-forwarded-for": "8.8.8.8"}
    assert resolve_client_ip("10.0.0.0", headers, TRUSTED, HEADERS) == "8.8.8.8"


def test_cidr_upper_boundary_inclusive():
    headers = {"x-forwarded-for": "8.8.8.8"}
    assert resolve_client_ip("10.255.255.255", headers, TRUSTED, HEADERS) == "8.8.8.8"


def test_just_outside_cidr_not_trusted():
    headers = {"x-forwarded-for": "8.8.8.8"}
    # 11.0.0.0 is outside 10.0.0.0/8
    assert resolve_client_ip("11.0.0.0", headers, TRUSTED, HEADERS) == "11.0.0.0"


def test_single_host_cidr():
    trusted = parse_networks(["172.16.0.1/32"])
    headers = {"x-forwarded-for": "8.8.8.8"}
    assert resolve_client_ip("172.16.0.1", headers, trusted, HEADERS) == "8.8.8.8"
    assert resolve_client_ip("172.16.0.2", headers, trusted, HEADERS) == "172.16.0.2"


def test_loopback_not_trusted_by_default():
    headers = {"x-forwarded-for": "8.8.8.8"}
    assert resolve_client_ip("127.0.0.1", headers, TRUSTED, HEADERS) == "127.0.0.1"


# --- IPv6 / mixed --------------------------------------------------------

def test_ipv6_peer_with_ipv4_chain():
    trusted = parse_networks(["fd00::/8", "10.0.0.0/8"])
    headers = {"x-forwarded-for": "8.8.8.8, 10.0.0.5"}
    assert resolve_client_ip("fd00::5", headers, trusted, HEADERS) == "8.8.8.8"


def test_ipv4_peer_with_ipv6_chain():
    trusted = parse_networks(["10.0.0.0/8", "fd00::/8"])
    headers = {"x-forwarded-for": "2001:db8::1, fd00::5"}
    assert resolve_client_ip("10.0.0.5", headers, trusted, HEADERS) == "2001:db8::1"


def test_ipv6_loopback_not_trusted_by_default():
    headers = {"x-forwarded-for": "8.8.8.8"}
    assert resolve_client_ip("::1", headers, TRUSTED, HEADERS) == "::1"


def test_ipv6_compressed_form_normalized_by_ipaddress():
    # 2001:db8:0:0::1 collapses to 2001:db8::1 inside the trust check
    trusted = parse_networks(["2001:db8::/32"])
    headers = {"x-forwarded-for": "8.8.8.8"}
    assert resolve_client_ip("2001:db8:0:0:0:0:0:5", headers, trusted, HEADERS) == "8.8.8.8"


# --- Misc / defensive ----------------------------------------------------

def test_empty_string_remote_ip():
    assert resolve_client_ip("", {}, TRUSTED, HEADERS) == ""


def test_malformed_remote_ip():
    # garbage peer can't be in any network -> headers ignored, returned as-is
    headers = {"x-forwarded-for": "8.8.8.8"}
    assert resolve_client_ip("not-an-ip", headers, TRUSTED, HEADERS) == "not-an-ip"


def test_port_suffixed_xff_returned_verbatim():
    # We don't normalize header values; if a proxy appends a port, it's on them.
    # Documenting actual behaviour so a future change is intentional.
    headers = {"x-forwarded-for": "8.8.8.8:443"}
    assert resolve_client_ip("10.0.0.5", headers, TRUSTED, HEADERS) == "8.8.8.8:443"


def test_overlapping_cidrs():
    # smaller range nested in larger; both treated as trusted
    trusted = parse_networks(["10.0.0.0/8", "10.1.0.0/16"])
    headers = {"x-forwarded-for": "8.8.8.8, 10.1.0.1, 10.2.0.1"}
    assert resolve_client_ip("10.0.0.5", headers, trusted, HEADERS) == "8.8.8.8"


def test_long_chain():
    chain = ", ".join(["10.0.0." + str(i) for i in range(1, 20)] + ["8.8.8.8"][::-1])
    # 19 trusted hops then one client (leftmost)
    chain = "8.8.8.8, " + ", ".join("10.0.0." + str(i) for i in range(1, 20))
    headers = {"x-forwarded-for": chain}
    assert resolve_client_ip("10.0.0.20", headers, TRUSTED, HEADERS) == "8.8.8.8"


def test_parse_networks_accepts_host_bits_set():
    # strict=False allows 10.0.0.5/8 -> 10.0.0.0/8
    nets = parse_networks(["10.0.0.5/8"])
    assert len(nets) == 1
    assert str(nets[0]) == "10.0.0.0/8"


def test_parse_networks_empty():
    assert parse_networks([]) == ()


def test_parse_networks_skips_blank_strings():
    # Real-world: env var with empty value
    nets = parse_networks(["10.0.0.0/8", "", "  "])
    # ip_network rejects "" and "  " -> warnings, but we get the valid one
    assert len(nets) == 1
