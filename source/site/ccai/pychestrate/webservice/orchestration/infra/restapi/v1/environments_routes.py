"""
.. module:: orchestration.infra.restapi.v1.environments_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the environments tag.

.. moduleauthor:: Code Craft AI LLC

Implements the environment-registry operations from
``specs/openapi/pychestrate.yaml``:

* ``GET  /api/v1/projects/{project_id}/environments``
* ``POST /api/v1/projects/{project_id}/environments``
* ``GET  /api/v1/projects/{project_id}/environments/{environment_id}``

Each handler follows the shape of
``webservice.orchestration.build.restapi.v1.build_runs_routes``:
cookie-or-api-key session validation, RBAC permission check, JSON
body decode, then delegation to the in-tree environment-registry
facade (``orchestration.infra.environment.service``).

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
from ccai.pychestrate.webservice.orchestration.infra.environment import (
    service as environment_service,
)
from ccai.pychestrate.webservice.orchestration.infra.environment.errors import (
    EnvironmentAttrsInvalidError,
    EnvironmentKindUnknownError,
    EnvironmentNameConflictError,
    EnvironmentNotFoundError,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


ENVIRONMENTS_PATH_SUFFIX = "/environments"
PROJECTS_PATH_PREFIX = "/projects"

ENVIRONMENTS_READ_PERMISSION_KEY = "system:environments.read"
ENVIRONMENTS_WRITE_PERMISSION_KEY = "system:environments.write"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

_LOGGER = logging.getLogger("pychestrate.environments.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks
        problem response so nested helpers can signal an error
        once and the top-level handler can convert it to a return
        value at the boundary.
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


def _enum_value_or_str(value: Any) -> str:
    """
        Return the ``.value`` of a string-enum or its ``str``.

        :param value: Enum instance or scalar.

        :returns: String value.
    """
    extracted = getattr(value, "value", None)
    if extracted is not None:
        rtnval = str(extracted)
        return rtnval
    rtnval = str(value)
    return rtnval


def _environment_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize an :class:`EnvironmentView` to the OpenAPI
        ``Environment`` schema.

        :param view: Read-model returned by the environment facade.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "environment_id": str(view.environment_id),
        "project_id": str(view.project_id),
        "kind_name": view.kind_name,
        "name": view.name,
        "state": _enum_value_or_str(view.state),
        "attrs": dict(view.attrs or {}),
        "frozen_by": view.frozen_by,
        "frozen_reason": view.frozen_reason,
        "frozen_at": _iso_or_none(view.frozen_at),
        "last_applied_run_id": view.last_applied_run_id,
        "last_output_digest_sha256": view.last_output_digest_sha256,
        "last_applied_at": _iso_or_none(view.last_applied_at),
        "archived_reason": view.archived_reason,
        "archived_at": _iso_or_none(view.archived_at),
        "destroyed_at": _iso_or_none(view.destroyed_at),
        "created_at": _iso_or_none(view.created_at),
        "updated_at": _iso_or_none(view.updated_at),
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/environments
# ---------------------------------------------------------------------------


def handle_list_environments(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/environments``

        Query params: ``kind``, ``state``, ``page``, ``per_page``.

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
            permission_key=ENVIRONMENTS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        kind_filter = request.query_params.get("kind", None)
        state_filter = request.query_params.get("state", None)
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

        all_views = environment_service.list_environments(
            db_session=db_session,
            project_id=project_id,
            limit=MAX_PAGE_SIZE,
        )
        if kind_filter is not None and len(kind_filter) > 0:
            filtered: List[Any] = []
            for view in all_views:
                if view.kind_name == kind_filter:
                    filtered.append(view)
            all_views = filtered
        if state_filter is not None and len(state_filter) > 0:
            filtered_state: List[Any] = []
            for view in all_views:
                if _enum_value_or_str(view.state) == state_filter:
                    filtered_state.append(view)
            all_views = filtered_state

        total = len(all_views)
        offset = (page - 1) * per_page
        window = all_views[offset:offset + per_page]

        items: List[Dict[str, Any]] = []
        for view in window:
            items.append(_environment_view_to_dict(view=view))

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
# POST /api/v1/projects/{project_id}/environments
# ---------------------------------------------------------------------------


def handle_register_environment(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/environments``

        Declares a named environment under a registered
        environment kind. Delegates to
        :func:`orchestration.infra.environment.service.declare_environment`.

        :param request: Incoming webworks request.

        :returns: JSON response (201) carrying the freshly-declared
                  :class:`Environment`, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=ENVIRONMENTS_WRITE_PERMISSION_KEY,
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

        kind_name = body.get("kind_name", None)
        if not isinstance(kind_name, str) or len(kind_name) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'kind_name' is required.",
                extensions={"missing_fields": ["kind_name"]},
            )

        attrs = body.get("attrs", {})
        if isinstance(attrs, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'attrs' must be an object.",
            )

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        inputs = environment_service.EnvironmentDeclareInputs(
            name=name,
            kind_name=kind_name,
            attrs=dict(attrs),
        )

        try:
            view = environment_service.declare_environment(
                db_session=db_session,
                project_id=project_id,
                inputs=inputs,
                actor_id=actor_id,
            )
        except EnvironmentKindUnknownError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"kind_name": kind_name},
            )
            view = None  # unreachable
        except EnvironmentAttrsInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"kind_name": kind_name},
            )
            view = None  # unreachable
        except EnvironmentNameConflictError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"kind_name": kind_name, "name": name},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.environments.register project_id=%s kind=%s env_id=%s",
            project_id,
            kind_name,
            str(view.environment_id),
        )

        body_dict = _environment_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/environments/{environment_id}
# ---------------------------------------------------------------------------


def handle_read_environment(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/environments/{environment_id}``

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the environment dict or
                  a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    environment_id = request.path_params.get("environment_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=ENVIRONMENTS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        try:
            view = environment_service.get_environment(
                db_session=db_session,
                environment_id=environment_id,
            )
        except EnvironmentNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"environment_id": environment_id},
            )
            view = None  # unreachable

        if str(view.project_id) != str(project_id):
            _abort_problem(
                request=request,
                status=404,
                detail="Environment does not belong to this project.",
                extensions={
                    "project_id": project_id,
                    "environment_id": environment_id,
                },
            )

        body = _environment_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_environments_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the environment-registry REST routes to a webworks
        app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + ENVIRONMENTS_PATH_SUFFIX, methods=["GET"],
    )(handle_list_environments)
    app.attach_route(
        base + ENVIRONMENTS_PATH_SUFFIX, methods=["POST"],
    )(handle_register_environment)
    app.attach_route(
        base + ENVIRONMENTS_PATH_SUFFIX + "/{environment_id}", methods=["GET"],
    )(handle_read_environment)
    return


__all__ = [
    "ENVIRONMENTS_PATH_SUFFIX",
    "ENVIRONMENTS_READ_PERMISSION_KEY",
    "ENVIRONMENTS_WRITE_PERMISSION_KEY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "register_environments_routes",
    "handle_list_environments",
    "handle_register_environment",
    "handle_read_environment",
]
