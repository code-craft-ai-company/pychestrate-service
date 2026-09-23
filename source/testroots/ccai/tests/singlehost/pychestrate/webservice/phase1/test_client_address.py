"""
.. module:: test_client_address
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the trusted-proxy-aware client address and the
               readable User-Agent summary (security.auth.client_address).

.. moduleauthor:: Code Craft AI LLC

The sign-in handler took the client address from the raw
``X-Forwarded-For`` header (spoofable), and the sessions page showed a
hash of an empty string for every session (audit ADM-16). Each test
pins one rule of the resolver or the summary.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.security.auth.client_address import (
    PEER_ADDRESS_HEADER,
    describe_user_agent,
    resolve_client_address,
    wrap_wsgi_app_with_peer_address,
)
from ccai.pychestrate.webservice.webinterface.foundation.cookie_session import (
    parse_trusted_proxy_addresses,
)


class _Headers:
    def __init__(self, values: Dict[str, str]) -> None:
        self._values = {key.lower(): value for key, value in values.items()}
        return

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        rtnval = self._values.get(key.lower(), default)
        return rtnval


class _Request:
    def __init__(self, headers: Dict[str, str]) -> None:
        self.headers = _Headers(headers)
        self.scope = {}
        return


#: The default: the loopback addresses (PYCHESTRATE_TRUSTED_PROXY_ADDRESSES unset).
_LOOPBACK = parse_trusted_proxy_addresses(raw=None)


def test_an_untrusted_peer_is_the_client_whatever_it_forwards():
    """
    **Feature: client address (ADM-16)**
    **Property: a request that does not come from a trusted proxy is
    attributed to its socket peer; its X-Forwarded-For is ignored.**
    """
    request = _Request({PEER_ADDRESS_HEADER: "203.0.113.9", "X-Forwarded-For": "10.1.2.3"})
    testbase.assert_equal(
        resolve_client_address(request=request, policy=_LOOPBACK), "203.0.113.9"
    )
    return


def test_a_trusted_proxy_hop_is_resolved_to_the_entry_it_appended():
    """
    **Feature: client address (ADM-16)**
    **Property: behind a trusted proxy the client is the right-most
    X-Forwarded-For entry (the one the proxy added), not a value the
    client put further left.**
    """
    request = _Request({
        PEER_ADDRESS_HEADER: "127.0.0.1",
        "X-Forwarded-For": "6.6.6.6, 198.51.100.7",
    })
    testbase.assert_equal(
        resolve_client_address(request=request, policy=_LOOPBACK), "198.51.100.7"
    )
    return


def test_trusted_hops_are_skipped():
    """
    **Feature: client address (ADM-16)**
    **Property: entries from further trusted proxies are skipped, so a
    chain of internal proxies still resolves to the client.**
    """
    networks = parse_trusted_proxy_addresses(raw="127.0.0.1,10.0.0.0/8")
    request = _Request({
        PEER_ADDRESS_HEADER: "127.0.0.1",
        "X-Forwarded-For": "198.51.100.7, 10.0.0.5",
    })
    testbase.assert_equal(
        resolve_client_address(request=request, policy=networks), "198.51.100.7"
    )
    return


def test_a_trusted_proxy_without_forwarded_for_falls_back_to_x_real_ip():
    """
    **Feature: client address (ADM-16)**
    **Property: behind a trusted proxy that sets only X-Real-IP, that
    address is used.**
    """
    request = _Request({PEER_ADDRESS_HEADER: "127.0.0.1", "X-Real-IP": "192.0.2.44"})
    testbase.assert_equal(
        resolve_client_address(request=request, policy=_LOOPBACK), "192.0.2.44"
    )
    return


def test_an_unknown_peer_yields_no_address():
    """
    **Feature: client address (ADM-16)**
    **Property: when the peer cannot be determined the address is
    empty -- a bare X-Forwarded-For is never trusted.**
    """
    request = _Request({"X-Forwarded-For": "198.51.100.7"})
    testbase.assert_equal(
        resolve_client_address(request=request, policy=_LOOPBACK), ""
    )
    return


def test_trusting_every_peer_takes_the_original_client():
    """
    **Feature: client address (ADM-16)**
    **Property: with PYCHESTRATE_TRUSTED_PROXY_ADDRESSES="*" every hop
    is trusted, so the client is the left-most X-Forwarded-For entry.**
    """
    request = _Request({
        PEER_ADDRESS_HEADER: "203.0.113.9",
        "X-Forwarded-For": "198.51.100.7, 10.0.0.5",
    })
    testbase.assert_equal(
        resolve_client_address(request=request, policy=parse_trusted_proxy_addresses(raw="*")),
        "198.51.100.7",
    )
    return


def test_the_wsgi_wrapper_overwrites_a_client_supplied_peer_header():
    """
    **Feature: client address (ADM-16)**
    **Property: the WSGI wrapper replaces any client-sent peer header
    with REMOTE_ADDR, so the peer cannot be forged.**
    """
    seen = {}

    def _inner(environ, start_response):
        seen["peer"] = environ.get("HTTP_X_PYCHESTRATE_PEER_ADDRESS")
        return []

    wrapped = wrap_wsgi_app_with_peer_address(_inner)
    wrapped({"REMOTE_ADDR": "203.0.113.9", "HTTP_X_PYCHESTRATE_PEER_ADDRESS": "127.0.0.1"}, None)
    testbase.assert_equal(seen["peer"], "203.0.113.9")
    return


def test_chrome_on_macos_is_summarized():
    """
    **Feature: client address (ADM-16)**
    **Property: a desktop Chrome User-Agent reads as "Chrome <major> on
    macOS".**
    """
    agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    testbase.assert_equal(describe_user_agent(user_agent=agent), "Chrome 128 on macOS")
    return


def test_edge_on_windows_is_not_reported_as_chrome():
    """
    **Feature: client address (ADM-16)**
    **Property: Edge (which also says Chrome) reads as Edge.**
    """
    agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like "
        "Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.2739.42"
    )
    testbase.assert_equal(describe_user_agent(user_agent=agent), "Edge 128 on Windows")
    return


def test_firefox_on_linux_is_summarized():
    """
    **Feature: client address (ADM-16)**
    **Property: a Firefox User-Agent reads as "Firefox <major> on
    Linux".**
    """
    agent = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
    testbase.assert_equal(describe_user_agent(user_agent=agent), "Firefox 130 on Linux")
    return
