"""
.. module:: hardening.security_headers
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Security response headers and the per-response CSP nonce.

.. moduleauthor:: Code Craft AI LLC

Applied to every response at the WSGI boundary (so dispatcher 404s,
405s and 500s get them too):

* ``Content-Security-Policy`` on HTML documents::

      default-src 'self'; script-src 'self' 'nonce-<per response>';
      style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:;
      font-src 'self' data:; connect-src 'self'; object-src 'none';
      base-uri 'self'; form-action 'self'; frame-ancestors 'none'

  Scripts are strict: only same-origin files and the inline blocks
  our templates mark with ``nonce="{{ csp_nonce() }}"`` run -- no
  ``'unsafe-inline'``, no ``'unsafe-eval'``, no inline event
  handlers. Styles allow ``'unsafe-inline'`` deliberately: the mj-*
  component library (``pyc-mj-lib``, not built in this repository)
  injects a ``<style>`` element and ~60 ``style="..."`` attributes
  through ``innerHTML``, and 36 server-rendered templates carry
  ``style`` attributes; nonces cannot cover style attributes. CSS
  injection is far weaker than script injection, and script-src
  stays strict.
* ``frame-ancestors 'none'`` / ``X-Frame-Options: DENY`` -- except
  under ``/embed/``, the signed chromeless views that exist to be
  framed by third-party pages (``frame-ancestors *``, no XFO).
* ``X-Content-Type-Options: nosniff`` and
  ``Referrer-Policy: same-origin`` on every response.
* ``Cache-Control: no-store`` on HTML and JSON responses that do not
  set their own caching, so pages and API data are never kept in the
  browser cache -- pressing Back after signing out re-requests the
  page (and is sent to sign in) instead of showing it from cache.
  Static assets keep the caching they declare.
* ``Strict-Transport-Security`` on HTTPS responses when the runtime
  environment is ``production`` (the alpha nginx front adds HSTS
  itself).

Headers a handler already set are left alone.

The nonce is minted per request and published in a context variable
before the application runs; templates read it through the
``csp_nonce()`` Jinja global (:func:`install_csp_nonce_global`), and
the same value goes into the response's policy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import contextvars
import secrets

from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


#: Path prefix of the signed, framable embed views.
EMBED_PATH_PREFIX: str = "/embed/"

#: Response content types that get ``Cache-Control: no-store`` when
#: the handler did not choose a caching policy.
NO_STORE_CONTENT_TYPES = frozenset((
    "text/html",
    "application/json",
    "application/problem+json",
))

#: ``Strict-Transport-Security`` value sent on production HTTPS.
HSTS_VALUE: str = "max-age=31536000"

REFERRER_POLICY_VALUE: str = "same-origin"

_ACTIVE_CSP_NONCE: contextvars.ContextVar = contextvars.ContextVar(
    "pychestrate_csp_nonce", default="",
)


def new_csp_nonce() -> str:
    """
        Mint a fresh CSP nonce (128 random bits, base64url).

        :returns: Nonce string.
    """
    rtnval = secrets.token_urlsafe(16)
    return rtnval


def set_active_csp_nonce(*, nonce: str) -> None:
    """
        Publish the nonce of the request being served.

        :param nonce: Nonce string.

        :returns: None.
    """
    _ACTIVE_CSP_NONCE.set(nonce)
    return


def csp_nonce() -> str:
    """
        The CSP nonce of the request being served; ``""`` outside a
        request (tests rendering templates directly). Installed as the
        ``csp_nonce`` Jinja global.

        :returns: Nonce string.
    """
    rtnval = _ACTIVE_CSP_NONCE.get()
    return rtnval


def install_csp_nonce_global(*, environment: Any) -> None:
    """
        Attach :func:`csp_nonce` to a jinja environment so templates
        can write ``<script nonce="{{ csp_nonce() }}">``.

        :param environment: :class:`jinja2.Environment`.

        :returns: None.
    """
    environment.globals["csp_nonce"] = csp_nonce
    return


def build_content_security_policy(*, nonce: str, framable: bool) -> str:
    """
        Build the Content-Security-Policy value for an HTML document.

        :param nonce: Per-response script nonce.
        :param framable: True for the embed views third-party pages
                         frame.

        :returns: Policy string.
    """
    directives = [
        "default-src 'self'",
        "script-src 'self' 'nonce-{}'".format(nonce),
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors *" if framable else "frame-ancestors 'none'",
    ]
    rtnval = "; ".join(directives)
    return rtnval


def _media_type(content_type: Optional[str]) -> str:
    """
        The bare media type of a Content-Type value.

        :param content_type: Header value or ``None``.

        :returns: Lower-case media type (``""`` when absent).
    """
    if content_type is None:
        return ""
    rtnval = content_type.split(";", 1)[0].strip().lower()
    return rtnval


def security_headers_for(
        *,
        path: str,
        existing: Dict[str, str],
        nonce: str,
        is_https: bool,
        hsts_enabled: bool
    ) -> List[Tuple[str, str]]:
    """
        Decide which security headers to add to one response.

        :param path: Request path.
        :param existing: The response's headers, keyed by lower-case
                         name.
        :param nonce: The request's CSP nonce.
        :param is_https: Whether the request arrived over HTTPS.
        :param hsts_enabled: Whether HSTS is sent (production).

        :returns: ``(name, value)`` pairs to append.
    """
    framable = path.startswith(EMBED_PATH_PREFIX)
    media_type = _media_type(existing.get("content-type", None))
    added: List[Tuple[str, str]] = []

    if media_type == "text/html" and "content-security-policy" not in existing:
        added.append((
            "Content-Security-Policy",
            build_content_security_policy(nonce=nonce, framable=framable),
        ))
    if framable is False and "x-frame-options" not in existing:
        added.append(("X-Frame-Options", "DENY"))
    if "x-content-type-options" not in existing:
        added.append(("X-Content-Type-Options", "nosniff"))
    if "referrer-policy" not in existing:
        added.append(("Referrer-Policy", REFERRER_POLICY_VALUE))
    if media_type in NO_STORE_CONTENT_TYPES and "cache-control" not in existing:
        added.append(("Cache-Control", "no-store"))
    if hsts_enabled is True and is_https is True and "strict-transport-security" not in existing:
        added.append(("Strict-Transport-Security", HSTS_VALUE))
    rtnval = added
    return rtnval


def request_is_https(*, environ: Dict[str, Any]) -> bool:
    """
        Whether the request reached the TLS terminator over HTTPS
        (``wsgi.url_scheme``, or the proxy's ``X-Forwarded-Proto``;
        browsers ignore HSTS received over plain HTTP, so a forged
        header gains nothing).

        :param environ: WSGI environ.

        :returns: True for HTTPS.
    """
    if str(environ.get("wsgi.url_scheme", "")).lower() == "https":
        return True
    forwarded = str(environ.get("HTTP_X_FORWARDED_PROTO", "") or "")
    rtnval = forwarded.split(",", 1)[0].strip().lower() == "https"
    return rtnval


def wrap_wsgi_application_with_security_headers(
        *,
        wsgi_app: Callable[..., Iterable[bytes]],
        hsts_enabled: bool = False
    ) -> Callable[..., Iterable[bytes]]:
    """
        Wrap a WSGI application so every response carries the security
        headers and HTML documents a CSP whose script nonce matches the
        one the templates rendered.

        The nonce is published before ``wsgi_app`` runs and is not
        cleared afterwards, so it stays valid however lazily the
        application renders; the next request on the same thread
        replaces it.

        :param wsgi_app: WSGI callable.
        :param hsts_enabled: Send HSTS on HTTPS responses.

        :returns: WSGI callable.
    """
    def _application(environ: Dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        nonce = new_csp_nonce()
        set_active_csp_nonce(nonce=nonce)
        path = str(environ.get("PATH_INFO", "") or "/")
        is_https = request_is_https(environ=environ)

        def _start_response(status: str, headers: List[Tuple[str, str]], exc_info: Any = None) -> Any:
            existing = {str(name).lower(): str(value) for name, value in headers}
            patched = list(headers) + security_headers_for(
                path=path,
                existing=existing,
                nonce=nonce,
                is_https=is_https,
                hsts_enabled=hsts_enabled,
            )
            if exc_info is None:
                rtnval = start_response(status, patched)
            else:
                rtnval = start_response(status, patched, exc_info)
            return rtnval

        rtnval = wsgi_app(environ, _start_response)
        return rtnval

    rtnval = _application
    return rtnval


__all__ = [
    "EMBED_PATH_PREFIX",
    "HSTS_VALUE",
    "build_content_security_policy",
    "csp_nonce",
    "install_csp_nonce_global",
    "new_csp_nonce",
    "request_is_https",
    "security_headers_for",
    "set_active_csp_nonce",
    "wrap_wsgi_application_with_security_headers",
]
