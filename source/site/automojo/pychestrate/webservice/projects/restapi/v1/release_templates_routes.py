"""
.. module:: projects.restapi.v1.release_templates_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for
               ``/api/v1/projects/{project_id}/release-templates``.

.. moduleauthor:: Automation Mojo LLC

REST CRUD for project-scoped release templates.

Five routes cover the surface:

* ``GET    /api/v1/projects/{project_id}/release-templates``
* ``POST   /api/v1/projects/{project_id}/release-templates``
* ``GET    /api/v1/projects/{project_id}/release-templates/{template_id}``
* ``PATCH  /api/v1/projects/{project_id}/release-templates/{template_id}``
* ``DELETE /api/v1/projects/{project_id}/release-templates/{template_id}``

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.

Note: the original plan called for slug-based URLs
(``/projects/{slug}/release-templates``). The codebase has two
distinct ``Project`` models -- a legacy ``Project`` (BigInt
``proj_id``) under :mod:`automojo.pychestrate.core.orm` used by
every project-scoped feature manager (releases, pipelines,
repositories, etc.), and a newer ``Project`` (UUID ``project_id``,
slug) under :mod:`automojo.pychestrate.webservice.projects.models`
used by the lifecycle REST surface. Because there is no bridge
between the two, release templates must FK onto exactly one --
the legacy ``Project`` was chosen since it matches every
sibling project-scoped manager. As a result the REST URL keys
on the legacy int ``project_id`` rather than the new project
slug.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.security.rbac import rbac_evaluator


PROJECTS_PATH = "/projects"
RELEASE_TEMPLATES_PATH = "/release-templates"

RELEASE_TEMPLATES_READ_PERMISSION_KEY = "system:release_templates.read"
RELEASE_TEMPLATES_WRITE_PERMISSION_KEY = "system:release_templates.write"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition
        once and the handler can convert it to a return at the
        boundary.
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
        extensions: Optional[dict] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Human-readable detail string.
        :param extensions: Optional problem-document extensions.
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
        Pull the request-scoped SQLAlchemy session off the request.

        :param request: Incoming webworks request.

        :returns: Session or ``None`` when absent.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_actor_user_id(request: Request) -> Optional[str]:
    """
        Pull the resolved actor-user id off the request.

        :param request: Incoming webworks request.

        :returns: User id string or ``None``.
    """
    rtnval = getattr(request, "actor_user_id", None)
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


def _decode_json_or_abort(*, request: Request) -> dict:
    """
        Decode the request body as JSON, aborting 400 on missing /
        non-dict.

        :param request: Incoming webworks request.

        :returns: Decoded JSON dict.
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


def _parse_positive_int_query(
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


def _parse_path_int(
        *,
        request: Request,
        name: str
    ) -> int:
    """
        Coerce a path parameter to a positive integer.

        :param request: Incoming webworks request.
        :param name: Path-parameter name.

        :returns: Coerced integer.
    """
    raw = request.path_params.get(name, None)
    if raw is None or len(str(raw)) == 0:
        _abort_problem(
            request=request,
            status=400,
            detail="Path param '{}' is required.".format(name),
        )
    try:
        rtnval = int(raw)
    except (TypeError, ValueError):
        _abort_problem(
            request=request,
            status=400,
            detail="Path param '{}' must be an integer.".format(name),
        )
        rtnval = 0  # unreachable

    return rtnval


def _build_template_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ReleaseTemplateManager`. Lazy-imports.

        :param db_session: Open SQLAlchemy session.

        :returns: ReleaseTemplateManager instance.
    """
    from automojo.pychestrate.core.managers.release_template_manager import (  # noqa: E402
        ReleaseTemplateManager,
    )
    rtnval = ReleaseTemplateManager(db_session=db_session)
    return rtnval


def _template_to_dict(template: Any) -> dict:
    """
        Render a :class:`ReleaseTemplateResponse` as a dict.

        :param template: ``ReleaseTemplateResponse`` dataclass.

        :returns: JSON-friendly dict.
    """
    created_at_iso = None
    if template.created_at is not None:
        created_at_iso = template.created_at.isoformat()

    updated_at_iso = None
    if template.updated_at is not None:
        updated_at_iso = template.updated_at.isoformat()

    rtnval = {
        "template_id": template.id,
        "project_id": template.project_id,
        "name": template.name,
        "description": template.description,
        "default_channel": template.default_channel,
        "version_pattern": template.version_pattern,
        "default_repo_ids": list(template.default_repo_ids),
        "default_pipeline": template.default_pipeline,
        "default_schedule": template.default_schedule,
        "created_at": created_at_iso,
        "updated_at": updated_at_iso,
    }
    return rtnval


def _coerce_optional_str(value: Any) -> Optional[str]:
    """
        Coerce a JSON-decoded value to ``Optional[str]``.

        :param value: Raw JSON value.

        :returns: ``None`` if value is ``None``; otherwise ``str(value)``.
    """
    if value is None:
        return None
    rtnval = str(value)
    return rtnval


def _coerce_optional_dict(
        *, request: Request, name: str, value: Any
    ) -> Optional[Dict[str, Any]]:
    """
        Validate that ``value`` is ``None`` or a JSON object.

        :param request: Incoming webworks request.
        :param name: Field name (for error context).
        :param value: Raw JSON value.

        :returns: The dict or ``None``.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        _abort_problem(
            request=request,
            status=400,
            detail="Field '{}' must be a JSON object or null.".format(name),
            extensions={"field": name},
        )
    rtnval = value
    return rtnval


def _coerce_optional_int_list(
        *, request: Request, name: str, value: Any
    ) -> Optional[List[int]]:
    """
        Validate that ``value`` is ``None`` or a list of integers.

        :param request: Incoming webworks request.
        :param name: Field name (for error context).
        :param value: Raw JSON value.

        :returns: The list of integers or ``None``.
    """
    if value is None:
        return None
    if not isinstance(value, list):
        _abort_problem(
            request=request,
            status=400,
            detail="Field '{}' must be a JSON array of integers.".format(name),
            extensions={"field": name},
        )

    coerced: List[int] = []
    for index, candidate in enumerate(value):
        if not isinstance(candidate, int):
            _abort_problem(
                request=request,
                status=400,
                detail="Field '{}[{}]' must be an integer.".format(name, index),
                extensions={"field": name, "index": index},
            )
        coerced.append(int(candidate))

    rtnval = coerced
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_list_release_templates(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/release-templates``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a ``{items, meta}`` page.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RELEASE_TEMPLATES_READ_PERMISSION_KEY,
        )

        project_id = _parse_path_int(request=request, name="project_id")
        page = _parse_positive_int_query(
            request=request,
            name="page",
            raw=request.query_params.get("page", None),
            default=1,
            minimum=1,
        )
        per_page = _parse_positive_int_query(
            request=request,
            name="per_page",
            raw=request.query_params.get("per_page", None),
            default=DEFAULT_PAGE_SIZE,
            minimum=MIN_PAGE_SIZE,
            maximum=MAX_PAGE_SIZE,
        )

        offset = (page - 1) * per_page
        manager = _build_template_manager(db_session=db_session)
        result = manager.list_for_project(
            project_id, offset=offset, limit=per_page
        )

        items: List[Dict[str, Any]] = []
        for entry in result.templates:
            items.append(_template_to_dict(entry))

        body = {
            "items": items,
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": int(result.total),
                "next_cursor": None,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_create_release_template(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/release-templates``.

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the new template dict.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RELEASE_TEMPLATES_WRITE_PERMISSION_KEY,
        )

        project_id = _parse_path_int(request=request, name="project_id")
        actor_user_id = _resolve_actor_user_id(request=request)
        payload = _decode_json_or_abort(request=request)

        name_value = _coerce_optional_str(payload.get("name", None))
        if name_value is None:
            _abort_problem(
                request=request,
                status=400,
                detail="Field 'name' is required.",
                extensions={"field": "name"},
            )

        description_value = payload.get("description", "")
        if description_value is None:
            description_value = ""
        if not isinstance(description_value, str):
            description_value = str(description_value)

        default_channel = _coerce_optional_str(
            payload.get("default_channel", None)
        )
        version_pattern = _coerce_optional_str(
            payload.get("version_pattern", None)
        )
        default_repo_ids = _coerce_optional_int_list(
            request=request,
            name="default_repo_ids",
            value=payload.get("default_repo_ids", None),
        )
        default_pipeline = _coerce_optional_dict(
            request=request,
            name="default_pipeline",
            value=payload.get("default_pipeline", None),
        )
        default_schedule = _coerce_optional_dict(
            request=request,
            name="default_schedule",
            value=payload.get("default_schedule", None),
        )

        manager = _build_template_manager(db_session=db_session)

        from automojo.pychestrate.core.managers.release_template_manager import (  # noqa: E402
            DuplicateReleaseTemplateError,
            ReleaseTemplateProjectNotFoundError,
            ReleaseTemplateValidationError,
        )

        try:
            template = manager.create(
                project_id,
                name=name_value,
                description=description_value,
                default_channel=default_channel,
                version_pattern=version_pattern,
                default_repo_ids=default_repo_ids,
                default_pipeline=default_pipeline,
                default_schedule=default_schedule,
                created_by=actor_user_id,
            )
        except ReleaseTemplateProjectNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"project_id": project_id},
            )
        except ReleaseTemplateValidationError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"field": xcpt.field},
            )
        except DuplicateReleaseTemplateError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"name": name_value},
            )

        body = _template_to_dict(template)
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_release_template(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/release-templates/{template_id}``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the template dict.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RELEASE_TEMPLATES_READ_PERMISSION_KEY,
        )

        project_id = _parse_path_int(request=request, name="project_id")
        template_id = _parse_path_int(request=request, name="template_id")

        manager = _build_template_manager(db_session=db_session)
        template = manager.get(template_id)
        if template is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Release template not found.",
                extensions={"template_id": template_id},
            )
        if template.project_id != project_id:
            _abort_problem(
                request=request,
                status=404,
                detail="Release template not found.",
                extensions={
                    "template_id": template_id,
                    "project_id": project_id,
                },
            )

        body = _template_to_dict(template)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_patch_release_template(request: Request) -> Response:
    """
        ``PATCH /api/v1/projects/{project_id}/release-templates/{template_id}``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the updated template dict.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RELEASE_TEMPLATES_WRITE_PERMISSION_KEY,
        )

        project_id = _parse_path_int(request=request, name="project_id")
        template_id = _parse_path_int(request=request, name="template_id")
        actor_user_id = _resolve_actor_user_id(request=request)
        payload = _decode_json_or_abort(request=request)

        manager = _build_template_manager(db_session=db_session)
        existing = manager.get(template_id)
        if existing is None or existing.project_id != project_id:
            _abort_problem(
                request=request,
                status=404,
                detail="Release template not found.",
                extensions={
                    "template_id": template_id,
                    "project_id": project_id,
                },
            )

        name_value = _coerce_optional_str(payload.get("name", None))
        description_value: Optional[str] = None
        if "description" in payload:
            raw_description = payload.get("description")
            if raw_description is None:
                description_value = ""
            elif isinstance(raw_description, str):
                description_value = raw_description
            else:
                description_value = str(raw_description)

        default_channel: Optional[str] = None
        if "default_channel" in payload:
            default_channel = _coerce_optional_str(
                payload.get("default_channel", None)
            )
            if default_channel is None:
                default_channel = ""

        version_pattern: Optional[str] = None
        if "version_pattern" in payload:
            version_pattern = _coerce_optional_str(
                payload.get("version_pattern", None)
            )
            if version_pattern is None:
                version_pattern = ""

        default_repo_ids: Optional[List[int]] = None
        if "default_repo_ids" in payload:
            default_repo_ids = _coerce_optional_int_list(
                request=request,
                name="default_repo_ids",
                value=payload.get("default_repo_ids", None),
            )
            if default_repo_ids is None:
                default_repo_ids = []

        default_pipeline: Optional[Dict[str, Any]] = None
        if "default_pipeline" in payload:
            default_pipeline = _coerce_optional_dict(
                request=request,
                name="default_pipeline",
                value=payload.get("default_pipeline", None),
            )
            if default_pipeline is None:
                default_pipeline = {}

        default_schedule: Optional[Dict[str, Any]] = None
        if "default_schedule" in payload:
            default_schedule = _coerce_optional_dict(
                request=request,
                name="default_schedule",
                value=payload.get("default_schedule", None),
            )
            if default_schedule is None:
                default_schedule = {}

        from automojo.pychestrate.core.managers.release_template_manager import (  # noqa: E402
            DuplicateReleaseTemplateError,
            ReleaseTemplateNotFoundError,
            ReleaseTemplateValidationError,
        )

        try:
            updated = manager.update(
                template_id,
                name=name_value,
                description=description_value,
                default_channel=default_channel,
                version_pattern=version_pattern,
                default_repo_ids=default_repo_ids,
                default_pipeline=default_pipeline,
                default_schedule=default_schedule,
                updated_by=actor_user_id,
            )
        except ReleaseTemplateNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"template_id": template_id},
            )
        except ReleaseTemplateValidationError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"field": xcpt.field},
            )
        except DuplicateReleaseTemplateError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"name": name_value},
            )

        body = _template_to_dict(updated)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_delete_release_template(request: Request) -> Response:
    """
        ``DELETE /api/v1/projects/{project_id}/release-templates/{template_id}``.

        :param request: Incoming webworks request.

        :returns: 204 (empty body) on success, problem response on
                  failure.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RELEASE_TEMPLATES_WRITE_PERMISSION_KEY,
        )

        project_id = _parse_path_int(request=request, name="project_id")
        template_id = _parse_path_int(request=request, name="template_id")
        actor_user_id = _resolve_actor_user_id(request=request)

        manager = _build_template_manager(db_session=db_session)
        existing = manager.get(template_id)
        if existing is None or existing.project_id != project_id:
            _abort_problem(
                request=request,
                status=404,
                detail="Release template not found.",
                extensions={
                    "template_id": template_id,
                    "project_id": project_id,
                },
            )

        from automojo.pychestrate.core.managers.release_template_manager import (  # noqa: E402
            ReleaseTemplateNotFoundError,
        )

        try:
            manager.delete(template_id, deleted_by=actor_user_id)
        except ReleaseTemplateNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"template_id": template_id},
            )

        rtnval: Response = Response(status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_release_templates_routes(
        *, app: Any, version_prefix: str
    ) -> None:
    """
        Attach the release-template routes to a webworks application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix, e.g. ``/api/v1``.

        :returns: None.
    """
    base = (
        version_prefix
        + PROJECTS_PATH
        + "/{project_id}"
        + RELEASE_TEMPLATES_PATH
    )
    detail = base + "/{template_id}"

    app.attach_route(base, methods=["GET"])(
        handle_list_release_templates
    )
    app.attach_route(base, methods=["POST"])(
        handle_create_release_template
    )

    app.attach_route(detail, methods=["GET"])(
        handle_read_release_template
    )
    app.attach_route(detail, methods=["PATCH"])(
        handle_patch_release_template
    )
    app.attach_route(detail, methods=["DELETE"])(
        handle_delete_release_template
    )
    return


__all__ = [
    "PROJECTS_PATH",
    "RELEASE_TEMPLATES_PATH",
    "RELEASE_TEMPLATES_READ_PERMISSION_KEY",
    "RELEASE_TEMPLATES_WRITE_PERMISSION_KEY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "register_release_templates_routes",
    "handle_list_release_templates",
    "handle_create_release_template",
    "handle_read_release_template",
    "handle_patch_release_template",
    "handle_delete_release_template",
]
