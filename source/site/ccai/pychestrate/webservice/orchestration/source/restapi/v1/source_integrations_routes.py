"""
.. module:: orchestration.source.restapi.v1.source_integrations_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the source_integrations tag.

.. moduleauthor:: Code Craft AI LLC

Implements the source-integrations operations from
``specs/openapi/pychestrate.yaml``:

* ``GET  /api/v1/projects/{project_id}/source-integrations``
* ``POST /api/v1/projects/{project_id}/source-integrations``
* ``GET  /api/v1/projects/{project_id}/source-integrations/{integration_id}``

Each handler follows the shape of
``webservice.orchestration.test.restapi.v1.test_catalog_routes``:
cookie-or-api-key session validation, RBAC permission check, JSON
body decode, then delegation to the in-tree source-integrations
facade (``orchestration.source.service``).

The source domain models one SCM project config per project --
the composite key is the ``project_id`` itself. To present a
RESTful collection the ``integration_id`` path parameter is the
``project_id`` (a project owns at most one source integration in
the M1 scaffolding); list returns a single-element collection
when a config is registered.

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
from ccai.pychestrate.webservice.orchestration.source import (
    service as source_service,
)
from ccai.pychestrate.webservice.orchestration.source.errors import (
    ScmConfigNotFoundError,
    ScmProviderNotFoundError,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


SOURCE_INTEGRATIONS_PATH_SUFFIX = "/source-integrations"
PROJECTS_PATH_PREFIX = "/projects"

SOURCE_INTEGRATIONS_READ_PERMISSION_KEY = "system:source_integrations.read"
SOURCE_INTEGRATIONS_WRITE_PERMISSION_KEY = "system:source_integrations.write"

_LOGGER = logging.getLogger("pychestrate.source_integrations.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition
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
    ) -> None:
    """
        Require the calling principal to hold ``permission_key``.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param permission_key: Required ``system:*`` permission key.

        :returns: None.
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
    return


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


def _config_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`ScmProjectConfigView` to the OpenAPI
        ``SourceIntegration`` schema.

        :param view: SCM project-config read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "integration_id": str(view.project_id),
        "project_id": str(view.project_id),
        "provider_name": view.provider_name,
        "repo_key": view.repo_key,
        "pipeline_file_path": view.pipeline_file_path,
        "use_polling": bool(view.use_polling),
        "polling_ref_glob": view.polling_ref_glob,
        "last_poll_at": _iso_or_none(view.last_poll_at),
        "created_at": _iso_or_none(view.created_at),
        "updated_at": _iso_or_none(view.updated_at),
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/source-integrations
# ---------------------------------------------------------------------------


def handle_list_source_integrations(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/source-integrations``

        Returns a ``{items, meta}`` page. The collection holds at
        most one element -- a project owns a single SCM config in
        the M1 scaffolding.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the page, or a problem
                  response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=SOURCE_INTEGRATIONS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        items: List[Dict[str, Any]] = []
        try:
            view = source_service.get_project_config(
                db_session=db_session,
                project_id=project_id,
            )
            items.append(_config_view_to_dict(view=view))
        except ScmConfigNotFoundError:
            items = []

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
# POST /api/v1/projects/{project_id}/source-integrations
# ---------------------------------------------------------------------------


def handle_register_source_integration(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/source-integrations``

        Registers (or updates) the per-project SCM config.
        Delegates to
        :func:`orchestration.source.service.set_project_config`.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the registered
                  :class:`SourceIntegration`, or a problem
                  response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=SOURCE_INTEGRATIONS_WRITE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)

        provider_name = body.get("provider_name", None)
        repo_key = body.get("repo_key", None)

        missing_fields: List[str] = []
        if not isinstance(provider_name, str) or len(provider_name) == 0:
            missing_fields.append("provider_name")
        if not isinstance(repo_key, str) or len(repo_key) == 0:
            missing_fields.append("repo_key")
        if len(missing_fields) > 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Missing required field(s): {}".format(
                    ", ".join(missing_fields),
                ),
                extensions={"missing_fields": missing_fields},
            )

        pipeline_file_path = body.get(
            "pipeline_file_path",
            source_service.DEFAULT_PIPELINE_FILE_PATH,
        )
        if not isinstance(pipeline_file_path, str) or len(pipeline_file_path) == 0:
            pipeline_file_path = source_service.DEFAULT_PIPELINE_FILE_PATH

        use_polling = body.get("use_polling", False)
        if isinstance(use_polling, bool) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'use_polling' must be a boolean.",
            )

        polling_ref_glob = body.get("polling_ref_glob", "")
        if isinstance(polling_ref_glob, str) is False:
            polling_ref_glob = ""

        try:
            view = source_service.set_project_config(
                db_session=db_session,
                project_id=project_id,
                provider_name=provider_name,
                repo_key=repo_key,
                pipeline_file_path=pipeline_file_path,
                use_polling=use_polling,
                polling_ref_glob=polling_ref_glob,
            )
        except ScmProviderNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"provider_name": provider_name},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.source_integrations.register project_id=%s provider=%s repo=%s",
            project_id,
            provider_name,
            repo_key,
        )

        body_dict = _config_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/source-integrations/{integration_id}
# ---------------------------------------------------------------------------


def handle_read_source_integration(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/source-integrations/{integration_id}``

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the source integration,
                  or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    integration_id = request.path_params.get("integration_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=SOURCE_INTEGRATIONS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        if integration_id != project_id:
            _abort_problem(
                request=request,
                status=404,
                detail="Source integration not found.",
                extensions={
                    "project_id": project_id,
                    "integration_id": integration_id,
                },
            )

        try:
            view = source_service.get_project_config(
                db_session=db_session,
                project_id=project_id,
            )
        except ScmConfigNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"integration_id": integration_id},
            )
            view = None  # unreachable

        body = _config_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_source_integrations_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the source-integrations REST routes to a webworks
        app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + SOURCE_INTEGRATIONS_PATH_SUFFIX, methods=["GET"],
    )(handle_list_source_integrations)
    app.attach_route(
        base + SOURCE_INTEGRATIONS_PATH_SUFFIX, methods=["POST"],
    )(handle_register_source_integration)
    app.attach_route(
        base + SOURCE_INTEGRATIONS_PATH_SUFFIX + "/{integration_id}",
        methods=["GET"],
    )(handle_read_source_integration)
    return


__all__ = [
    "SOURCE_INTEGRATIONS_PATH_SUFFIX",
    "SOURCE_INTEGRATIONS_READ_PERMISSION_KEY",
    "SOURCE_INTEGRATIONS_WRITE_PERMISSION_KEY",
    "register_source_integrations_routes",
    "handle_list_source_integrations",
    "handle_register_source_integration",
    "handle_read_source_integration",
]
