"""
.. module:: metrics.restapi.v1.dashboards_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the dashboards tag.

.. moduleauthor:: Automation Mojo LLC

Implements the project-dashboard operations from
``specs/openapi/pychestrate.yaml``:

* ``GET  /api/v1/projects/{project_id}/dashboards``
* ``POST /api/v1/projects/{project_id}/dashboards``
* ``GET  /api/v1/projects/{project_id}/dashboards/{dashboard_id}``

Each handler follows the shape of
``orchestration.build.restapi.v1.build_runs_routes`` and delegates
to the in-tree dashboards facade (``metrics.dashboards.service``).
Error responses are RFC 7807 problem documents emitted via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.metrics.dashboards import (
    service as dashboards_service,
)
from automojo.pychestrate.webservice.metrics.dashboards.errors import (
    DashboardConflictError,
    DashboardNotFoundError,
    TileConfigInvalidError,
    TileKindUnknownError,
)
from automojo.pychestrate.webservice.projects import repository as projects_repo
from automojo.pychestrate.webservice.security.rbac import rbac_evaluator


PROJECTS_PATH_PREFIX = "/projects"
DASHBOARDS_PATH_SUFFIX = "/dashboards"

DASHBOARDS_READ_PERMISSION_KEY = "system:dashboards.read"
DASHBOARDS_WRITE_PERMISSION_KEY = "system:dashboards.write"

_LOGGER = logging.getLogger("pychestrate.dashboards.routes")


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


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session.
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
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
    principal = getattr(request, "auth_principal", None)
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


def _tile_to_dict(tile: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`TileInstance` to the OpenAPI
        ``DashboardTile`` schema.

        :param tile: Tile read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "tile_id": tile.tile_id,
        "kind": tile.kind,
        "x": int(tile.x),
        "y": int(tile.y),
        "w": int(tile.w),
        "h": int(tile.h),
        "config": dict(tile.config or {}),
    }
    return rtnval


def _dashboard_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`DashboardView` to the OpenAPI
        ``Dashboard`` schema.

        :param view: Dashboard read-model.

        :returns: JSON-friendly dict.
    """
    tiles: List[Dict[str, Any]] = []
    for tile in view.tiles:
        tiles.append(_tile_to_dict(tile=tile))
    rtnval: Dict[str, Any] = {
        "dashboard_id": str(view.dashboard_id),
        "project_id": str(view.project_id),
        "name": view.name,
        "description": view.description,
        "owner_principal_id": view.owner_principal_id,
        "grid_columns_max": int(view.grid_columns_max),
        "tiles": tiles,
        "version": int(view.version),
        "created_at": _iso_or_none(view.created_at),
        "updated_at": _iso_or_none(view.updated_at),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------


def _parse_tile_instances(
        *,
        request: Request,
        raw_tiles: Any
    ) -> List[Any]:
    """
        Validate the ``tiles`` array of a create request and
        build :class:`TileInstance` objects.

        :param request: Incoming webworks request.
        :param raw_tiles: Raw ``tiles`` value from the body.

        :returns: List of TileInstance objects.
    """
    if isinstance(raw_tiles, list) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'tiles' must be an array.",
        )

    tile_instances: List[Any] = []
    for index, entry in enumerate(raw_tiles):
        if isinstance(entry, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'tiles[{}]' must be an object.".format(index),
            )
        tile_id = entry.get("tile_id", None)
        kind = entry.get("kind", None)
        if not isinstance(tile_id, str) or len(tile_id) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'tiles[{}].tile_id' is required.".format(index),
            )
        if not isinstance(kind, str) or len(kind) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'tiles[{}].kind' is required.".format(index),
            )
        config = entry.get("config", {})
        if isinstance(config, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'tiles[{}].config' must be an object.".format(
                    index,
                ),
            )
        tile_instances.append(
            dashboards_service.TileInstance(
                tile_id=tile_id,
                kind=kind,
                x=int(entry.get("x", 0)),
                y=int(entry.get("y", 0)),
                w=int(entry.get("w", 1)),
                h=int(entry.get("h", 1)),
                config=dict(config),
            )
        )
    return tile_instances


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/dashboards
# ---------------------------------------------------------------------------


def handle_list_dashboards(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/dashboards``

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items, meta}``
                  page, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=DASHBOARDS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        views = dashboards_service.list_dashboards_for_project(
            db_session=db_session,
            project_id=project_id,
        )
        items: List[Dict[str, Any]] = []
        for view in views:
            items.append(_dashboard_view_to_dict(view=view))

        body = {
            "items": items,
            "meta": {
                "page": 1,
                "per_page": len(items),
                "total": len(items),
                "next_cursor": None,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/dashboards
# ---------------------------------------------------------------------------


def handle_create_dashboard(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/dashboards``

        Creates a named dashboard with an optional set of
        metric-tile definitions. Delegates to
        :func:`metrics.dashboards.service.create_dashboard`.

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the ``Dashboard``
                  shape, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=DASHBOARDS_WRITE_PERMISSION_KEY,
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

        description = body.get("description", "")
        if isinstance(description, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'description' must be a string.",
            )

        grid_columns_max = body.get(
            "grid_columns_max",
            dashboards_service.DEFAULT_GRID_COLUMNS_MAX,
        )
        if isinstance(grid_columns_max, int) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'grid_columns_max' must be an integer.",
            )

        tile_instances = _parse_tile_instances(
            request=request,
            raw_tiles=body.get("tiles", []),
        )

        owner_principal_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            owner_principal_id = str(principal_user_id)

        try:
            view = dashboards_service.create_dashboard(
                db_session=db_session,
                project_id=project_id,
                name=name,
                description=description,
                owner_principal_id=owner_principal_id,
                grid_columns_max=grid_columns_max,
                tiles=tile_instances,
            )
        except DashboardConflictError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"name": name},
            )
            view = None  # unreachable
        except TileKindUnknownError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
            )
            view = None  # unreachable
        except TileConfigInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.dashboards.create project_id=%s dashboard_id=%s",
            project_id,
            str(view.dashboard_id),
        )

        body_dict = _dashboard_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/dashboards/{dashboard_id}
# ---------------------------------------------------------------------------


def handle_read_dashboard(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/dashboards/{dashboard_id}``

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the ``Dashboard``
                  shape, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    dashboard_id = request.path_params.get("dashboard_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=DASHBOARDS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        try:
            view = dashboards_service.get_dashboard(
                db_session=db_session,
                dashboard_id=dashboard_id,
            )
        except DashboardNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"dashboard_id": dashboard_id},
            )
            view = None  # unreachable

        if str(view.project_id) != str(project_id):
            _abort_problem(
                request=request,
                status=404,
                detail="Dashboard does not belong to this project.",
                extensions={
                    "project_id": project_id,
                    "dashboard_id": dashboard_id,
                },
            )

        body_dict = _dashboard_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_dashboards_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the dashboards REST routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + DASHBOARDS_PATH_SUFFIX, methods=["GET"],
    )(handle_list_dashboards)
    app.attach_route(
        base + DASHBOARDS_PATH_SUFFIX, methods=["POST"],
    )(handle_create_dashboard)
    app.attach_route(
        base + DASHBOARDS_PATH_SUFFIX + "/{dashboard_id}", methods=["GET"],
    )(handle_read_dashboard)
    return


__all__ = [
    "DASHBOARDS_PATH_SUFFIX",
    "DASHBOARDS_READ_PERMISSION_KEY",
    "DASHBOARDS_WRITE_PERMISSION_KEY",
    "register_dashboards_routes",
    "handle_list_dashboards",
    "handle_create_dashboard",
    "handle_read_dashboard",
]
