"""
.. module:: secrets.restapi.v1.secrets_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/secrets.

.. moduleauthor:: Automation Mojo LLC

The production webservice runs on ``automojo.webworks`` (see
:mod:`app_pychestrate_main`). This module provides the
webworks-native ``secrets`` controller.

Full CRUD, scope-aware (org / project / user) — PR p20g:

* ``GET    /api/v1/secrets`` — list secret metadata; ``scope_kind``
  / ``scope_ref`` query filters.
* ``POST   /api/v1/secrets`` — create a secret (value KEK-encrypted
  at rest; plaintext is NEVER persisted or echoed back).
* ``GET    /api/v1/secrets/value/{secret_ref:path}`` — read the
  decrypted secret value. Heavily permission-gated + audit-logged.
* ``GET    /api/v1/secrets/{secret_ref:path}`` — read metadata only.
* ``PUT    /api/v1/secrets/{secret_ref:path}`` — rotate / update the
  value.
* ``DELETE /api/v1/secrets/{secret_ref:path}`` — delete a secret.

Metadata responses NEVER carry the secret value. Only the dedicated
``.../value`` route returns plaintext, and only to authorized callers.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "2.0.0"


from typing import Any, Optional

from automojo.errors.exceptions import SemanticError
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.secrets import secrets_service
from automojo.pychestrate.webservice.secrets.exceptions import (
    SecretAccessDeniedError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretVersionExpiredError,
)
from automojo.pychestrate.webservice.secrets.models import (
    SecretRecord,
    SecretScopeKind,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.secrets.secrets_aspects import (
    build_default_aspects,
)


SECRETS_PATH = "/secrets"


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition once
        and the handler can convert it to a return at the boundary.
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
        secret_ref: Optional[str] = None,
        extensions: Optional[dict] = None
    ) -> None:
    """
        Build a problem response from the request context and raise
        :class:`_ProblemAbort` so the handler returns the response.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param secret_ref: Optional secret_ref to attach as an
                           extension member.
        :param extensions: Optional additional extension members.

        :returns: Never returns; raises :class:`_ProblemAbort`.
    """
    resolved_extensions: Optional[dict] = None
    if secret_ref is not None or extensions is not None:
        resolved_extensions = {}
        if secret_ref is not None:
            resolved_extensions["secret_ref"] = secret_ref
        if extensions is not None:
            resolved_extensions.update(extensions)

    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=resolved_extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session attached by
        :class:`PychestrateSessionMiddleware`.

        :param request: Incoming webworks request.

        :returns: Session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort with a 503
        problem document.

        :param request: Incoming webworks request.

        :returns: Session.
        :raises: :class:`_ProblemAbort` (503).
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


def _require_principal(request: Request) -> Any:
    """
        Resolve the authenticated principal or abort with a 401.

        :param request: Incoming webworks request.

        :returns: AuthPrincipal.
        :raises: :class:`_ProblemAbort` (401).
    """
    principal = _resolve_auth_principal(request=request)
    if principal is None:
        _abort_problem(
            request=request,
            status=401,
            detail="Authentication required.",
        )
    rtnval = principal
    return rtnval


def _parse_scope_kind_or_abort(
        *, request: Request, raw: str
    ) -> SecretScopeKind:
    """
        Coerce a ``scope_kind`` string to the enum, aborting 400 with
        the raw value as an extension on unknown values.

        :param request: Incoming webworks request.
        :param raw: Raw string value.

        :returns: :class:`SecretScopeKind`.
    """
    normalized = raw.strip().upper()
    try:
        scope_kind = SecretScopeKind[normalized]
    except KeyError:
        _abort_problem(
            request=request,
            status=400,
            detail="Unknown scope_kind: {}".format(raw),
            extensions={"scope_kind": raw},
        )

    rtnval = scope_kind
    return rtnval


def _decode_json_or_abort(*, request: Request) -> dict:
    """
        Decode the request body as a JSON object, aborting 400 on a
        missing / malformed / non-dict body.

        :param request: Incoming webworks request.

        :returns: Decoded dict.
        :raises: :class:`_ProblemAbort` (400).
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request, status=400, detail="Request body must be JSON"
        )
    if not isinstance(payload, dict):
        _abort_problem(
            request=request,
            status=400,
            detail="Request body must be a JSON object",
        )

    rtnval = payload
    return rtnval


def _record_to_dict(record: SecretRecord) -> dict:
    """
        Render a :class:`SecretRecord` ORM row as a JSON-safe dict.
        Metadata only — the secret value is NEVER returned.

        :param record: ORM record.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "secret_ref": record.secret_ref,
        "backend_name": record.backend_name,
        "scope_kind": record.scope_kind.value,
        "scope_ref": (
            str(record.scope_ref) if record.scope_ref is not None else None
        ),
        "current_version_id": (
            str(record.current_version_id)
            if record.current_version_id is not None else None
        ),
        "created_at": (
            record.created_at.isoformat()
            if record.created_at is not None else None
        ),
        "updated_at": (
            record.updated_at.isoformat()
            if record.updated_at is not None else None
        ),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_list_secrets(request: Request) -> Response:
    """
        ``GET /api/v1/secrets`` — list secret metadata, ordered by
        ``secret_ref`` ascending, optionally filtered by
        ``scope_kind`` / ``scope_ref``.

        The list NEVER carries secret values.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a list of metadata
                  dicts, or problem response on failure.
    """
    try:
        db_session = _require_session(request=request)

        scope_kind_arg = request.query_params.get("scope_kind", None)
        scope_ref_arg = request.query_params.get("scope_ref", None)

        scope_kind: Optional[SecretScopeKind] = None
        if scope_kind_arg is not None and len(scope_kind_arg.strip()) > 0:
            scope_kind = _parse_scope_kind_or_abort(
                request=request, raw=scope_kind_arg
            )

        records = secrets_service.list_secrets(
            db_session=db_session,
            scope_kind=scope_kind,
            scope_ref=scope_ref_arg,
        )
        body = [_record_to_dict(record) for record in records]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_create_secret(request: Request) -> Response:
    """
        ``POST /api/v1/secrets`` — create a secret. The body carries
        ``name`` (the ``secret_ref``), ``scope_kind``, ``scope_ref``,
        and ``value``. The value is KEK-encrypted at rest; it is
        NEVER persisted in plaintext nor echoed in the response.

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the secret metadata dict,
                  or problem response on failure.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        principal = _require_principal(request=request)

        secret_ref = str(payload.get("name", "") or payload.get("secret_ref", ""))
        if len(secret_ref.strip()) == 0:
            _abort_problem(
                request=request,
                status=400,
                detail="Request body must carry a non-empty 'name'.",
            )

        raw_scope = str(payload.get("scope_kind", "ORG"))
        scope_kind = _parse_scope_kind_or_abort(request=request, raw=raw_scope)
        scope_ref = payload.get("scope_ref", None)

        raw_value = payload.get("value", None)
        if raw_value is None:
            _abort_problem(
                request=request,
                status=400,
                detail="Request body must carry a 'value'.",
                secret_ref=secret_ref,
            )

        plaintext = SecretBytes(str(raw_value).encode("utf-8"))

        try:
            version = secrets_service.put_secret(
                db_session=db_session,
                principal=principal,
                secret_ref=secret_ref,
                plaintext=plaintext,
                aspects=build_default_aspects(),
                scope_kind=scope_kind,
                scope_ref=scope_ref,
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                secret_ref=secret_ref,
            )
        except SecretAlreadyExistsError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                secret_ref=secret_ref,
            )
        except SecretAccessDeniedError as xcpt:
            _abort_problem(
                request=request,
                status=403,
                detail=str(xcpt),
                secret_ref=secret_ref,
            )

        record = secrets_service.get_secret_record(
            db_session=db_session, secret_ref=secret_ref
        )
        body = _record_to_dict(record)
        body["current_version_id"] = str(version.version_id)
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_secret(request: Request) -> Response:
    """
        ``GET /api/v1/secrets/{secret_ref:path}`` — read metadata for
        one secret. Returns 404 problem+json with the secret_ref as
        an extension member when the record does not exist.

        The metadata response NEVER carries the secret value.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the metadata dict, or
                  problem response on failure.
    """
    secret_ref = request.path_params.get("secret_ref", "")
    try:
        db_session = _require_session(request=request)

        record = (
            db_session.query(SecretRecord)
            .filter(SecretRecord.secret_ref == secret_ref)
            .first()
        )
        if record is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Secret not found: {}".format(secret_ref),
                secret_ref=secret_ref,
            )

        body = _record_to_dict(record)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_secret_value(request: Request) -> Response:
    """
        ``GET /api/v1/secrets/value/{secret_ref:path}`` — read the
        decrypted secret value. This is the sensitive operation: the
        scope-aware ACL is enforced and an ``audit.secret.accessed``
        record is emitted by the service layer.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying ``{secret_ref,
                  version_number, value}``, or problem response.
    """
    secret_ref = request.path_params.get("secret_ref", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_principal(request=request)

        try:
            result = secrets_service.read_secret(
                db_session=db_session,
                principal=principal,
                secret_ref=secret_ref,
                aspects=build_default_aspects(),
            )
        except SecretNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                secret_ref=secret_ref,
            )
        except SecretAccessDeniedError as xcpt:
            _abort_problem(
                request=request,
                status=403,
                detail=str(xcpt),
                secret_ref=secret_ref,
            )
        except SecretVersionExpiredError as xcpt:
            _abort_problem(
                request=request,
                status=410,
                detail=str(xcpt),
                secret_ref=secret_ref,
            )

        value_text = result.plaintext.reveal().decode("utf-8")
        body = {
            "secret_ref": result.secret_ref,
            "version_number": int(result.version_number),
            "value": value_text,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_update_secret(request: Request) -> Response:
    """
        ``PUT /api/v1/secrets/{secret_ref:path}`` — rotate / update a
        secret's value. The body carries ``value``. The new value is
        KEK-encrypted at rest; ``audit.secret.updated`` is emitted.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the updated metadata dict,
                  or problem response on failure.
    """
    secret_ref = request.path_params.get("secret_ref", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        principal = _require_principal(request=request)

        raw_value = payload.get("value", None)
        if raw_value is None:
            _abort_problem(
                request=request,
                status=400,
                detail="Request body must carry a 'value'.",
                secret_ref=secret_ref,
            )

        plaintext = SecretBytes(str(raw_value).encode("utf-8"))

        try:
            version = secrets_service.update_secret(
                db_session=db_session,
                principal=principal,
                secret_ref=secret_ref,
                plaintext=plaintext,
                aspects=build_default_aspects(),
            )
        except SecretNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                secret_ref=secret_ref,
            )
        except SecretAccessDeniedError as xcpt:
            _abort_problem(
                request=request,
                status=403,
                detail=str(xcpt),
                secret_ref=secret_ref,
            )

        record = secrets_service.get_secret_record(
            db_session=db_session, secret_ref=secret_ref
        )
        body = _record_to_dict(record)
        body["current_version_id"] = str(version.version_id)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_delete_secret(request: Request) -> Response:
    """
        ``DELETE /api/v1/secrets/{secret_ref:path}`` — delete a
        secret and every version. ``audit.secret.deleted`` is emitted.

        :param request: Incoming webworks request.

        :returns: JSON response (204) on success, or problem response.
    """
    secret_ref = request.path_params.get("secret_ref", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_principal(request=request)

        try:
            secrets_service.delete_secret(
                db_session=db_session,
                principal=principal,
                secret_ref=secret_ref,
                aspects=build_default_aspects(),
            )
        except SecretNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                secret_ref=secret_ref,
            )
        except SecretAccessDeniedError as xcpt:
            _abort_problem(
                request=request,
                status=403,
                detail=str(xcpt),
                secret_ref=secret_ref,
            )

        rtnval: Response = JSONResponse(content=None, status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_secrets_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the scope-aware secrets CRUD routes to a webworks
        application.

        The fixed ``/secrets`` collection and the fixed
        ``/secrets/value/...`` value route register BEFORE the
        ``/{secret_ref:path}`` parameterized routes so the webworks
        router resolves the fixed prefixes deterministically.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + SECRETS_PATH

    app.attach_route(base, methods=["GET"])(handle_list_secrets)
    app.attach_route(base, methods=["POST"])(handle_create_secret)
    app.attach_route(
        base + "/value/{secret_ref:path}", methods=["GET"]
    )(handle_read_secret_value)
    app.attach_route(
        base + "/{secret_ref:path}", methods=["GET"]
    )(handle_read_secret)
    app.attach_route(
        base + "/{secret_ref:path}", methods=["PUT"]
    )(handle_update_secret)
    app.attach_route(
        base + "/{secret_ref:path}", methods=["DELETE"]
    )(handle_delete_secret)

    return


__all__ = [
    "SECRETS_PATH",
    "register_secrets_routes",
    "handle_list_secrets",
    "handle_create_secret",
    "handle_read_secret",
    "handle_read_secret_value",
    "handle_update_secret",
    "handle_delete_secret",
]
