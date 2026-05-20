"""
.. module:: jobs.envelope.restapi.v1.signing_keys_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST route for /api/v1/envelope-signing-keys.

.. moduleauthor:: Automation Mojo LLC

A JWKS-style public-key distribution endpoint. The pod-client agent
verifies signed job envelopes against the Ed25519 public key the
server publishes here — without the operator having to install the
key out-of-band.

* ``GET /api/v1/envelope-signing-keys`` (tag: dispatch)

Auth decision
-------------
A signing *public* key is not a secret — publishing it is the whole
point. But to keep the unauthenticated info-leak surface minimal the
endpoint is gated behind *any authenticated principal*: a cookie
session, an API key, OR a verified mTLS client certificate. A
freshly-enrolled pod client already holds its mTLS identity, so the
mTLS path covers the client's use case; operators and CI tooling use
the cookie / API-key path. The handler treats the presence of either
an ``auth_principal`` (resolved by the session middleware from the
cookie / API key) or an ``SSL_CLIENT_S_DN_CN`` mTLS environ value as
sufficient. Anonymous requests get a 401 problem document.

When no signing key has been provisioned the handler returns 503 so
callers can distinguish "not configured yet" from "auth failure".

Error responses are RFC 7807 problem documents per the convention in
:mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Any, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.jobs.envelope import signer


ENVELOPE_SIGNING_KEYS_PATH = "/envelope-signing-keys"

#: WSGI environ key nginx populates with the verified client cert
#: common-name after a successful mTLS handshake. Presence is treated
#: as proof of an authenticated transport-level principal.
MTLS_CLIENT_CN_ENVIRON_KEY = "SSL_CLIENT_S_DN_CN"

_LOGGER = logging.getLogger("pychestrate.envelope.signing_keys.routes")


def _resolve_auth_principal(request: Request) -> Optional[Any]:
    """
        Return the ``AuthPrincipal`` attached to the request by the
        session middleware, or ``None`` when the request carries no
        cookie session / API key.

        :param request: Incoming webworks request.

        :returns: AuthPrincipal or None.
    """
    rtnval = getattr(request, "auth_principal", None)
    return rtnval


def _resolve_mtls_client_cn(request: Request) -> Optional[str]:
    """
        Return the verified client common-name nginx forwarded for
        this request, or ``None`` when no mTLS handshake completed.

        Mirrors :func:`runs_routes._resolve_mtls_client_cn` — walks
        the explicit test seam, the WSGI environ dict, and the
        webworks ``scope`` dict.

        :param request: Incoming webworks request.

        :returns: Client common-name string or None.
    """
    explicit = getattr(request, "mtls_client_cn", None)
    if isinstance(explicit, str) and len(explicit) > 0:
        rtnval = explicit
        return rtnval

    environ = getattr(request, "environ", None)
    if isinstance(environ, dict):
        candidate = environ.get(MTLS_CLIENT_CN_ENVIRON_KEY, None)
        if isinstance(candidate, str) and len(candidate) > 0:
            rtnval = candidate
            return rtnval

    scope = getattr(request, "scope", None)
    if isinstance(scope, dict):
        candidate = scope.get(MTLS_CLIENT_CN_ENVIRON_KEY, None)
        if isinstance(candidate, str) and len(candidate) > 0:
            rtnval = candidate
            return rtnval

    rtnval = None
    return rtnval


def _request_is_authenticated(request: Request) -> bool:
    """
        Decide whether the request carries any authenticated
        principal — a cookie / API-key principal OR a verified mTLS
        client certificate.

        :param request: Incoming webworks request.

        :returns: True when the request is authenticated.
    """
    principal = _resolve_auth_principal(request=request)
    if principal is not None:
        rtnval = True
        return rtnval

    mtls_cn = _resolve_mtls_client_cn(request=request)
    if mtls_cn is not None:
        rtnval = True
        return rtnval

    rtnval = False
    return rtnval


def handle_list_envelope_signing_keys(request: Request) -> Response:
    """
        ``GET /api/v1/envelope-signing-keys`` — return the JWKS-style
        public-key set the service signs job envelopes with.

        Response shape::

            {"keys": [{"key_id": "...", "algorithm": "Ed25519",
                       "public_key_pem": "-----BEGIN PUBLIC KEY...",
                       "status": "active"}]}

        Returns 401 for an anonymous request, 503 when no signing key
        has been provisioned, and 200 with the key set otherwise.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying ``{"keys": [...]}``;
                  401 / 503 problem responses on failure.
    """
    authenticated = _request_is_authenticated(request=request)
    if authenticated is False:
        rtnval = problem_response_for_http_status(
            status=401,
            detail="Authentication required",
            instance=request.path,
        )
        return rtnval

    key_set = signer.active_signing_key_set()
    if len(key_set) == 0:
        rtnval = problem_response_for_http_status(
            status=503,
            detail="Envelope signing key is not provisioned",
            instance=request.path,
        )
        return rtnval

    body = {"keys": key_set}
    rtnval = JSONResponse(content=body, status_code=200)
    return rtnval


def register_signing_keys_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the envelope-signing-key distribution route to a
        webworks application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + ENVELOPE_SIGNING_KEYS_PATH
    app.attach_route(base, methods=["GET"])(
        handle_list_envelope_signing_keys
    )
    return


__all__ = [
    "ENVELOPE_SIGNING_KEYS_PATH",
    "MTLS_CLIENT_CN_ENVIRON_KEY",
    "register_signing_keys_routes",
    "handle_list_envelope_signing_keys",
]
