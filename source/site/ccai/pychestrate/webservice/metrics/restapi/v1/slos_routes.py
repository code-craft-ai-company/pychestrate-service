"""
.. module:: metrics.restapi.v1.slos_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the slos tag.

.. moduleauthor:: Code Craft AI LLC

Implements the SLO-view operations from
``specs/openapi/pychestrate.yaml``:

* ``GET    /api/v1/projects/{project_id}/slos``
* ``POST   /api/v1/projects/{project_id}/slos``
* ``GET    /api/v1/projects/{project_id}/slos/{slo_id}``
* ``DELETE /api/v1/projects/{project_id}/slos/{slo_id}``

DOMAIN NOTE -- the in-tree SLO facade
(``metrics.slos.service``) ships ``create_slo``, ``get_slo``,
``list_slos_for_project``, ``delete_slo``, and ``compute_status``.
It does NOT ship an ``update_slo`` mutator (the SLO row carries a
``version`` column reserved for an M2 edit path that has not
landed). A ``PATCH`` route is therefore intentionally NOT
registered -- there is no domain capability behind it. The
``GET .../slos/{slo_id}`` read embeds the current burn-rate /
status by calling ``compute_status``.

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
from ccai.pychestrate.webservice.metrics.slos import (
    service as slos_service,
)
from ccai.pychestrate.webservice.metrics.slos.errors import (
    SLOConfigInvalidError,
    SLOConflictError,
    SLOKindUnknownError,
    SLONotFoundError,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


SLOS_PATH_SUFFIX = "/slos"
PROJECTS_PATH_PREFIX = "/projects"

SLOS_READ_PERMISSION_KEY = "system:slos.read"
SLOS_WRITE_PERMISSION_KEY = "system:slos.write"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

_LOGGER = logging.getLogger("pychestrate.slos.routes")


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


def _slo_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize an :class:`SLOView` to the OpenAPI ``Slo``
        schema.

        :param view: Read-model returned by the SLO facade.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "slo_id": str(view.slo_id),
        "project_id": str(view.project_id),
        "name": view.name,
        "description": view.description,
        "kind": view.kind,
        "target": float(view.target),
        "window_seconds": int(view.window_seconds),
        "definition_config": dict(view.definition_config or {}),
        "default_notification_route_key": view.default_notification_route_key,
        "auto_attach_burn_rate_alerts": bool(
            view.auto_attach_burn_rate_alerts,
        ),
        "version": int(view.version),
        "created_at": _iso_or_none(view.created_at),
        "updated_at": _iso_or_none(view.updated_at),
    }
    return rtnval


def _slo_status_to_dict(status: Any) -> Dict[str, Any]:
    """
        Serialize an :class:`SLOStatus` to the OpenAPI
        ``SloStatus`` schema.

        :param status: Status read-model from ``compute_status``.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "slo_id": str(status.slo_id),
        "achieved_ratio": status.achieved_ratio,
        "error_budget_remaining_ratio": status.error_budget_remaining_ratio,
        "target": float(status.target),
        "window_start": _iso_or_none(status.window_start),
        "window_end": _iso_or_none(status.window_end),
        "good_count": int(status.good_count),
        "total_count": int(status.total_count),
        "breaching": bool(status.breaching),
        "reason": status.reason,
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/slos
# ---------------------------------------------------------------------------


def handle_list_slos(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/slos``

        Query params: ``kind``, ``page``, ``per_page``.

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
            permission_key=SLOS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        kind_filter = request.query_params.get("kind", None)
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

        all_views = slos_service.list_slos_for_project(
            db_session=db_session,
            project_id=project_id,
        )
        if kind_filter is not None and len(kind_filter) > 0:
            filtered: List[Any] = []
            for view in all_views:
                if view.kind == kind_filter:
                    filtered.append(view)
            all_views = filtered

        total = len(all_views)
        offset = (page - 1) * per_page
        window = all_views[offset:offset + per_page]

        items: List[Dict[str, Any]] = []
        for view in window:
            items.append(_slo_view_to_dict(view=view))

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
# POST /api/v1/projects/{project_id}/slos
# ---------------------------------------------------------------------------


def handle_create_slo(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/slos``

        Declares an SLO definition. Delegates to
        :func:`metrics.slos.service.create_slo`.

        :param request: Incoming webworks request.

        :returns: JSON response (201) carrying the freshly-created
                  :class:`Slo`, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=SLOS_WRITE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)

        name = body.get("name", None)
        if not isinstance(name, str) or len(name) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'name' is required.",
                extensions={"missing_fields": ["name"]},
            )

        kind = body.get("kind", None)
        if not isinstance(kind, str) or len(kind) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'kind' is required.",
                extensions={"missing_fields": ["kind"]},
            )

        target = body.get("target", None)
        if isinstance(target, bool) or not isinstance(target, (int, float)):
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'target' is required and must be a number.",
                extensions={"missing_fields": ["target"]},
            )

        window_seconds = body.get(
            "window_seconds", slos_service.DEFAULT_WINDOW_SECONDS,
        )
        if isinstance(window_seconds, bool) or not isinstance(
            window_seconds, int
        ):
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'window_seconds' must be an integer.",
            )

        description = body.get("description", "")
        if isinstance(description, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'description' must be a string.",
            )

        definition_config = body.get("definition_config", {})
        if isinstance(definition_config, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'definition_config' must be an object.",
            )

        route_key = body.get("default_notification_route_key", None)
        if route_key is not None and isinstance(route_key, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail=(
                    "Field 'default_notification_route_key' must be a "
                    "string."
                ),
            )

        auto_attach = body.get("auto_attach_burn_rate_alerts", False)
        if isinstance(auto_attach, bool) is False:
            _abort_problem(
                request=request,
                status=422,
                detail=(
                    "Field 'auto_attach_burn_rate_alerts' must be a "
                    "boolean."
                ),
            )

        try:
            view = slos_service.create_slo(
                db_session=db_session,
                project_id=project_id,
                name=name,
                kind=kind,
                target=float(target),
                window_seconds=int(window_seconds),
                description=description,
                definition_config=dict(definition_config),
                default_notification_route_key=route_key,
                auto_attach_burn_rate_alerts=auto_attach,
            )
        except SLOConflictError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"name": name},
            )
            view = None  # unreachable
        except SLOKindUnknownError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"kind": kind},
            )
            view = None  # unreachable
        except SLOConfigInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"kind": kind},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.slos.create project_id=%s kind=%s slo_id=%s",
            project_id,
            kind,
            str(view.slo_id),
        )

        body_dict = _slo_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/slos/{slo_id}
# ---------------------------------------------------------------------------


def handle_read_slo(request: Request) -> Response:
    """
        ``GET .../slos/{slo_id}``

        Returns the SLO definition with an embedded ``status``
        block carrying the current burn-rate / achieved ratio.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the SLO dict or a
                  problem response.
    """
    project_id = request.path_params.get("project_id", "")
    slo_id = request.path_params.get("slo_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=SLOS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        try:
            view = slos_service.get_slo(
                db_session=db_session,
                slo_id=slo_id,
            )
        except SLONotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"slo_id": slo_id},
            )
            view = None  # unreachable

        if str(view.project_id) != str(project_id):
            _abort_problem(
                request=request,
                status=404,
                detail="SLO does not belong to this project.",
                extensions={"project_id": project_id, "slo_id": slo_id},
            )

        body = _slo_view_to_dict(view=view)

        try:
            status = slos_service.compute_status(
                db_session=db_session,
                slo_id=slo_id,
            )
            body["status"] = _slo_status_to_dict(status=status)
        except SLOKindUnknownError:
            body["status"] = None

        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# DELETE /api/v1/projects/{project_id}/slos/{slo_id}
# ---------------------------------------------------------------------------


def handle_delete_slo(request: Request) -> Response:
    """
        ``DELETE .../slos/{slo_id}``

        Idempotent delete -- the burn-rate-state row cascades via
        the FK. Returns 404 when the SLO does not exist or belongs
        to another project.

        :param request: Incoming webworks request.

        :returns: Empty 204 response or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    slo_id = request.path_params.get("slo_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=SLOS_WRITE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        try:
            view = slos_service.get_slo(
                db_session=db_session,
                slo_id=slo_id,
            )
        except SLONotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"slo_id": slo_id},
            )
            view = None  # unreachable

        if str(view.project_id) != str(project_id):
            _abort_problem(
                request=request,
                status=404,
                detail="SLO does not belong to this project.",
                extensions={"project_id": project_id, "slo_id": slo_id},
            )

        slos_service.delete_slo(
            db_session=db_session,
            slo_id=slo_id,
        )

        rtnval: Response = JSONResponse(content=None, status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_slos_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the SLO-view REST routes to a webworks app.

        DOMAIN NOTE -- no ``PATCH`` route is registered: the SLO
        facade ships no ``update_slo`` mutator.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + SLOS_PATH_SUFFIX, methods=["GET"],
    )(handle_list_slos)
    app.attach_route(
        base + SLOS_PATH_SUFFIX, methods=["POST"],
    )(handle_create_slo)
    app.attach_route(
        base + SLOS_PATH_SUFFIX + "/{slo_id}", methods=["GET"],
    )(handle_read_slo)
    app.attach_route(
        base + SLOS_PATH_SUFFIX + "/{slo_id}", methods=["DELETE"],
    )(handle_delete_slo)
    return


__all__ = [
    "SLOS_PATH_SUFFIX",
    "SLOS_READ_PERMISSION_KEY",
    "SLOS_WRITE_PERMISSION_KEY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "register_slos_routes",
    "handle_list_slos",
    "handle_create_slo",
    "handle_read_slo",
    "handle_delete_slo",
]
