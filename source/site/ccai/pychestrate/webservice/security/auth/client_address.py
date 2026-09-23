"""
.. module:: security.auth.client_address
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The client's real address (trusted-proxy aware) and a
               readable browser / OS summary, for the sessions page, the
               audit log, and the sign-in back-off.

.. moduleauthor:: Code Craft AI LLC

The sign-in handler took the client address straight from the
``X-Forwarded-For`` header, which any client can set, and the sessions
page then showed the SHA-256 of an empty string for every session
(audit ADM-16). This module resolves the address the way a reverse
proxy deployment needs:

* The *peer* is the socket address the request came from:
  ``REMOTE_ADDR`` from the WSGI environ. The request object the web
  framework builds does not carry the environ, so
  :func:`wrap_wsgi_app_with_peer_address` copies ``REMOTE_ADDR`` into a
  private header (overwriting anything a client sent under that name)
  before the framework parses the request.
* When the peer is a trusted proxy, the client is the right-most
  ``X-Forwarded-For`` entry that is not itself a trusted proxy -- the
  entry the proxy appended, which a client cannot forge -- or
  ``X-Real-IP`` when there is no usable ``X-Forwarded-For``. The
  trusted proxies are the ones the Secure-cookie policy trusts:
  ``PYCHESTRATE_TRUSTED_PROXY_ADDRESSES`` (see
  :mod:`webinterface.foundation.cookie_session`; unset means the
  loopback addresses, where the deployed nginx runs). With ``*``
  (trust every peer) the left-most entry, the original client, is
  used.
* Otherwise the peer is the client, and forwarding headers are
  ignored.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import ipaddress
import logging
import os
import re

from typing import Any, Callable, Optional, Tuple

from ccai.pychestrate.webservice.webinterface.foundation.cookie_session import (
    TRUSTED_PROXY_ADDRESSES_ENV_VAR,
    TrustedProxyPolicy,
    parse_trusted_proxy_addresses,
)


_module_logger = logging.getLogger(__name__)

#: Private request header carrying the socket peer address, set by
#: :func:`wrap_wsgi_app_with_peer_address`.
PEER_ADDRESS_HEADER: str = "X-Pychestrate-Peer-Address"
_PEER_ADDRESS_ENVIRON_KEY: str = "HTTP_X_PYCHESTRATE_PEER_ADDRESS"

#: Longest user-agent string kept on a session.
MAX_USER_AGENT_LENGTH: int = 512

_TRUST_NO_PROXY = TrustedProxyPolicy(trust_any=False, networks=())


def trusted_proxy_policy() -> TrustedProxyPolicy:
    """
        The trusted proxies, from ``PYCHESTRATE_TRUSTED_PROXY_ADDRESSES``
        (the same setting the Secure-cookie policy reads; unset means
        the loopback addresses). A malformed value trusts no proxy here
        -- the cookie policy refuses it at startup.

        :returns: The :class:`TrustedProxyPolicy`.
    """
    try:
        rtnval = parse_trusted_proxy_addresses(
            raw=os.environ.get(TRUSTED_PROXY_ADDRESSES_ENV_VAR, None)
        )
    except Exception:
        _module_logger.warning(
            "pychestrate.auth.client_address.bad_trusted_proxies variable=%s",
            TRUSTED_PROXY_ADDRESSES_ENV_VAR,
        )
        rtnval = _TRUST_NO_PROXY
    return rtnval


def _normalize_address(*, value: Any) -> Optional[str]:
    """
        A bare IP address from a header or environ value (strips an
        IPv6 ``[...]`` wrapper, an IPv4 ``:port`` suffix and an
        IPv4-mapped IPv6 prefix), or None when it is not an address.
    """
    if value is None:
        return None
    text = str(value).strip().strip('"')
    if len(text) == 0:
        return None
    if text.startswith("[") is True and "]" in text:
        text = text[1:text.index("]")]
    elif text.count(":") == 1 and "." in text:
        text = text.split(":", 1)[0]
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    rtnval = str(address)
    return rtnval


def _forwarded_hops(*, request: Any) -> list:
    """
        The ``X-Forwarded-For`` entries, left (client) to right (last
        proxy), each normalized to a bare address or None when it is
        not one.
    """
    forwarded = _header(request=request, name="X-Forwarded-For")
    if forwarded is None:
        return []
    rtnval = [
        _normalize_address(value=part)
        for part in str(forwarded).split(",")
        if len(part.strip()) > 0
    ]
    return rtnval


def _header(*, request: Any, name: str) -> Optional[str]:
    headers = getattr(request, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get(name, None)
        if value is None:
            value = headers.get(name.lower(), None)
    except Exception:
        return None
    return value


def peer_address(*, request: Any) -> Optional[str]:
    """
        The socket peer's address: ``REMOTE_ADDR`` from the request's
        WSGI scope when the framework keeps it, else the private header
        the WSGI wrapper sets, else the framework's own client field.

        :param request: Incoming webworks request.

        :returns: Address or None when unknown.
    """
    scope = getattr(request, "scope", None)
    if isinstance(scope, dict) is True:
        candidate = _normalize_address(value=scope.get("REMOTE_ADDR", None))
        if candidate is not None:
            return candidate
    candidate = _normalize_address(value=_header(request=request, name=PEER_ADDRESS_HEADER))
    if candidate is not None:
        return candidate
    candidate = _normalize_address(value=getattr(request, "remote_address", None))
    if candidate is not None:
        return candidate
    client = getattr(request, "client", None)
    if client is not None:
        candidate = _normalize_address(value=getattr(client, "host", None))
        if candidate is not None:
            return candidate
    return None


def resolve_client_address(
        *,
        request: Any,
        policy: Optional[TrustedProxyPolicy] = None
    ) -> str:
    """
        The client's address, honouring forwarding headers only when the
        request came through a trusted proxy.

        :param request: Incoming webworks request.
        :param policy: Trusted proxies (defaults to
                       :func:`trusted_proxy_policy`).

        :returns: The address, or ``""`` when it cannot be determined.
    """
    trusted = policy if policy is not None else trusted_proxy_policy()
    peer = peer_address(request=request)
    if peer is None:
        return ""
    if trusted.trusts(peer_address=peer) is False:
        return peer

    hops = _forwarded_hops(request=request)
    if trusted.trust_any is True:
        # Every hop is trusted, so the original client is the left-most
        # entry.
        if len(hops) > 0 and hops[0] is not None:
            return hops[0]
    else:
        for address in reversed(hops):
            if address is None:
                # A malformed hop: stop rather than trust what is left
                # of it (it came from beyond the last trusted proxy).
                break
            if trusted.trusts(peer_address=address) is True:
                continue
            return address

    real_ip = _normalize_address(value=_header(request=request, name="X-Real-IP"))
    if real_ip is not None:
        return real_ip
    return peer


def request_user_agent(*, request: Any) -> str:
    """
        The request's ``User-Agent`` header, bounded.

        :param request: Incoming webworks request.

        :returns: The header value (``""`` when absent).
    """
    value = _header(request=request, name="User-Agent")
    if value is None:
        return ""
    rtnval = str(value)[:MAX_USER_AGENT_LENGTH]
    return rtnval


_BROWSER_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"Edg(?:e|A|iOS)?/(\d+)", "Edge"),
    (r"OPR/(\d+)", "Opera"),
    (r"Firefox/(\d+)", "Firefox"),
    (r"FxiOS/(\d+)", "Firefox"),
    (r"CriOS/(\d+)", "Chrome"),
    (r"Chrome/(\d+)", "Chrome"),
    (r"Version/(\d+)[.\d]* (?:Mobile/\S+ )?Safari/", "Safari"),
    (r"pychestrate-client/([\d.]+)", "pychestrate-client"),
    (r"pyc/([\d.]+)", "pyc"),
    (r"curl/([\d.]+)", "curl"),
    (r"python-requests/([\d.]+)", "python-requests"),
)

_OS_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"Windows NT", "Windows"),
    (r"iPhone", "iOS"),
    (r"iPad", "iPadOS"),
    (r"Mac OS X|Macintosh", "macOS"),
    (r"Android", "Android"),
    (r"CrOS", "ChromeOS"),
    (r"Linux", "Linux"),
)


def describe_user_agent(*, user_agent: Optional[str]) -> str:
    """
        A short readable summary of a ``User-Agent`` string, such as
        ``"Chrome 128 on macOS"``.

        :param user_agent: The header value.

        :returns: Summary (``""`` for an empty value; the first words of
                  an unrecognised value).
    """
    if user_agent is None:
        return ""
    text = str(user_agent).strip()
    if len(text) == 0:
        return ""

    browser = None
    if "HeadlessChrome/" in text:
        match = re.search(r"HeadlessChrome/(\d+)", text)
        browser = "Headless Chrome {}".format(match.group(1)) if match is not None else "Headless Chrome"
    else:
        for pattern, name in _BROWSER_PATTERNS:
            match = re.search(pattern, text)
            if match is not None:
                browser = "{} {}".format(name, match.group(1))
                break

    os_name = None
    for pattern, name in _OS_PATTERNS:
        if re.search(pattern, text) is not None:
            os_name = name
            break

    if browser is not None and os_name is not None:
        rtnval = "{} on {}".format(browser, os_name)
        return rtnval
    if browser is not None:
        return browser
    if os_name is not None:
        rtnval = "Unknown browser on {}".format(os_name)
        return rtnval
    rtnval = text[:40]
    return rtnval


def wrap_wsgi_app_with_peer_address(app: Callable[..., Any]) -> Callable[..., Any]:
    """
        WSGI middleware that exposes the socket peer (``REMOTE_ADDR``)
        to request handlers through :data:`PEER_ADDRESS_HEADER`. The
        header is always overwritten, so a client cannot supply it.

        :param app: The WSGI application.

        :returns: The wrapped WSGI application.
    """

    def _with_peer_address(environ: dict, start_response: Callable[..., Any]) -> Any:
        environ[_PEER_ADDRESS_ENVIRON_KEY] = str(environ.get("REMOTE_ADDR", "") or "")
        return app(environ, start_response)

    return _with_peer_address


__all__ = [
    "MAX_USER_AGENT_LENGTH",
    "PEER_ADDRESS_HEADER",
    "describe_user_agent",
    "peer_address",
    "request_user_agent",
    "resolve_client_address",
    "trusted_proxy_policy",
    "wrap_wsgi_app_with_peer_address",
]
