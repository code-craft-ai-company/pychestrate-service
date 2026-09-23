"""
.. module:: webinterface.foundation.cookie_session
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HMAC-signed cookie-backed session for the
               consumer web UI.

.. moduleauthor:: Code Craft AI LLC

The consumer web UI uses an HMAC-signed cookie to carry the
user_id, session token, CSRF token, and one-time flash messages
between requests. This module owns that cookie format for the
webworks routes:

* :func:`sign_session_payload` -- serialize a dict to a
  base64url-encoded ``payload.signature`` cookie value, signed
  with HMAC-SHA256 using the operator-supplied secret.

* :func:`verify_session_payload` -- read a cookie value, verify
  the signature, and return the decoded dict; returns
  ``None`` on tamper / missing signature / invalid base64 /
  malformed shape.

The cookie is **signed but not encrypted**. CSRF tokens, flash
messages, and the resolved user_id all sit safely in the clear
because the threat model is "no tampering" not "no readable
contents". Anything sensitive (passwords, raw secrets) does NOT
go in the session cookie.

Cookie hygiene
--------------

The session cookie is written ``HttpOnly`` + ``SameSite=Lax``. The
``Secure`` attribute follows one rule for every cookie the service
sets, enforced by :func:`wrap_wsgi_app_with_secure_cookie_policy`
around the whole WSGI application:

* **On** when the request reached the service over HTTPS -- the WSGI
  scheme is ``https`` (TLS at the server, or gunicorn applied a
  forwarded scheme from one of its ``--forwarded-allow-ips``), or the
  request came from a trusted proxy whose ``X-Forwarded-Proto`` says
  ``https``. A proxy is trusted when its address is listed in
  ``PYCHESTRATE_TRUSTED_PROXY_ADDRESSES`` (comma-separated addresses
  or CIDR networks, ``*`` for any peer; unset means the loopback
  addresses ``127.0.0.1`` and ``::1``, the nginx-on-the-same-host
  deployment the runbook documents).
* **Always on** when ``PYCHESTRATE_RUNTIME_ENVIRONMENT`` is
  ``production`` or anything other than ``development``, ``staging``
  or ``testing``. Production must be served over HTTPS.
* **Off** otherwise, so a development, staging or testing server
  reached over plain HTTP keeps a working sign-in (a browser never
  returns a ``Secure`` cookie over HTTP).

The header is only believed from a trusted proxy because a client can
send any header it likes; it can only ever *add* ``Secure``, never
remove it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from ccai.errors.exceptions import ConfigurationError


_module_logger = logging.getLogger(__name__)


COOKIE_NAME: str = "pychestrate_ui_session"

_SIGNATURE_SEPARATOR: str = "."

# Runtime environments that may run over plain HTTP, where a ``Secure``
# session cookie would never be sent back by the browser and would
# silently break the login round-trip. Requests to these environments
# still get ``Secure`` cookies when they arrive over HTTPS (see
# :func:`wrap_wsgi_app_with_secure_cookie_policy`).
_HTTP_RUNTIME_ENVIRONMENTS = ("development", "staging", "testing")

_RUNTIME_ENVIRONMENT_ENV_VAR: str = "PYCHESTRATE_RUNTIME_ENVIRONMENT"

#: Environment variable naming the proxies whose ``X-Forwarded-Proto``
#: header the Secure-cookie policy believes: comma-separated IP
#: addresses or CIDR networks, or ``*`` for any peer. Unset means
#: :data:`DEFAULT_TRUSTED_PROXY_ADDRESSES`; set but empty trusts none.
TRUSTED_PROXY_ADDRESSES_ENV_VAR: str = "PYCHESTRATE_TRUSTED_PROXY_ADDRESSES"

#: Loopback only: the reverse proxy runs on the same host and forwards
#: to a service bound to 127.0.0.1, as the alpha runbook documents.
DEFAULT_TRUSTED_PROXY_ADDRESSES: Tuple[str, ...] = ("127.0.0.1", "::1")

_TRUST_ANY_PROXY: str = "*"

_WSGI_URL_SCHEME_KEY: str = "wsgi.url_scheme"
_WSGI_REMOTE_ADDR_KEY: str = "REMOTE_ADDR"
_WSGI_FORWARDED_PROTO_KEY: str = "HTTP_X_FORWARDED_PROTO"

_HTTPS_SCHEME: str = "https"

_IpNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def _default_secure_cookie_flag() -> bool:
    """
        Resolve the environment floor of the ``Secure`` flag: the value
        that applies regardless of how the request arrived.

        Production deployments must serve over HTTPS, so their cookies
        are always marked ``Secure``. The development / staging /
        testing deployments may run over plain HTTP, where a ``Secure``
        cookie is never returned by the browser -- breaking
        authentication -- so their floor is off and the flag follows
        the request scheme instead (see
        :func:`wrap_wsgi_app_with_secure_cookie_policy`). Any
        unrecognized / unset environment fails safe to ``Secure``.

        :returns: ``True`` to set ``Secure``; ``False`` otherwise.
    """
    raw = os.environ.get(_RUNTIME_ENVIRONMENT_ENV_VAR, "")
    environment = raw.strip().lower()
    if environment in _HTTP_RUNTIME_ENVIRONMENTS:
        rtnval = False
        return rtnval
    rtnval = True
    return rtnval


@dataclass(frozen=True)
class TrustedProxyPolicy:
    """
        The set of peers whose ``X-Forwarded-Proto`` header the
        Secure-cookie policy believes.

        :param trust_any: ``True`` when every peer is trusted (``*``).
        :param networks: Trusted addresses, as single-address or CIDR
                         networks.
    """
    trust_any: bool
    networks: Tuple[_IpNetwork, ...]

    def trusts(self, *, peer_address: Optional[str]) -> bool:
        """
            Decide whether a request from ``peer_address`` came from a
            trusted proxy.

            :param peer_address: The immediate peer (WSGI
                                 ``REMOTE_ADDR``), or ``None``.

            :returns: ``True`` when the peer is trusted.
        """
        if self.trust_any is True:
            return True

        if peer_address is None or len(peer_address.strip()) == 0:
            return False

        try:
            address = ipaddress.ip_address(peer_address.strip())
        except ValueError:
            return False

        # A dual-stack listener reports IPv4 peers as IPv4-mapped IPv6
        # addresses (``::ffff:127.0.0.1``); compare those as IPv4.
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped

        for network in self.networks:
            if address.version == network.version and address in network:
                return True

        rtnval = False
        return rtnval


def parse_trusted_proxy_addresses(*, raw: Optional[str]) -> TrustedProxyPolicy:
    """
        Parse a ``PYCHESTRATE_TRUSTED_PROXY_ADDRESSES`` value.

        :param raw: Comma-separated IP addresses or CIDR networks, or
                    ``*`` to trust any peer. ``None`` (the variable is
                    unset) yields :data:`DEFAULT_TRUSTED_PROXY_ADDRESSES`;
                    an empty string trusts no proxy.

        :returns: The parsed :class:`TrustedProxyPolicy`.
        :raises: ConfigurationError when an entry is neither ``*`` nor
                 an IP address or network, so a typo stops startup
                 instead of silently leaving cookies without ``Secure``.
    """
    if raw is None:
        entries = list(DEFAULT_TRUSTED_PROXY_ADDRESSES)
    else:
        entries = [entry.strip() for entry in raw.split(",") if len(entry.strip()) > 0]

    trust_any = False
    networks: List[_IpNetwork] = []
    for entry in entries:
        if entry == _TRUST_ANY_PROXY:
            trust_any = True
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            err_msg_lines = ["Invalid trusted proxy address."]
            err_msg_lines.append("VARIABLE: {}".format(TRUSTED_PROXY_ADDRESSES_ENV_VAR))
            err_msg_lines.append("ENTRY: {}".format(entry))
            err_msg_lines.append(
                "EXPECTED: comma-separated IP addresses or CIDR networks, or '*'"
            )
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg)

    rtnval = TrustedProxyPolicy(trust_any=trust_any, networks=tuple(networks))
    return rtnval


def environ_is_https(*, environ: Dict[str, Any], policy: TrustedProxyPolicy) -> bool:
    """
        Decide whether a request reached the service over HTTPS.

        :param environ: WSGI environ of the request.
        :param policy: Which peers may assert the scheme through
                       ``X-Forwarded-Proto``.

        :returns: ``True`` when the WSGI scheme is ``https``, or when the
                  peer is a trusted proxy and the first (client-facing)
                  value of its ``X-Forwarded-Proto`` header is
                  ``https``.
    """
    scheme = str(environ.get(_WSGI_URL_SCHEME_KEY, "") or "").strip().lower()
    if scheme == _HTTPS_SCHEME:
        return True

    forwarded_proto = environ.get(_WSGI_FORWARDED_PROTO_KEY, None)
    if forwarded_proto is None:
        return False

    peer_address = environ.get(_WSGI_REMOTE_ADDR_KEY, None)
    if policy.trusts(peer_address=peer_address) is False:
        return False

    first_value = str(forwarded_proto).split(",")[0].strip().lower()
    rtnval = first_value == _HTTPS_SCHEME
    return rtnval


def resolve_secure_cookie_flag(*, environ: Dict[str, Any], policy: TrustedProxyPolicy) -> bool:
    """
        Resolve the ``Secure`` flag for cookies set on the response to a
        request: always on outside development / staging / testing,
        otherwise on exactly when the request arrived over HTTPS.

        :param environ: WSGI environ of the request.
        :param policy: Trusted-proxy policy for ``X-Forwarded-Proto``.

        :returns: ``True`` when cookies must carry ``Secure``.
    """
    if _default_secure_cookie_flag() is True:
        return True
    rtnval = environ_is_https(environ=environ, policy=policy)
    return rtnval


def add_secure_attribute(*, set_cookie_value: str) -> str:
    """
        Return a ``Set-Cookie`` header value that carries the ``Secure``
        attribute, adding it when absent.

        :param set_cookie_value: A ``Set-Cookie`` header value, e.g.
                                 ``"sid=abc; Path=/; HttpOnly"``.

        :returns: The value, with ``; Secure`` appended when it had no
                  ``Secure`` attribute.
    """
    attributes = set_cookie_value.split(";")[1:]
    for attribute in attributes:
        attribute_name = attribute.split("=", 1)[0].strip().lower()
        if attribute_name == "secure":
            return set_cookie_value
    rtnval = set_cookie_value + "; Secure"
    return rtnval


def wrap_wsgi_app_with_secure_cookie_policy(
        *,
        wsgi_app: Callable[..., Iterable[bytes]],
        trusted_proxy_addresses: Optional[str] = None
    ) -> Callable[..., Iterable[bytes]]:
    """
        Wrap a WSGI application so every ``Set-Cookie`` header it emits
        carries ``Secure`` whenever :func:`resolve_secure_cookie_flag`
        says so. This is the single enforcement point for the rule in
        the module docstring: it covers the UI session cookie, the
        setup-wizard unlock cookie, and any cookie a handler adds later.

        :param wsgi_app: The WSGI application to wrap.
        :param trusted_proxy_addresses: Trusted proxies, in the
            ``PYCHESTRATE_TRUSTED_PROXY_ADDRESSES`` format. ``None``
            reads that environment variable (unset means loopback).

        :returns: The wrapping WSGI application.
        :raises: ConfigurationError when the trusted-proxy list is
                 malformed.
    """
    raw = trusted_proxy_addresses
    if raw is None:
        raw = os.environ.get(TRUSTED_PROXY_ADDRESSES_ENV_VAR, None)
    policy = parse_trusted_proxy_addresses(raw=raw)

    if policy.trust_any is True:
        trusted_description = "any peer"
    elif len(policy.networks) == 0:
        trusted_description = "no proxy"
    else:
        trusted_description = ", ".join(str(network) for network in policy.networks)
    _module_logger.info(
        "Secure-cookie policy: X-Forwarded-Proto is trusted from %s.",
        trusted_description,
    )

    def _secure_cookie_policy_app(
            environ: Dict[str, Any],
            start_response: Callable[..., Any]
        ) -> Iterable[bytes]:
        if resolve_secure_cookie_flag(environ=environ, policy=policy) is False:
            rtnval = wsgi_app(environ, start_response)
            return rtnval

        def _start_response_with_secure_cookies(
                status: str,
                headers: List[Tuple[str, str]],
                exc_info: Optional[Any] = None
            ) -> Any:
            secured_headers: List[Tuple[str, str]] = []
            for header_name, header_value in headers:
                if header_name.lower() == "set-cookie":
                    header_value = add_secure_attribute(set_cookie_value=header_value)
                secured_headers.append((header_name, header_value))
            if exc_info is None:
                rtnval_inner = start_response(status, secured_headers)
            else:
                rtnval_inner = start_response(status, secured_headers, exc_info)
            return rtnval_inner

        rtnval = wsgi_app(environ, _start_response_with_secure_cookies)
        return rtnval

    rtnval = _secure_cookie_policy_app
    return rtnval


def sign_session_payload(
        *,
        payload: Dict[str, Any],
        secret: bytes
    ) -> str:
    """
        Serialize a dict to a signed cookie value.

        The wire format is ``<b64-payload>.<b64-signature>`` where
        the signature is HMAC-SHA256 over the b64-encoded payload.
        Encoding before signing means the verifier doesn't need
        to re-canonicalize the dict to check the signature.

        :param payload: JSON-serializable dict.
        :param secret: HMAC secret bytes (>=16 bytes recommended).

        :returns: Cookie value string.
        :raises: ValueError on empty / too-short secret.
    """
    if secret is None or len(secret) < 16:
        raise ValueError(
            "sign_session_payload requires secret >= 16 bytes"
        )

    payload_json = json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    # Strip '=' padding so the resulting cookie value contains only
    # URL-safe base64 characters (A-Z a-z 0-9 - _) plus the '.'
    # separator.  Unpadded values are not quoted by SimpleCookie, which
    # means browsers receive and re-send the cookie without surrounding
    # DQUOTE characters.  The verifier adds padding back before decoding.
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("ascii").rstrip("=")

    signature = hmac.new(
        secret, payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")

    rtnval = payload_b64 + _SIGNATURE_SEPARATOR + signature_b64
    return rtnval


def verify_session_payload(
        *,
        cookie_value: Optional[str],
        secret: bytes
    ) -> Optional[Dict[str, Any]]:
    """
        Verify a cookie value's signature and return the decoded
        payload dict. Returns ``None`` on any failure -- callers
        treat that as "no session" (anonymous request).

        :param cookie_value: The raw cookie value from
                             ``request.cookies.get(COOKIE_NAME)``.
                             ``None`` returns ``None``.
        :param secret: HMAC secret bytes.

        :returns: Decoded dict on valid signature, ``None`` otherwise.
        :raises: ValueError on empty / too-short secret. Verification
                 failures (tamper, bad b64, bad shape) return ``None``
                 rather than raising so handlers stay simple.
    """
    if secret is None or len(secret) < 16:
        raise ValueError(
            "verify_session_payload requires secret >= 16 bytes"
        )

    if cookie_value is None or len(cookie_value) == 0:
        return None

    if _SIGNATURE_SEPARATOR not in cookie_value:
        return None

    payload_b64, signature_b64 = cookie_value.rsplit(
        _SIGNATURE_SEPARATOR, 1
    )
    if len(payload_b64) == 0 or len(signature_b64) == 0:
        return None

    # HMAC is computed over the payload_b64 string exactly as stored in
    # the cookie (i.e. without '=' padding) so the expected signature
    # matches what sign_session_payload produced.
    expected_signature = hmac.new(
        secret, payload_b64.encode("ascii"), hashlib.sha256
    ).digest()

    # base64.urlsafe_b64decode requires padding; restore it before
    # decoding.  Both payload_b64 and signature_b64 may have been
    # stripped of trailing '=' by sign_session_payload.
    def _restore_b64_padding(s: str) -> str:
        rem = len(s) % 4
        if rem == 0:
            return s
        return s + "=" * (4 - rem)

    try:
        actual_signature = base64.urlsafe_b64decode(
            _restore_b64_padding(signature_b64).encode("ascii")
        )
    except (ValueError, TypeError):
        return None

    if not hmac.compare_digest(expected_signature, actual_signature):
        return None

    try:
        payload_json = base64.urlsafe_b64decode(
            _restore_b64_padding(payload_b64).encode("ascii")
        )
    except (ValueError, TypeError):
        return None

    try:
        payload = json.loads(payload_json.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    rtnval = payload
    return rtnval


def read_session_from_request(
        *,
        request: Any,
        secret: bytes,
        cookie_name: str = COOKIE_NAME
    ) -> Dict[str, Any]:
    """
        Extract and verify the UI session cookie from a webworks
        request. Returns an empty dict for missing / tampered /
        malformed cookies so handlers can write
        ``session = read_session_from_request(...)`` and treat the
        result as a regular dict.

        :param request: Webworks Request.
        :param secret: HMAC secret bytes.
        :param cookie_name: Cookie name (defaults to
                            :data:`COOKIE_NAME`).

        :returns: Dict (empty on no / invalid session).
    """
    raw = request.cookies.get(cookie_name, None)
    decoded = verify_session_payload(cookie_value=raw, secret=secret)
    if decoded is None:
        return {}
    rtnval = decoded
    return rtnval


def write_session_to_response(
        *,
        response: Any,
        payload: Dict[str, Any],
        secret: bytes,
        cookie_name: str = COOKIE_NAME,
        max_age_seconds: Optional[int] = None,
        secure: Optional[bool] = None,
        http_only: bool = True,
        same_site: str = "Lax",
        path: str = "/"
    ) -> None:
    """
        Sign and attach the session cookie to a webworks response.
        Defaults to ``Secure`` + ``HttpOnly`` + ``SameSite=Lax``
        per OWASP guidance.

        When ``secure`` is ``None`` (the default) the ``Secure`` flag
        starts from the runtime-environment floor
        (:func:`_default_secure_cookie_flag`): on in production (and
        any unrecognized environment), off for development / staging /
        testing. For those environments
        :func:`wrap_wsgi_app_with_secure_cookie_policy` adds ``Secure``
        on the way out whenever the request arrived over HTTPS
        (directly or through a trusted proxy), so an HTTPS staging
        deployment never issues a session cookie without it.

        :param response: Webworks Response.
        :param payload: Dict to sign + store.
        :param secret: HMAC secret bytes.
        :param cookie_name: Cookie name.
        :param max_age_seconds: Cookie ``Max-Age`` (None = session
                                cookie that dies with the browser).
        :param secure: Set the ``Secure`` flag. ``None`` resolves from
                       the runtime environment (the WSGI wrapper then
                       adds it for HTTPS requests).
        :param http_only: Set the ``HttpOnly`` flag.
        :param same_site: ``Strict`` | ``Lax`` | ``None``.
        :param path: Cookie scope path.

        :returns: None.
    """
    resolved_secure = secure
    if resolved_secure is None:
        resolved_secure = _default_secure_cookie_flag()

    cookie_value = sign_session_payload(payload=payload, secret=secret)
    response.set_cookie(
        name=cookie_name,
        value=cookie_value,
        max_age=max_age_seconds,
        path=path,
        secure=resolved_secure,
        httponly=http_only,
        samesite=same_site,
    )
    return


def clear_session_cookie_on_response(
        *,
        response: Any,
        cookie_name: str = COOKIE_NAME,
        path: str = "/"
    ) -> None:
    """
        Delete the UI session cookie on a webworks response.
        Used by logout flows.

        :param response: Webworks Response.
        :param cookie_name: Cookie name.
        :param path: Cookie scope path (must match the path the
                     cookie was set with for the delete to take).

        :returns: None.
    """
    response.delete_cookie(name=cookie_name, path=path)
    return


__all__ = [
    "COOKIE_NAME",
    "DEFAULT_TRUSTED_PROXY_ADDRESSES",
    "TRUSTED_PROXY_ADDRESSES_ENV_VAR",
    "TrustedProxyPolicy",
    "add_secure_attribute",
    "environ_is_https",
    "parse_trusted_proxy_addresses",
    "resolve_secure_cookie_flag",
    "sign_session_payload",
    "verify_session_payload",
    "read_session_from_request",
    "write_session_to_response",
    "clear_session_cookie_on_response",
    "wrap_wsgi_app_with_secure_cookie_policy",
]
