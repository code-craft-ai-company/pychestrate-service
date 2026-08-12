"""
.. module:: jobs.envelope.restapi.v1.jwks_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST route publishing the envelope-signing JWKS.

.. moduleauthor:: Code Craft AI LLC

The standards-shaped sibling of
:mod:`jobs.envelope.restapi.v1.signing_keys_routes`. Both publish the
same Ed25519 public key material; this module renders it as an
RFC 7517 JWK Set using the RFC 8037 ``OKP`` key type so a pod client
can feed the document straight into an off-the-shelf JOSE library
instead of parsing the Pychestrate-specific PEM shape.

* ``GET /api/v1/envelope-signing-keys/jwks.json`` (tag: dispatch)

Response shape
--------------
::

    {"keys": [{"kty": "OKP", "crv": "Ed25519",
               "x": "<base64url raw public key>",
               "kid": "pychestrate-dev-ed25519",
               "use": "sig", "alg": "EdDSA"}]}

The active signing key is always element zero; rotation grace-window
keys follow in ``kid`` order (RFC 7517 section 5 permits key order to
signal preference). The media type is the registered
``application/jwk-set+json`` (RFC 7517 section 8.5.1).

Auth decision
-------------
Identical to the sibling endpoint, deliberately: a signing *public*
key is not a secret, but the endpoint is gated behind *any*
authenticated principal — a cookie session, an API key, OR a verified
mTLS client certificate — so the unauthenticated info-leak surface
stays minimal. A freshly-enrolled pod client already holds its mTLS
identity, so the mTLS path covers the client's use case. Publishing
the same key material under two different auth postures would be a
bug, so this handler mirrors ``signing_keys_routes`` exactly.

Because the response is auth-gated it is cached as ``private`` — a
shared proxy must not hand a stored copy to an anonymous caller.

Caching semantics
-----------------
The document changes only on key rotation, and a client that caches
it forever would reject envelopes signed by a newly rotated key. So:

* ``Cache-Control: private, max-age=300, must-revalidate`` — serve
  from cache for at most 5 minutes, then revalidate. 300 s matches
  the ``max_envelope_age`` default in ``5-job-envelope`` so a client
  can never be more stale than the envelopes it is verifying.
* ``ETag`` — a strong validator: the SHA-256 of the canonical JSON
  rendering of the key set. Rotation changes the key list, which
  changes the digest.
* ``If-None-Match`` is honored and answered with ``304 Not Modified``
  (no body, same ``ETag`` / ``Cache-Control``), so the once-per-60 s
  unknown-key refresh that ``5-job-envelope`` NFR-4 mandates costs a
  header exchange rather than a full document.

Error responses are RFC 7807 problem documents per the convention in
:mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json
import logging

from typing import Any, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.jobs.envelope import signer


ENVELOPE_JWKS_PATH = "/envelope-signing-keys/jwks.json"

#: Registered media type for a JWK Set document (RFC 7517 section
#: 8.5.1). Clients that key off ``application/json`` still parse it —
#: neither ``requests`` nor ``httpx`` gates ``.json()`` on the
#: content type — so publishing the registered type costs nothing.
JWK_SET_MEDIA_TYPE = "application/jwk-set+json"

#: Freshness window handed to caches. Matches the ``max_envelope_age``
#: default (300 s) in the ``5-job-envelope`` requirements so a cached
#: key set can never outlive the envelopes it verifies.
JWKS_CACHE_MAX_AGE_SECONDS = 300

#: ``private`` (not ``public``) because the endpoint is auth-gated —
#: a shared cache must not serve a stored copy to an anonymous
#: caller. ``must-revalidate`` forbids serving the document stale
#: past ``max-age``, which bounds how long a rotation stays invisible.
JWKS_CACHE_CONTROL_VALUE = "private, max-age={}, must-revalidate".format(
    JWKS_CACHE_MAX_AGE_SECONDS
)

#: Request header carrying the client's cached ``ETag`` values.
IF_NONE_MATCH_HEADER = "If-None-Match"

#: WSGI environ key nginx populates with the verified client cert
#: common-name after a successful mTLS handshake. Presence is treated
#: as proof of an authenticated transport-level principal. Declared
#: locally rather than imported from a sibling route module — the
#: house convention for per-feature route seams.
MTLS_CLIENT_CN_ENVIRON_KEY = "SSL_CLIENT_S_DN_CN"

_LOGGER = logging.getLogger("pychestrate.envelope.jwks.routes")


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

        Walks the explicit test seam, the WSGI environ dict, and the
        webworks ``scope`` dict — same probe order as
        :func:`signing_keys_routes._resolve_mtls_client_cn`.

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


def _read_if_none_match(request: Request) -> str:
    """
        Read the ``If-None-Match`` request header, normalized to a
        stripped string (empty when the header is absent).

        HTTP field names are case-insensitive (RFC 9110 section 5.1)
        and HTTP/2 lowercases every one of them on the wire, so the
        canonically-cased lookup is backed by a case-insensitive scan
        rather than trusted on its own. Missing the header only costs
        a full 200 instead of a 304, which is why this reads
        defensively instead of failing.

        :param request: Incoming webworks request.

        :returns: Header value or an empty string.
    """
    direct = request.get_header(IF_NONE_MATCH_HEADER, "")
    if direct is not None:
        normalized_direct = str(direct).strip()
        if len(normalized_direct) > 0:
            rtnval = normalized_direct
            return rtnval

    wanted = IF_NONE_MATCH_HEADER.lower()
    for name, value in request.headers.items():
        if str(name).lower() == wanted:
            rtnval = str(value).strip()
            return rtnval

    rtnval = ""
    return rtnval


def build_jwks_document(*, jwk_list: List[Dict[str, str]]) -> Dict[str, Any]:
    """
        Wrap a JWK list in the RFC 7517 JWK Set envelope.

        :param jwk_list: JWKs from
                         :func:`signer.active_signing_jwk_list`.

        :returns: ``{"keys": [...]}`` document.
    """
    rtnval: Dict[str, Any] = {"keys": jwk_list}
    return rtnval


def compute_jwks_etag(*, document: Dict[str, Any]) -> str:
    """
        Derive a strong ``ETag`` from a JWK Set document.

        The digest runs over a canonical rendering (sorted keys, no
        insignificant whitespace) so two processes holding the same
        key set produce the same validator — which is what makes the
        ``ETag`` usable behind more than one gunicorn worker.

        :param document: The JWK Set document about to be served.

        :returns: Strong entity-tag — the hex digest wrapped in the
                  double quotes RFC 9110 section 8.8.3 requires.
    """
    canonical_text = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    rtnval = '"{}"'.format(digest)
    return rtnval


def _if_none_match_matches(*, header_value: str, etag: str) -> bool:
    """
        Evaluate an ``If-None-Match`` header against the current
        ``ETag`` per RFC 9110 section 13.1.2.

        Accepts the ``*`` wildcard and a comma-separated candidate
        list, and compares weakly (``W/`` prefix ignored) — which is
        the comparison RFC 9110 mandates for ``If-None-Match``.

        :param header_value: Raw, stripped header text.
        :param etag: The entity-tag the handler would serve.

        :returns: True when the client's cached copy is current.
    """
    if len(header_value) == 0:
        rtnval = False
        return rtnval

    if header_value == "*":
        rtnval = True
        return rtnval

    candidates = header_value.split(",")
    for candidate in candidates:
        normalized = candidate.strip()
        if normalized.startswith("W/"):
            normalized = normalized[2:]
        if normalized == etag:
            rtnval = True
            return rtnval

    rtnval = False
    return rtnval


def _build_not_modified_response(*, etag: str) -> Response:
    """
        Build the ``304 Not Modified`` answer for a client whose
        cached JWK Set is still current. Carries no body; repeats the
        validator and freshness headers so the client can extend its
        cache entry.

        :param etag: The current entity-tag.

        :returns: Empty-bodied 304 :class:`Response`.
    """
    headers = {
        "ETag": etag,
        "Cache-Control": JWKS_CACHE_CONTROL_VALUE,
    }
    rtnval = Response(status_code=304, body=b"", headers=headers)
    return rtnval


def _build_jwks_response(
        *,
        document: Dict[str, Any],
        etag: str
    ) -> Response:
    """
        Build the ``200 OK`` JWK Set answer with its media type,
        validator, and freshness headers.

        :param document: The ``{"keys": [...]}`` document.
        :param etag: The current entity-tag.

        :returns: 200 :class:`JSONResponse`.
    """
    response = JSONResponse(content=document, status_code=200)
    response.set_header("Content-Type", JWK_SET_MEDIA_TYPE)
    response.set_header("Cache-Control", JWKS_CACHE_CONTROL_VALUE)
    response.set_header("ETag", etag)
    rtnval: Response = response
    return rtnval


def handle_get_envelope_jwks(request: Request) -> Response:
    """
        ``GET /api/v1/envelope-signing-keys/jwks.json`` — publish the
        envelope-signing public keys as an RFC 7517 JWK Set.

        Returns 401 for an anonymous request, 503 when no signing key
        has been provisioned, 304 when the caller's ``If-None-Match``
        already matches, and 200 with the JWK Set otherwise.

        :param request: Incoming webworks request.

        :returns: 200 JWK Set / 304 revalidation / 401 / 503 problem
                  responses.
    """
    authenticated = _request_is_authenticated(request=request)
    if authenticated is False:
        rtnval: Response = problem_response_for_http_status(
            status=401,
            detail="Authentication required",
            instance=request.path,
        )
        return rtnval

    jwk_list = signer.active_signing_jwk_list()
    if len(jwk_list) == 0:
        rtnval = problem_response_for_http_status(
            status=503,
            detail="Envelope signing key is not provisioned",
            instance=request.path,
        )
        return rtnval

    document = build_jwks_document(jwk_list=jwk_list)
    etag = compute_jwks_etag(document=document)

    if_none_match = _read_if_none_match(request=request)
    is_current = _if_none_match_matches(
        header_value=if_none_match,
        etag=etag,
    )
    if is_current is True:
        _LOGGER.debug(
            "pychestrate.envelope.jwks.not_modified etag=%s",
            etag,
        )
        rtnval = _build_not_modified_response(etag=etag)
        return rtnval

    rtnval = _build_jwks_response(document=document, etag=etag)
    return rtnval


def register_envelope_jwks_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the envelope-signing JWK Set route to a webworks
        application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + ENVELOPE_JWKS_PATH
    app.attach_route(base, methods=["GET"])(handle_get_envelope_jwks)
    return


__all__ = [
    "ENVELOPE_JWKS_PATH",
    "IF_NONE_MATCH_HEADER",
    "JWKS_CACHE_CONTROL_VALUE",
    "JWKS_CACHE_MAX_AGE_SECONDS",
    "JWK_SET_MEDIA_TYPE",
    "MTLS_CLIENT_CN_ENVIRON_KEY",
    "build_jwks_document",
    "compute_jwks_etag",
    "handle_get_envelope_jwks",
    "register_envelope_jwks_routes",
]
