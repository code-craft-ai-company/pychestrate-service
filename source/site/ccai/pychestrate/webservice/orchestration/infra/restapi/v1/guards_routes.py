"""
.. module:: orchestration.infra.restapi.v1.guards_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the blast_radius_guards tag.

.. moduleauthor:: Code Craft AI LLC

Implements the blast-radius-guard operations from
``specs/openapi/pychestrate.yaml``:

* ``GET    /api/v1/projects/{project_id}/blast-radius-guards``
* ``POST   /api/v1/projects/{project_id}/blast-radius-guards``
* ``GET    /api/v1/projects/{project_id}/blast-radius-guards/{guard_id}``
* ``PATCH  /api/v1/projects/{project_id}/blast-radius-guards/{guard_id}``
* ``DELETE /api/v1/projects/{project_id}/blast-radius-guards/{guard_id}``
* ``POST   /api/v1/projects/{project_id}/blast-radius-guards:evaluate``

DOMAIN NOTE -- the in-tree guards facade
(``orchestration.infra.guards.service``) models a *guard
attachment*: the binding of a registry-defined guard rule onto a
single environment. There is no standalone "guard rule" CRUD
entity -- rules are supplied by the ``guard_rule`` factory
registry. A "blast-radius guard" on this REST surface is therefore
an attachment, and the synthetic ``guard_id`` is the composite
``{environment_id}.{rule_id}``. List + create are environment
scoped; the list endpoint requires the ``environment_id`` query
param. ``PATCH`` toggles ``enabled``; ``DELETE`` disables the
attachment (the facade exposes ``disable_attachment`` -- there is
no hard delete). ``:evaluate`` maps to the facade ``explain``
preview.

Error responses are RFC 7807 problem documents emitted via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.orchestration.infra.guards import (
    service as guards_service,
)
from ccai.pychestrate.webservice.orchestration.infra.guards.errors import (
    GuardAttachmentNotFoundError,
    GuardEnvironmentNotFoundError,
    GuardRuleUnknownError,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


GUARDS_PATH_SUFFIX = "/blast-radius-guards"
PROJECTS_PATH_PREFIX = "/projects"

GUARDS_READ_PERMISSION_KEY = "system:guards.read"
GUARDS_WRITE_PERMISSION_KEY = "system:guards.write"

GUARD_ID_SEPARATOR = "."

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

_LOGGER = logging.getLogger("pychestrate.guards.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a webworks
        problem response.
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
        middleware, or ``None`` for anonymous requests.

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
        Decode the request body as a JSON object, aborting with
        422 on missing / malformed / non-dict bodies.

        :param request: Incoming webworks request.

        :returns: Decoded dict.
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request,
            status=422,
            detail="Request body must be JSON.",
        )
    if isinstance(payload, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Request body must be a JSON object.",
        )

    rtnval = payload
    return rtnval


def _require_project_exists(
        *,
        request: Request,
        db_session: Any,
        project_id: str
    ) -> Any:
    """
        Look up the project row, aborting 404 when not found.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param project_id: Project UUID from the path.

        :returns: Project ORM row.
    """
    row = projects_repo.get_project_by_id(
        db_session=db_session,
        project_id=project_id,
    )
    if row is None:
        _abort_problem(
            request=request,
            status=404,
            detail="Project not found.",
            extensions={"project_id": project_id},
        )
    rtnval = row
    return rtnval


def _parse_positive_int(
        *,
        request: Request,
        name: str,
        raw: Optional[str],
        default: int,
        minimum: int,
        maximum: Optional[int] = None
    ) -> int:
    """
        Coerce a positive-integer query param with bounds checking.

        :param request: Incoming webworks request.
        :param name: Query-param name (for error context).
        :param raw: Raw query value or None.
        :param default: Fallback when the param is absent.
        :param minimum: Lower bound (inclusive).
        :param maximum: Optional upper bound (inclusive).

        :returns: Coerced integer.
    """
    if raw is None or len(raw) == 0:
        rtnval = default
        return rtnval

    try:
        candidate = int(raw)
    except ValueError:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be an integer.".format(name),
            extensions={"query_param": name, "raw_value": raw},
        )
        candidate = default  # unreachable

    if candidate < minimum:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be >= {}.".format(name, minimum),
            extensions={"query_param": name, "raw_value": raw},
        )
    if maximum is not None and candidate > maximum:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be <= {}.".format(name, maximum),
            extensions={"query_param": name, "raw_value": raw},
        )

    rtnval = candidate
    return rtnval


def _split_guard_id(*, request: Request, guard_id: str) -> Dict[str, str]:
    """
        Split the synthetic ``{environment_id}.{rule_id}`` guard
        id into its parts, aborting 404 on a malformed id.

        :param request: Incoming webworks request.
        :param guard_id: Composite guard identifier from the path.

        :returns: Dict with ``environment_id`` and ``rule_id``.
    """
    if guard_id is None or GUARD_ID_SEPARATOR not in guard_id:
        _abort_problem(
            request=request,
            status=404,
            detail="Blast-radius guard not found.",
            extensions={"guard_id": guard_id},
        )

    environment_id, _, rule_id = guard_id.partition(GUARD_ID_SEPARATOR)
    if len(environment_id) == 0 or len(rule_id) == 0:
        _abort_problem(
            request=request,
            status=404,
            detail="Blast-radius guard not found.",
            extensions={"guard_id": guard_id},
        )
    rtnval = {"environment_id": environment_id, "rule_id": rule_id}
    return rtnval


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _iso_or_none(value: Any) -> Optional[str]:
    """
        ISO-8601 serialize a datetime or return ``None``.

        :param value: Datetime or None.

        :returns: ISO-formatted string or None.
    """
    if value is None:
        rtnval = None
        return rtnval
    if isinstance(value, datetime):
        rtnval = value.isoformat()
        return rtnval
    rtnval = str(value)
    return rtnval


def _attachment_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`GuardAttachmentView` to the OpenAPI
        ``BlastRadiusGuard`` schema.

        :param view: Read-model returned by the guards facade.

        :returns: JSON-friendly dict.
    """
    guard_id = "{}{}{}".format(
        view.environment_id, GUARD_ID_SEPARATOR, view.rule_id,
    )
    rtnval: Dict[str, Any] = {
        "guard_id": guard_id,
        "project_id": str(view.project_id),
        "environment_id": str(view.environment_id),
        "rule_id": view.rule_id,
        "enabled": bool(view.enabled),
        "added_by": view.added_by,
        "added_at": _iso_or_none(view.added_at),
        "updated_at": _iso_or_none(view.updated_at),
    }
    return rtnval


def _trace_to_dict(trace: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`GuardTrace` to the OpenAPI
        ``BlastRadiusGuardEvaluation`` schema.

        :param trace: Aggregate decision from ``explain``.

        :returns: JSON-friendly dict.
    """
    entries: List[Dict[str, Any]] = []
    for entry in trace.entries:
        verdict = getattr(entry.verdict, "value", entry.verdict)
        entries.append(
            {
                "rule_id": entry.rule_id,
                "verdict": str(verdict),
                "reason": entry.reason,
            }
        )
    rtnval: Dict[str, Any] = {
        "allowed": bool(trace.allowed),
        "failing_rule_id": trace.failing_rule_id,
        "entries": entries,
    }
    return rtnval


def _resolve_actor_id(principal: Any) -> Optional[str]:
    """
        Extract the user id from an :class:`AuthPrincipal`.

        :param principal: Authenticated principal.

        :returns: Stringified user id or None.
    """
    principal_user_id = getattr(principal, "user_id", None)
    if principal_user_id is None:
        rtnval = None
        return rtnval
    rtnval = str(principal_user_id)
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/blast-radius-guards
# ---------------------------------------------------------------------------


def handle_list_guards(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/blast-radius-guards``

        Query params: ``environment_id`` (required -- the guards
        domain is environment scoped), ``enabled_only``, ``page``,
        ``per_page``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items, meta}``
                  page or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=GUARDS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        environment_id = request.query_params.get("environment_id", None)
        if environment_id is None or len(environment_id) == 0:
            _abort_problem(
                request=request,
                status=400,
                detail="Query param 'environment_id' is required.",
                extensions={"query_param": "environment_id"},
            )

        enabled_only_raw = request.query_params.get("enabled_only", None)
        enabled_only = False
        if enabled_only_raw is not None and enabled_only_raw == "true":
            enabled_only = True

        page = _parse_positive_int(
            request=request,
            name="page",
            raw=request.query_params.get("page", None),
            default=1,
            minimum=1,
        )
        per_page = _parse_positive_int(
            request=request,
            name="per_page",
            raw=request.query_params.get("per_page", None),
            default=DEFAULT_PAGE_SIZE,
            minimum=MIN_PAGE_SIZE,
            maximum=MAX_PAGE_SIZE,
        )

        try:
            all_views = guards_service.list_attachments_for_environment(
                db_session=db_session,
                project_id=project_id,
                environment_id=environment_id,
                enabled_only=enabled_only,
            )
        except GuardEnvironmentNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"environment_id": environment_id},
            )
            all_views = []  # unreachable

        total = len(all_views)
        offset = (page - 1) * per_page
        window = all_views[offset:offset + per_page]

        items: List[Dict[str, Any]] = []
        for view in window:
            items.append(_attachment_view_to_dict(view=view))

        body = {
            "items": items,
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": int(total),
                "next_cursor": None,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/blast-radius-guards
# ---------------------------------------------------------------------------


def handle_create_guard(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/blast-radius-guards``

        Attaches a registry-defined guard rule onto an
        environment. Delegates to
        :func:`orchestration.infra.guards.service.set_attachment`.

        :param request: Incoming webworks request.

        :returns: JSON response (201) carrying the freshly-created
                  :class:`BlastRadiusGuard`, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=GUARDS_WRITE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)

        environment_id = body.get("environment_id", None)
        if not isinstance(environment_id, str) or len(environment_id) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'environment_id' is required.",
                extensions={"missing_fields": ["environment_id"]},
            )

        rule_id = body.get("rule_id", None)
        if not isinstance(rule_id, str) or len(rule_id) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'rule_id' is required.",
                extensions={"missing_fields": ["rule_id"]},
            )

        enabled = body.get("enabled", True)
        if isinstance(enabled, bool) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'enabled' must be a boolean.",
            )

        actor_id = _resolve_actor_id(principal)

        try:
            view = guards_service.set_attachment(
                db_session=db_session,
                project_id=project_id,
                environment_id=environment_id,
                rule_id=rule_id,
                enabled=enabled,
                actor_id=actor_id,
            )
        except GuardEnvironmentNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"environment_id": environment_id},
            )
            view = None  # unreachable
        except GuardRuleUnknownError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"rule_id": rule_id},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.guards.create project_id=%s env=%s rule=%s",
            project_id,
            environment_id,
            rule_id,
        )

        body_dict = _attachment_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/blast-radius-guards/{guard_id}
# ---------------------------------------------------------------------------


def handle_read_guard(request: Request) -> Response:
    """
        ``GET .../blast-radius-guards/{guard_id}``

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the guard dict or a
                  problem response.
    """
    project_id = request.path_params.get("project_id", "")
    guard_id = request.path_params.get("guard_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=GUARDS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        parts = _split_guard_id(request=request, guard_id=guard_id)
        view = _find_guard_view(
            request=request,
            db_session=db_session,
            project_id=project_id,
            environment_id=parts["environment_id"],
            rule_id=parts["rule_id"],
        )

        body = _attachment_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def _find_guard_view(
        *,
        request: Request,
        db_session: Any,
        project_id: str,
        environment_id: str,
        rule_id: str
    ) -> Any:
    """
        Resolve a guard attachment view by environment + rule,
        aborting 404 on a miss.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param project_id: Project UUID.
        :param environment_id: Environment UUID.
        :param rule_id: Registry rule id.

        :returns: The matched :class:`GuardAttachmentView`.
    """
    try:
        views = guards_service.list_attachments_for_environment(
            db_session=db_session,
            project_id=project_id,
            environment_id=environment_id,
            enabled_only=False,
        )
    except GuardEnvironmentNotFoundError:
        views = []

    matched: Optional[Any] = None
    for view in views:
        if view.rule_id == rule_id:
            matched = view
            break

    if matched is None:
        _abort_problem(
            request=request,
            status=404,
            detail="Blast-radius guard not found.",
            extensions={
                "environment_id": environment_id,
                "rule_id": rule_id,
            },
        )
    rtnval = matched
    return rtnval


# ---------------------------------------------------------------------------
# PATCH /api/v1/projects/{project_id}/blast-radius-guards/{guard_id}
# ---------------------------------------------------------------------------


def handle_patch_guard(request: Request) -> Response:
    """
        ``PATCH .../blast-radius-guards/{guard_id}``

        Toggles the attachment ``enabled`` flag. Delegates to
        the guards facade ``set_attachment`` upsert.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the updated guard or a
                  problem response.
    """
    project_id = request.path_params.get("project_id", "")
    guard_id = request.path_params.get("guard_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=GUARDS_WRITE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        parts = _split_guard_id(request=request, guard_id=guard_id)
        _find_guard_view(
            request=request,
            db_session=db_session,
            project_id=project_id,
            environment_id=parts["environment_id"],
            rule_id=parts["rule_id"],
        )

        body = _decode_json_object_or_abort(request=request)
        enabled = body.get("enabled", None)
        if isinstance(enabled, bool) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'enabled' is required and must be a boolean.",
                extensions={"missing_fields": ["enabled"]},
            )

        actor_id = _resolve_actor_id(principal)

        try:
            view = guards_service.set_attachment(
                db_session=db_session,
                project_id=project_id,
                environment_id=parts["environment_id"],
                rule_id=parts["rule_id"],
                enabled=enabled,
                actor_id=actor_id,
            )
        except GuardEnvironmentNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"environment_id": parts["environment_id"]},
            )
            view = None  # unreachable
        except GuardRuleUnknownError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"rule_id": parts["rule_id"]},
            )
            view = None  # unreachable

        body_dict = _attachment_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# DELETE /api/v1/projects/{project_id}/blast-radius-guards/{guard_id}
# ---------------------------------------------------------------------------


def handle_delete_guard(request: Request) -> Response:
    """
        ``DELETE .../blast-radius-guards/{guard_id}``

        Disables the attachment. The guards facade exposes
        :func:`disable_attachment` -- there is no hard delete, so
        the attachment row survives in a disabled state.

        :param request: Incoming webworks request.

        :returns: Empty 204 response or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    guard_id = request.path_params.get("guard_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=GUARDS_WRITE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        parts = _split_guard_id(request=request, guard_id=guard_id)
        actor_id = _resolve_actor_id(principal)

        try:
            guards_service.disable_attachment(
                db_session=db_session,
                project_id=project_id,
                environment_id=parts["environment_id"],
                rule_id=parts["rule_id"],
                actor_id=actor_id,
            )
        except GuardAttachmentNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"guard_id": guard_id},
            )

        rtnval: Response = JSONResponse(content=None, status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/blast-radius-guards:evaluate
# ---------------------------------------------------------------------------


def handle_evaluate_guards(request: Request) -> Response:
    """
        ``POST .../blast-radius-guards:evaluate``

        Previews whether a proposed change would be blocked.
        Delegates to :func:`orchestration.infra.guards.service.explain`
        which walks every registered rule regardless of attachment
        state.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the evaluation trace or
                  a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=GUARDS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)

        environment_id = body.get("environment_id", None)
        if not isinstance(environment_id, str) or len(environment_id) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'environment_id' is required.",
                extensions={"missing_fields": ["environment_id"]},
            )

        action = body.get("action", None)
        if not isinstance(action, str) or len(action) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'action' is required.",
                extensions={"missing_fields": ["action"]},
            )

        requester_id = body.get("requester_id", "")
        if isinstance(requester_id, str) is False:
            requester_id = ""

        actor_role_set_raw = body.get("actor_role_set", [])
        if isinstance(actor_role_set_raw, list) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'actor_role_set' must be an array.",
            )
        actor_role_set = tuple(str(role) for role in actor_role_set_raw)

        try:
            trace = guards_service.explain(
                db_session=db_session,
                project_id=project_id,
                environment_id=environment_id,
                action=action,
                actor_role_set=actor_role_set,
                requester_id=requester_id,
            )
        except GuardEnvironmentNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"environment_id": environment_id},
            )
            trace = None  # unreachable

        body_dict = _trace_to_dict(trace=trace)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_guards_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the blast-radius-guard REST routes to a webworks
        app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + GUARDS_PATH_SUFFIX, methods=["GET"],
    )(handle_list_guards)
    app.attach_route(
        base + GUARDS_PATH_SUFFIX, methods=["POST"],
    )(handle_create_guard)
    app.attach_route(
        base + GUARDS_PATH_SUFFIX + ":evaluate", methods=["POST"],
    )(handle_evaluate_guards)
    app.attach_route(
        base + GUARDS_PATH_SUFFIX + "/{guard_id}", methods=["GET"],
    )(handle_read_guard)
    app.attach_route(
        base + GUARDS_PATH_SUFFIX + "/{guard_id}", methods=["PATCH"],
    )(handle_patch_guard)
    app.attach_route(
        base + GUARDS_PATH_SUFFIX + "/{guard_id}", methods=["DELETE"],
    )(handle_delete_guard)
    return


__all__ = [
    "GUARDS_PATH_SUFFIX",
    "GUARDS_READ_PERMISSION_KEY",
    "GUARDS_WRITE_PERMISSION_KEY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "register_guards_routes",
    "handle_list_guards",
    "handle_create_guard",
    "handle_read_guard",
    "handle_patch_guard",
    "handle_delete_guard",
    "handle_evaluate_guards",
]
