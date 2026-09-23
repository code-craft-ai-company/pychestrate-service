"""
.. module:: clients.mtls_identity
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Deliver the verified pod client-certificate identity from
               the TLS terminator to the request handlers.

.. moduleauthor:: Code Craft AI LLC

The pod-facing routes (heartbeat, dispatch long-poll, capabilities,
dispatch-ack, progress, results, artifacts, envelope signing keys)
authenticate the calling pod by the common name of the client
certificate the TLS terminator verified. The CN is the pod's client
id (see :mod:`clients.enrollment.ca_adapter`), and each handler
compares it with the ``client_id`` / run it acts on.

Nothing used to carry that identity to a handler:

* the deployment forwarded it as an ``SSL_CLIENT_S_DN_CN`` request
  header, and gunicorn (23+) drops every header whose name contains an
  underscore;
* a hyphenated header only reaches the app as an ``HTTP_*`` environ
  key the handlers never read, and webworks builds its ``Request``
  without the WSGI environ (``request.scope`` is empty), so even an
  environ key set by a TLS-terminating server was invisible.

This module closes the gap with two pieces installed around the app
by :func:`install_client_certificate_identity`:

1. :class:`ClientCertificateIdentityWsgiMiddleware` wraps the WSGI
   application. For each request it decides the verified identity:

   * from ``SSL_CLIENT_S_DN_CN`` (with ``SSL_CLIENT_VERIFY`` absent or
     ``SUCCESS``) when a TLS-terminating server put them in the
     environ -- clients cannot forge environ keys without the
     ``HTTP_`` prefix; or
   * from the ``X-Client-Cert-CN`` / ``X-Client-Cert-Verify`` request
     headers, but only when the TCP peer (``REMOTE_ADDR``) is a
     trusted proxy and the verify result is ``SUCCESS``.

   It always removes those two headers from the environ, so no handler
   can ever read a client-supplied value, and publishes the identity
   in a context variable while the request is processed.
2. :class:`ClientCertificateIdentityMiddleware`, a webworks pipeline
   middleware, copies that identity onto ``request.mtls_client_cn`` --
   the attribute every mTLS route resolver already checks first -- and
   clears it on requests without a verified certificate.

Trusted proxies come from ``PYCHESTRATE_TRUSTED_PROXY_ADDRESSES``, the
variable the Secure-cookie policy uses for ``X-Forwarded-Proto``
(:mod:`webinterface.foundation.cookie_session`), parsed by the same
function so both decisions always name the same proxies: a
comma-separated list of IP addresses or CIDR networks, or ``*`` for any
peer. When the variable is unset the loopback addresses are trusted
(``127.0.0.1``, ``::1``) -- the documented deployment runs nginx on the
same host and binds the app to loopback, the same convention gunicorn
uses for ``forwarded_allow_ips``. Set but empty trusts no proxy,
leaving only server-populated environ keys; a malformed entry stops
startup. ``*`` lets any peer assert a pod identity, so it is only safe
when nothing but the TLS terminator can reach the app. Every nginx
``location`` that proxies to the app must set both headers
(``proxy_set_header`` replaces a client-supplied header only where it
is declared).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from contextvars import ContextVar
from typing import Any, Callable, Dict, Iterable, Iterator, Optional

from ccai.pychestrate.webservice.webinterface.foundation.cookie_session import (
    DEFAULT_TRUSTED_PROXY_ADDRESSES,
    TRUSTED_PROXY_ADDRESSES_ENV_VAR,
    TrustedProxyPolicy,
    parse_trusted_proxy_addresses as _parse_trusted_proxy_policy,
)


#: Environment variable naming the proxies whose client-certificate
#: headers are trusted -- the Secure-cookie policy's variable (see the
#: module docstring). Unset means :data:`DEFAULT_TRUSTED_PROXY_ADDRESSES`
#: (loopback).
ENV_TRUSTED_PROXY_ADDRESSES: str = TRUSTED_PROXY_ADDRESSES_ENV_VAR

#: Request header the TLS terminator sets to the verified client
#: certificate's subject CN (nginx: ``$ssl_client_s_dn_cn``).
CLIENT_CERT_CN_HEADER: str = "X-Client-Cert-CN"

#: Request header the TLS terminator sets to its verification result
#: (nginx: ``$ssl_client_verify``: ``SUCCESS`` / ``FAILED:<reason>`` /
#: ``NONE``).
CLIENT_CERT_VERIFY_HEADER: str = "X-Client-Cert-Verify"

#: WSGI environ spellings of the two headers.
ENVIRON_CLIENT_CERT_CN_HEADER: str = "HTTP_X_CLIENT_CERT_CN"
ENVIRON_CLIENT_CERT_VERIFY_HEADER: str = "HTTP_X_CLIENT_CERT_VERIFY"

#: Environ keys a TLS-terminating server (or this middleware, after it
#: accepted a trusted header) carries the verified identity in.
ENVIRON_SSL_CLIENT_CN: str = "SSL_CLIENT_S_DN_CN"
ENVIRON_SSL_CLIENT_VERIFY: str = "SSL_CLIENT_VERIFY"

#: The only verification result that establishes an identity.
VERIFY_SUCCESS: str = "SUCCESS"

#: Pipeline name of :class:`ClientCertificateIdentityMiddleware`.
CLIENT_CERT_IDENTITY_MIDDLEWARE_NAME: str = "pychestrate-client-cert-identity"

#: Identity of the request being processed, published by the WSGI
#: middleware and read by the pipeline middleware.
_VERIFIED_CLIENT_CN: ContextVar[Optional[str]] = ContextVar(
    "pychestrate_verified_client_cn", default=None,
)

_LOGGER = logging.getLogger("pychestrate.clients.mtls_identity")


def parse_trusted_proxy_addresses(*, raw: Optional[str]) -> TrustedProxyPolicy:
    """
        Parse a ``PYCHESTRATE_TRUSTED_PROXY_ADDRESSES`` value with the
        Secure-cookie policy's parser, so both read it the same way.

        :param raw: Comma-separated IP addresses / CIDR networks, or
                    ``*`` for any peer; ``None`` (unset) selects
                    :data:`DEFAULT_TRUSTED_PROXY_ADDRESSES`; an empty
                    value trusts no proxy.

        :returns: The trusted-proxy policy.
        :raises: ConfigurationError when an entry is not ``*``, an IP
                 address or a network.
    """
    rtnval = _parse_trusted_proxy_policy(raw=raw)
    return rtnval


def trusted_proxy_addresses_from_environment() -> TrustedProxyPolicy:
    """
        Read :data:`ENV_TRUSTED_PROXY_ADDRESSES` from the process
        environment.

        :returns: The trusted-proxy policy.
        :raises: ConfigurationError when the value is malformed.
    """
    rtnval = parse_trusted_proxy_addresses(raw=os.environ.get(ENV_TRUSTED_PROXY_ADDRESSES, None))
    return rtnval


def describe_trusted_proxies(*, trusted_proxies: TrustedProxyPolicy) -> str:
    """
        Human-readable form of a trusted-proxy policy.

        :param trusted_proxies: The policy.

        :returns: ``"any peer"``, ``"no proxy"`` or the comma-separated
                  networks.
    """
    if trusted_proxies.trust_any is True:
        rtnval = "any peer"
    elif len(trusted_proxies.networks) == 0:
        rtnval = "no proxy"
    else:
        rtnval = ", ".join(str(network) for network in trusted_proxies.networks)
    return rtnval


def resolve_verified_client_cn(
        *,
        environ: Dict[str, Any],
        trusted_proxies: TrustedProxyPolicy
    ) -> Optional[str]:
    """
        Decide the verified client-certificate CN for one request.

        :param environ: WSGI environ of the request.
        :param trusted_proxies: The proxies whose client-certificate
                                headers are trusted.

        :returns: The verified CN, or ``None`` when the request carries
                  no verified client certificate.
    """
    server_cn = environ.get(ENVIRON_SSL_CLIENT_CN, None)
    if isinstance(server_cn, str) and len(server_cn.strip()) > 0:
        server_verify = environ.get(ENVIRON_SSL_CLIENT_VERIFY, None)
        if server_verify is None or str(server_verify).strip() == VERIFY_SUCCESS:
            rtnval = server_cn.strip()
            return rtnval

    header_cn = environ.get(ENVIRON_CLIENT_CERT_CN_HEADER, None)
    if not isinstance(header_cn, str) or len(header_cn.strip()) == 0:
        return None

    remote_addr = environ.get("REMOTE_ADDR", None)
    if trusted_proxies.trusts(peer_address=remote_addr) is False:
        _LOGGER.warning(
            "clients.mtls_identity.untrusted_peer remote_addr=%s path=%s -- ignoring %s; set %s"
            " to the address of the TLS terminator",
            remote_addr, environ.get("PATH_INFO", ""), CLIENT_CERT_CN_HEADER, ENV_TRUSTED_PROXY_ADDRESSES,
        )
        return None

    header_verify = environ.get(ENVIRON_CLIENT_CERT_VERIFY_HEADER, None)
    if not isinstance(header_verify, str) or header_verify.strip() != VERIFY_SUCCESS:
        return None

    rtnval = header_cn.strip()
    return rtnval


def current_verified_client_cn() -> Optional[str]:
    """
        The verified client-certificate CN of the request being
        processed, as published by
        :class:`ClientCertificateIdentityWsgiMiddleware`.

        :returns: The CN, or ``None``.
    """
    rtnval = _VERIFIED_CLIENT_CN.get()
    return rtnval


class _IdentityScopedResponse:
    """
        Re-publishes the request's identity while the WSGI response is
        iterated, so a WSGI application that only runs its handler when
        the server iterates the body still sees it. Forwards ``close``.
    """

    def __init__(self, *, result: Iterable[bytes], client_cn: Optional[str]) -> None:
        self._result: Iterable[bytes] = result
        self._client_cn: Optional[str] = client_cn
        return

    def __iter__(self) -> Iterator[bytes]:
        iterator = iter(self._result)
        while True:
            token = _VERIFIED_CLIENT_CN.set(self._client_cn)
            try:
                chunk = next(iterator)
            except StopIteration:
                break
            finally:
                _VERIFIED_CLIENT_CN.reset(token)
            yield chunk
        return

    def close(self) -> None:
        close = getattr(self._result, "close", None)
        if callable(close):
            close()
        return


class ClientCertificateIdentityWsgiMiddleware:
    """
        WSGI middleware that resolves the verified client-certificate
        identity of each request (see the module docstring), strips the
        client-certificate headers from the environ, and publishes the
        identity for :class:`ClientCertificateIdentityMiddleware`.

        :param app: The wrapped WSGI application.
        :param trusted_proxies: The proxies whose client-certificate
                                headers are trusted.
    """

    def __init__(self, *, app: Callable, trusted_proxies: TrustedProxyPolicy) -> None:
        self._app: Callable = app
        self._trusted_proxies: TrustedProxyPolicy = trusted_proxies
        return

    @property
    def trusted_proxies(self) -> TrustedProxyPolicy:
        return self._trusted_proxies

    def __call__(self, environ: Dict[str, Any], start_response: Callable) -> Iterable[bytes]:
        """
            Resolve and publish the identity, then call the wrapped app.

            :param environ: WSGI environ.
            :param start_response: WSGI start_response.

            :returns: The wrapped app's response iterable.
        """
        client_cn = resolve_verified_client_cn(environ=environ, trusted_proxies=self._trusted_proxies)

        environ.pop(ENVIRON_CLIENT_CERT_CN_HEADER, None)
        environ.pop(ENVIRON_CLIENT_CERT_VERIFY_HEADER, None)
        if client_cn is not None:
            environ[ENVIRON_SSL_CLIENT_CN] = client_cn
            environ[ENVIRON_SSL_CLIENT_VERIFY] = VERIFY_SUCCESS

        token = _VERIFIED_CLIENT_CN.set(client_cn)
        try:
            result = self._app(environ, start_response)
        finally:
            _VERIFIED_CLIENT_CN.reset(token)

        rtnval = _IdentityScopedResponse(result=result, client_cn=client_cn)
        return rtnval


class ClientCertificateIdentityMiddleware:
    """
        WebWorks pipeline middleware that sets ``request.mtls_client_cn``
        to the identity :class:`ClientCertificateIdentityWsgiMiddleware`
        verified for this request, or to ``None`` when there is none.
    """

    name: str = CLIENT_CERT_IDENTITY_MIDDLEWARE_NAME

    def __call__(self, request: Any, call_next: Callable[[Any], Any]) -> Any:
        """
            :param request: Webworks Request.
            :param call_next: Next callable in the pipeline.

            :returns: The downstream response.
        """
        request.mtls_client_cn = current_verified_client_cn()
        rtnval = call_next(request)
        return rtnval


def install_client_certificate_identity(
        *,
        app: Any,
        wsgi_app: Callable,
        trusted_proxies: Optional[TrustedProxyPolicy] = None
    ) -> Callable:
    """
        Install client-certificate identity delivery: add
        :class:`ClientCertificateIdentityMiddleware` to the webworks
        dispatcher pipeline and return ``wsgi_app`` wrapped in
        :class:`ClientCertificateIdentityWsgiMiddleware`.

        Must be called after ``app.startup()`` (the dispatcher exists
        from ``INFRASTRUCTURE_READY`` on), and the returned callable is
        what the WSGI server must host.

        :param app: WebWorks application.
        :param wsgi_app: The finished WSGI application for ``app``.
        :param trusted_proxies: Trusted-proxy policy; ``None`` reads
                                :data:`ENV_TRUSTED_PROXY_ADDRESSES`.

        :returns: The wrapped WSGI application.
        :raises: ConfigurationError when the trusted-proxy setting is
                 malformed.
    """
    if trusted_proxies is None:
        trusted_proxies = trusted_proxy_addresses_from_environment()

    middleware = ClientCertificateIdentityMiddleware()
    app.dispatcher.pipeline.add(middleware, name=middleware.name, position="start")

    _LOGGER.info(
        "clients.mtls_identity.installed trusted_proxies=%s headers=%s,%s",
        describe_trusted_proxies(trusted_proxies=trusted_proxies),
        CLIENT_CERT_CN_HEADER, CLIENT_CERT_VERIFY_HEADER,
    )

    rtnval = ClientCertificateIdentityWsgiMiddleware(app=wsgi_app, trusted_proxies=trusted_proxies)
    return rtnval


__all__ = [
    "CLIENT_CERT_CN_HEADER",
    "CLIENT_CERT_IDENTITY_MIDDLEWARE_NAME",
    "CLIENT_CERT_VERIFY_HEADER",
    "ClientCertificateIdentityMiddleware",
    "ClientCertificateIdentityWsgiMiddleware",
    "DEFAULT_TRUSTED_PROXY_ADDRESSES",
    "ENV_TRUSTED_PROXY_ADDRESSES",
    "current_verified_client_cn",
    "describe_trusted_proxies",
    "install_client_certificate_identity",
    "parse_trusted_proxy_addresses",
    "resolve_verified_client_cn",
    "trusted_proxy_addresses_from_environment",
]
