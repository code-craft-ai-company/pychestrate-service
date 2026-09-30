"""
.. module:: embed.restapi.v1.embed_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the embeddable-views surface.

.. moduleauthor:: Code Craft AI LLC

Exposes the ``8-embeddable-views`` domain over webworks. Three
routes:

* ``GET  /api/v1/embed/views``
  — list the fixed catalog of embeddable view kinds. RBAC-gated on
  ``system:embed.read``.
* ``POST /api/v1/embed/views/{view_key}:sign``
  — mint a signed embed URL for a view kind. RBAC-gated on
  ``system:embed.sign``. Returns ``{url, key_id, expires_unix,
  expires_at, ttl_seconds, view_kind, iframe_snippet,
  webcomponent_snippet}``.
* ``GET  /embed/{view_key}``
  — the chromeless embed-serving endpoint. Auth IS the signed token
  carried in the URL query string (``a``/``e``/``k``/``s``), not a
  session cookie. Verifies the token via
  :mod:`embed.signing` and, on success, renders a minimal HTML
  document hosting the view kind's Layer 9 WebComponent. Bad,
  tampered, or expired tokens answer 401/403 with a chromeless HTML
  stub.

Operator routes (``/api/v1/embed/...``) emit RFC 7807 problem
documents via :mod:`api.problem_json_webworks`. The serving route
returns minimal HTML on every path because its consumers are
``<iframe>`` hosts that cannot parse a JSON problem document.

**Not served by default (ORC-07).** The surface does not work end to end yet:
``POST .../views/{view_key}:sign`` is unreachable (the router does not treat a
path segment such as ``{view_key}:sign`` as a parameter, so it answers 405), the
serving page loads no script, four of the five component tags
(``pyc-log-stream``, ``pyc-artifact-preview``, ``pyc-pipeline-dag``,
``pyc-metric-tile``) are not defined by any bundle, and the scopes the catalog
declares (``system:run.read`` and others) are not in the permission catalog. A
list endpoint that answers 200 for views that cannot be embedded is worse than
no endpoint, so the application registers these routes only when
``PYCHESTRATE_EMBED_ENABLED`` is set (see :func:`embed_views_enabled`). The
OpenAPI document marks the operations ``planned``.

The signing key store lives in ``1-secrets-vault`` in the final
design; until that wiring lands, :mod:`embed.key_provider` supplies
a process-stable HMAC key so issuance and verification agree within
a process lifetime.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from datetime import datetime, timezone
from html import escape as html_escape
from typing import Any, Dict, Optional

from ccai.errors.exceptions import ConfigurationError, SemanticError

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import HTMLResponse, JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.embed import key_provider
from ccai.pychestrate.webservice.embed.signing import (
    AUDIENCE_QUERY_KEY,
    EXPIRES_QUERY_KEY,
    KEY_ID_QUERY_KEY,
    SIGNATURE_QUERY_KEY,
    VerificationOutcome,
    issue_signed_url,
    verify_signed_url,
)
from ccai.pychestrate.webservice.embed.view_catalog import (
    EmbedViewKind,
    get_view_kind,
    list_view_kinds,
)
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


#: The variable that turns the embeddable-views routes on (they are off by default).
EMBED_ENABLED_VARIABLE = "PYCHESTRATE_EMBED_ENABLED"

EMBED_API_PATH = "/embed/views"
EMBED_SERVE_PATH = "/embed"

EMBED_READ_PERMISSION_KEY = "system:embed.read"
EMBED_SIGN_PERMISSION_KEY = "system:embed.sign"

DEFAULT_TTL_SECONDS = 3600
MAX_TTL_SECONDS = 86400
MIN_TTL_SECONDS = 1

_LOGGER = logging.getLogger("pychestrate.embed.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing (operator routes)
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a webworks problem
        response so nested helpers can signal an error once and the
        top-level handler converts it at the boundary.
    """

    def __init__(self, response: Response) -> None:
        super().__init__("problem abort")
        self.response: Response = response
        return


def _abort_problem(
        *,
        request: Request,
        status: int,
        detail: str,
        extensions: Optional[Dict[str, Any]] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional namespaced extension members.

        :returns: Never returns.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session or ``None``.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session.
    """
    db_session = _resolve_db_session(request=request)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
    return rtnval


def _resolve_auth_principal(request: Request) -> Optional[Any]:
    """
        Return the ``AuthPrincipal`` attached by the session
        middleware, or ``None`` when the request is anonymous.

        :param request: Incoming webworks request.

        :returns: AuthPrincipal or None.
    """
    rtnval = getattr(request, "auth_principal", None)
    return rtnval


def _require_permission(
        *,
        request: Request,
        db_session: Any,
        permission_key: str
    ) -> Any:
    """
        Require the calling principal to hold ``permission_key``.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param permission_key: Required ``system:*`` permission key.

        :returns: The :class:`AuthPrincipal`.
    """
    principal = _resolve_auth_principal(request=request)
    if principal is None:
        _abort_problem(
            request=request,
            status=401,
            detail="Authentication required.",
        )

    now = datetime.now(timezone.utc)
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=permission_key,
        now=now,
    )
    if decision.allowed is False:
        _abort_problem(
            request=request,
            status=403,
            detail="Permission denied: {}".format(permission_key),
            extensions={"required_permission": permission_key},
        )
    rtnval = principal
    return rtnval


def _decode_json_object_or_abort(*, request: Request) -> Dict[str, Any]:
    """
        Decode the request body as a JSON object, aborting 422 on a
        missing / malformed / non-dict body. An empty body is
        tolerated as an empty object so defaults apply.

        :param request: Incoming webworks request.

        :returns: Decoded dict.
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        rtnval: Dict[str, Any] = {}
        return rtnval
    if isinstance(payload, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Request body must be a JSON object.",
        )

    rtnval = payload
    return rtnval


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _view_kind_to_dict(*, view_kind: EmbedViewKind) -> Dict[str, Any]:
    """
        Render an :class:`EmbedViewKind` as a JSON-friendly dict.

        :param view_kind: Catalog entry.

        :returns: Dict matching the OpenAPI ``EmbedViewKind`` schema.
    """
    rtnval: Dict[str, Any] = {
        "view_kind": view_kind.view_kind_name,
        "component_tag": view_kind.component_tag,
        "declared_read_scope": list(view_kind.declared_read_scope),
        "supports_anonymous": view_kind.supports_anonymous,
    }
    return rtnval


def _iframe_snippet(*, url: str) -> str:
    """
        Build a ready-to-paste ``<iframe>`` snippet for a signed URL.

        :param url: Signed embed URL.

        :returns: HTML iframe snippet string.
    """
    rtnval = (
        '<iframe src="{url}" loading="lazy" '
        'style="border:0;width:100%;height:480px" '
        'referrerpolicy="no-referrer"></iframe>'
    ).format(url=url)
    return rtnval


def _webcomponent_snippet(*, url: str, component_tag: str) -> str:
    """
        Build a ready-to-paste WebComponent snippet for a signed URL.

        :param url: Signed embed URL.
        :param component_tag: Layer 9 WebComponent tag.

        :returns: HTML WebComponent snippet string.
    """
    rtnval = '<{tag} embed-src="{url}"></{tag}>'.format(
        tag=component_tag, url=url
    )
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/embed/views
# ---------------------------------------------------------------------------


def embed_views_enabled() -> bool:
    """
        Whether the application should register the embeddable-views routes.

        They are off unless ``PYCHESTRATE_EMBED_ENABLED`` is ``1``, ``true``,
        ``yes`` or ``on`` (any case): the surface is unfinished (see the module
        note).

        :returns: ``True`` when the routes should be registered.
    """
    value = os.environ.get(EMBED_ENABLED_VARIABLE, "")
    rtnval = value.strip().lower() in ("1", "true", "yes", "on")
    return rtnval


def handle_list_views(request: Request) -> Response:
    """
        ``GET /api/v1/embed/views`` — list the fixed catalog of
        embeddable view kinds. RBAC-gated on ``system:embed.read``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items}`` body, or a
                  problem response.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=EMBED_READ_PERMISSION_KEY,
        )

        items = []
        for view_kind in list_view_kinds():
            items.append(_view_kind_to_dict(view_kind=view_kind))

        body = {"items": items, "total": len(items)}
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/embed/views/{view_key}:sign
# ---------------------------------------------------------------------------


def _resolve_ttl_seconds(*, request: Request, body: Dict[str, Any]) -> int:
    """
        Resolve and bounds-check the requested ``ttl_seconds``.

        :param request: Incoming webworks request.
        :param body: Decoded JSON body.

        :returns: Validated TTL in seconds.
    """
    raw_ttl = body.get("ttl_seconds", None)
    if raw_ttl is None:
        rtnval = DEFAULT_TTL_SECONDS
        return rtnval

    if isinstance(raw_ttl, bool) is True or isinstance(raw_ttl, int) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'ttl_seconds' must be an integer.",
        )
    if raw_ttl < MIN_TTL_SECONDS:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'ttl_seconds' must be >= {}.".format(MIN_TTL_SECONDS),
        )
    if raw_ttl > MAX_TTL_SECONDS:
        _abort_problem(
            request=request,
            status=400,
            detail="Requested ttl_seconds exceeds the maximum of {}.".format(
                MAX_TTL_SECONDS
            ),
            extensions={"code": "embed.ttl_exceeded", "max_ttl_seconds": MAX_TTL_SECONDS},
        )

    rtnval = int(raw_ttl)
    return rtnval


def _principal_audience(*, principal: Any) -> str:
    """
        Derive a default audience from the issuing principal.

        :param principal: The :class:`AuthPrincipal`.

        :returns: The principal's primary email, or a stable
                  fallback when none is available.
    """
    email = getattr(principal, "email", None)
    if isinstance(email, str) is True and len(email) > 0:
        rtnval = email
        return rtnval
    user_id = getattr(principal, "user_id", None)
    if user_id is not None:
        rtnval = "principal:{}".format(str(user_id))
        return rtnval
    rtnval = "principal:unknown"
    return rtnval


def handle_sign_view(request: Request) -> Response:
    """
        ``POST /api/v1/embed/views/{view_key}:sign`` — mint a signed
        embed URL for a view kind. RBAC-gated on
        ``system:embed.sign``.

        Body (all optional): ``{resource_id, audience, ttl_seconds}``.
        ``resource_id`` defaults to the view key; ``audience``
        defaults to the issuing principal's email; ``ttl_seconds``
        defaults to 3600 and is capped at 86400.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the signed URL + paste
                  snippets, or a problem response.
    """
    view_key = request.path_params.get("view_key", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=EMBED_SIGN_PERMISSION_KEY,
        )

        try:
            view_kind = get_view_kind(view_kind_name=view_key)
        except ConfigurationError:
            _abort_problem(
                request=request,
                status=404,
                detail="Unknown embed view kind: {}".format(view_key),
                extensions={"code": "embed.unknown_view_kind", "view_kind": view_key},
            )
            view_kind = None  # unreachable

        body = _decode_json_object_or_abort(request=request)

        resource_id = body.get("resource_id", None)
        if resource_id is None or (
            isinstance(resource_id, str) and len(resource_id) == 0
        ):
            resource_id = view_kind.view_kind_name
        if isinstance(resource_id, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'resource_id' must be a string.",
            )

        audience = body.get("audience", None)
        if audience is None or (
            isinstance(audience, str) and len(audience) == 0
        ):
            audience = _principal_audience(principal=principal)
        if isinstance(audience, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'audience' must be a string.",
            )

        ttl_seconds = _resolve_ttl_seconds(request=request, body=body)

        signing_key = key_provider.get_active_signing_key()
        now_unix = int(datetime.now(timezone.utc).timestamp())

        try:
            signed = issue_signed_url(
                view_kind=view_kind.view_kind_name,
                resource_id=resource_id,
                audience=audience,
                ttl_seconds=ttl_seconds,
                signing_key=signing_key,
                now_unix=now_unix,
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"view_kind": view_kind.view_kind_name},
            )
            signed = None  # unreachable

        expires_at = datetime.fromtimestamp(
            signed.expires_unix, tz=timezone.utc
        ).isoformat()

        body_dict = {
            "url": signed.url,
            "key_id": signed.key_id,
            "expires_unix": signed.expires_unix,
            "expires_at": expires_at,
            "ttl_seconds": ttl_seconds,
            "view_kind": view_kind.view_kind_name,
            "resource_id": resource_id,
            "audience": audience,
            "iframe_snippet": _iframe_snippet(url=signed.url),
            "webcomponent_snippet": _webcomponent_snippet(
                url=signed.url, component_tag=view_kind.component_tag
            ),
        }

        _LOGGER.info(
            "pychestrate.embed.url_issued view_kind=%s resource_id=%s key_id=%s",
            view_kind.view_kind_name,
            resource_id,
            signed.key_id,
        )

        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /embed/{view_key}  (chromeless, token-auth serving route)
# ---------------------------------------------------------------------------


#: What a person looking at a rejected embed is told, by rejection reason.
#: The reason itself stays machine-readable on the page (``data-embed-error``).
EMBED_ERROR_MESSAGES: Dict[str, str] = {
    "unknown_view_kind": "This view does not exist.",
    "malformed_payload": "The link is incomplete.",
    "signature_mismatch": "The link is not valid.",
    "expired": "The link has expired.",
    "signing_key_unknown": "The link was signed with a key this service no longer accepts.",
}

_EMBED_ERROR_FALLBACK_MESSAGE: str = "The link could not be accepted."


def _embed_error_html(*, status: int, reason: str) -> str:
    """
        Build the small, styled chromeless page an embed shows when its
        signed URL is rejected (ORC-46). It sits inside someone else's
        page, so it says what happened in plain words and who can fix it,
        follows the light / dark tokens, and carries no navigation.

        :param status: HTTP status code.
        :param reason: Machine-readable rejection reason.

        :returns: HTML document string.
    """
    message = EMBED_ERROR_MESSAGES.get(reason, _EMBED_ERROR_FALLBACK_MESSAGE)
    rtnval = (
        "<!DOCTYPE html><html lang=\"en\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Embed unavailable</title>"
        "<link rel=\"stylesheet\" href=\"/static/styles/pyc-tokens.css\">"
        "<style>"
        "body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;"
        "background:var(--pyc-color-app-bg,#f5f5f7);color:var(--pyc-color-on-surface,#1a1a2e);"
        "font-family:var(--pyc-font-family-base,-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,sans-serif)}}"
        "main{{box-sizing:border-box;max-width:28rem;margin:1rem;padding:1.5rem;text-align:center;"
        "background:var(--pyc-color-surface,#fff);border:1px solid var(--pyc-color-border,#dee2e6);border-radius:8px}}"
        "h1{{margin:0 0 .5rem;font-size:1.125rem}}"
        "p{{margin:.25rem 0}}"
        ".muted{{color:var(--pyc-color-on-surface-muted,#5a6072);font-size:.875rem}}"
        "</style></head>"
        "<body><main data-embed-error=\"{reason}\">"
        "<h1>This embed could not be displayed</h1>"
        "<p>{message}</p>"
        "<p class=\"muted\">Ask whoever shared it for a new link. (Error {status})</p>"
        "</main></body></html>"
    ).format(reason=html_escape(reason, quote=True), message=html_escape(message), status=int(status))
    return rtnval


def _embed_document_html(
        *,
        view_kind: EmbedViewKind,
        resource_id: str
    ) -> str:
    """
        Build the minimal chromeless HTML document hosting the view
        kind's Layer 9 WebComponent.

        :param view_kind: Resolved catalog entry.
        :param resource_id: Resource id from the signed URL.

        :returns: HTML document string.
    """
    rtnval = (
        "<!DOCTYPE html><html lang=\"en\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Pychestrate embed</title></head>"
        "<body data-embed-view=\"{view_kind}\">"
        "<{tag} resource-id=\"{resource_id}\"></{tag}>"
        "</body></html>"
    ).format(
        view_kind=view_kind.view_kind_name,
        tag=view_kind.component_tag,
        resource_id=resource_id,
    )
    return rtnval


def _verification_status(*, outcome: VerificationOutcome) -> int:
    """
        Map a :class:`VerificationOutcome` to an HTTP status code.

        ``MALFORMED_PAYLOAD`` (a missing / unparseable token) reads
        as 401 — the request did not present usable credentials.
        Every other non-verified outcome (signature mismatch,
        expired, unknown key) reads as 403 — credentials were
        presented but rejected.

        :param outcome: The verification result.

        :returns: HTTP status code.
    """
    if outcome == VerificationOutcome.MALFORMED_PAYLOAD:
        rtnval = 401
        return rtnval
    rtnval = 403
    return rtnval


def handle_serve_embed(request: Request) -> Response:
    """
        ``GET /embed/{view_key}?a=&e=&k=&s=`` — the chromeless embed
        serving endpoint. Auth IS the signed token in the query
        string, not a session. Verifies the token via
        :func:`embed.signing.verify_signed_url` and renders the
        view's Layer 9 WebComponent on success.

        :param request: Incoming webworks request.

        :returns: HTML response (200) with the embed document, or an
                  HTML stub (401/403/404).
    """
    view_key = request.path_params.get("view_key", "")
    query_params = request.query_params

    resource_id = query_params.get("resource_id", "")
    audience = query_params.get(AUDIENCE_QUERY_KEY, "")
    expires_raw = query_params.get(EXPIRES_QUERY_KEY, "")
    key_id = query_params.get(KEY_ID_QUERY_KEY, "")
    signature_hex = query_params.get(SIGNATURE_QUERY_KEY, "")

    try:
        view_kind = get_view_kind(view_kind_name=view_key)
    except ConfigurationError:
        rtnval: Response = HTMLResponse(
            content=_embed_error_html(status=404, reason="unknown_view_kind"),
            status_code=404,
        )
        return rtnval

    # The serving URL carries the resource id either on the path-adjacent
    # query string or, when absent, defaults to the view kind name --
    # matching the :sign default so a default-resource sign round-trips.
    if resource_id is None or len(resource_id) == 0:
        resource_id = view_kind.view_kind_name

    try:
        expires_unix = int(expires_raw)
    except (TypeError, ValueError):
        _LOGGER.info(
            "pychestrate.embed.url_rejected view_kind=%s reason=%s",
            view_key,
            "malformed_payload",
        )
        rtnval = HTMLResponse(
            content=_embed_error_html(status=401, reason="malformed_payload"),
            status_code=401,
        )
        return rtnval

    now_unix = int(datetime.now(timezone.utc).timestamp())

    outcome = verify_signed_url(
        view_kind=view_key,
        resource_id=resource_id,
        audience=audience,
        expires_unix=expires_unix,
        key_id=key_id,
        signature_hex=signature_hex,
        now_unix=now_unix,
        key_resolver=key_provider.resolve_signing_key,
    )

    if outcome != VerificationOutcome.VERIFIED:
        status = _verification_status(outcome=outcome)
        _LOGGER.info(
            "pychestrate.embed.url_rejected view_kind=%s reason=%s",
            view_key,
            outcome.value,
        )
        rtnval = HTMLResponse(
            content=_embed_error_html(status=status, reason=outcome.value),
            status_code=status,
        )
        return rtnval

    _LOGGER.info(
        "pychestrate.embed.url_verified view_kind=%s resource_id=%s",
        view_key,
        resource_id,
    )
    rtnval = HTMLResponse(
        content=_embed_document_html(
            view_kind=view_kind, resource_id=resource_id
        ),
        status_code=200,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_embed_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the embeddable-views REST routes to a webworks app.

        The two operator routes mount under ``version_prefix`` (i.e.
        ``/api/v1/embed/...``). The serving route mounts at the
        top-level ``/embed/{view_key}`` so it is reachable by
        ``<iframe>`` hosts without an ``/api`` prefix; it is a
        chromeless surface (see
        :mod:`webinterface.site_shell.chromeless_routes`).

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    api_base = version_prefix + EMBED_API_PATH

    app.attach_route(api_base, methods=["GET"])(handle_list_views)
    app.attach_route(
        api_base + "/{view_key}:sign", methods=["POST"]
    )(handle_sign_view)
    app.attach_route(
        EMBED_SERVE_PATH + "/{view_key}", methods=["GET"]
    )(handle_serve_embed)

    _LOGGER.info(
        "pychestrate.embed.routes.registered: GET %s, POST %s/{view_key}:sign,"
        " GET %s/{view_key} (chromeless token-auth serving route)",
        api_base,
        api_base,
        EMBED_SERVE_PATH,
    )
    return


__all__ = [
    "EMBED_ENABLED_VARIABLE",
    "embed_views_enabled",
    "EMBED_API_PATH",
    "EMBED_SERVE_PATH",
    "EMBED_READ_PERMISSION_KEY",
    "EMBED_SIGN_PERMISSION_KEY",
    "DEFAULT_TTL_SECONDS",
    "MAX_TTL_SECONDS",
    "register_embed_routes",
    "handle_list_views",
    "handle_sign_view",
    "handle_serve_embed",
]
