"""
.. module:: projects.restapi.v1.projects_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/projects.

.. moduleauthor:: Automation Mojo LLC

The production webservice runs on ``automojo.webworks`` (see
:mod:`app_pychestrate_main`). This is the **last** flask_restx
controller to be ported -- it replaces ``projects_controller``
next to it.

Ten routes mirror the flask_restx controller's M1 + M2 matrix:

* ``POST   /api/v1/projects``
* ``GET    /api/v1/projects/{slug}``
* ``PATCH  /api/v1/projects/{slug}``
* ``DELETE /api/v1/projects/{slug}``
* ``POST   /api/v1/projects/{slug}/archive``
* ``POST   /api/v1/projects/{slug}/unarchive``
* ``GET    /api/v1/projects/{slug}/members``
* ``POST   /api/v1/projects/{slug}/members``
* ``DELETE /api/v1/projects/{slug}/members/{user_id}``
  (last-admin safeguard; remove the
  :data:`PROJECT_OWNER_ROLE` binding for the user)
* ``DELETE /api/v1/projects/{slug}/members/{user_id}/{role_name}``
  (remove a specific ``(user_id, role_name)`` binding)

The pods port (#134) registers routes under
``/api/v1/projects/{project_id}/...`` -- those use distinct fixed
sub-paths (``pod-definitions``, ``pods``, ``pod-templates``,
``runs``) so they cannot collide with this module's
``{slug}/archive`` / ``{slug}/members`` / etc. fixed sub-paths.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Optional

from automojo.errors.exceptions import SemanticError
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.projects import service as project_service
from automojo.pychestrate.webservice.projects.exceptions import (
    LastAdminRemovalError,
    MemberBindingNotFoundError,
    MetadataFieldValidationError,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectStateTransitionError,
    SlugValidationError,
)
from automojo.pychestrate.webservice.projects.service import PROJECT_OWNER_ROLE


PROJECTS_PATH = "/projects"

_TRUTHY_QUERY_VALUES = ("1", "true", "yes")


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
        extensions: Optional[dict] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_actor_user_id(request: Request) -> Optional[str]:
    rtnval = getattr(request, "actor_user_id", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.
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


def _decode_json_or_abort(*, request: Request) -> dict:
    """
        Decode the request body as JSON, aborting 400 on missing /
        non-dict.
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


def _parse_force_flag(*, request: Request) -> bool:
    """
        Read the ``force`` query parameter and coerce to bool.
        ``1`` / ``true`` / ``yes`` (case-insensitive) → True;
        anything else → False; absent → False.

        :param request: Incoming webworks request.

        :returns: Bool.
    """
    raw = request.query_params.get("force", "")
    if raw is None:
        return False
    rtnval = raw.strip().lower() in _TRUTHY_QUERY_VALUES
    return rtnval


def _model_to_dict(project: Any) -> dict:
    """
        Render a :class:`Project` ORM row as the REST response
        dict.

        :param project: ORM project instance.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "project_id": str(project.project_id),
        "slug": project.slug,
        "display_name": project.display_name,
        "description": project.description,
        "state": project.state.value if project.state is not None else None,
        "owning_group_id": (
            str(project.owning_group_id)
            if project.owning_group_id is not None else None
        ),
        "template_id": project.template_id,
        "template_version": project.template_version,
        "extension_fields": (
            dict(project.extension_fields)
            if project.extension_fields is not None else {}
        ),
        "created_at": (
            project.created_at.isoformat()
            if project.created_at is not None else None
        ),
        "updated_at": (
            project.updated_at.isoformat()
            if project.updated_at is not None else None
        ),
        "archived_at": (
            project.archived_at.isoformat()
            if project.archived_at is not None else None
        ),
    }
    return rtnval


def _binding_to_dict(binding: Any) -> dict:
    """
        Render a :class:`ProjectMemberBinding` ORM row as a dict.

        :param binding: ORM binding instance.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "binding_id": str(binding.binding_id),
        "project_id": str(binding.project_id),
        "user_id": str(binding.user_id),
        "role_name": binding.role_name,
        "added_at": (
            binding.added_at.isoformat()
            if binding.added_at is not None else None
        ),
        "added_by_user_id": (
            str(binding.added_by_user_id)
            if binding.added_by_user_id is not None else None
        ),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers — project lifecycle
# ---------------------------------------------------------------------------


def handle_create_project(request: Request) -> Response:
    """
        ``POST /api/v1/projects`` — create a new project.

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the project dict, or
                  problem response on failure.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        slug = payload.get("slug", "")
        try:
            project = project_service.create_project(
                db_session=db_session,
                slug=slug,
                display_name=payload.get("display_name", ""),
                description=payload.get("description", ""),
                owning_group_id=payload.get("owning_group_id", None),
                template_id=payload.get("template_id", None),
                template_version=payload.get("template_version", None),
                actor_user_id=actor_user_id,
            )
        except SlugValidationError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"slug": slug},
            )
        except ProjectAlreadyExistsError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"slug": slug},
            )

        body = _model_to_dict(project)
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_project(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{slug}`` — read a project.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the project dict, or
                  problem response on failure.
    """
    slug = request.path_params.get("slug", "")
    try:
        db_session = _require_session(request=request)

        try:
            project = project_service.read_project_by_slug(
                db_session=db_session, slug=slug
            )
        except SlugValidationError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"slug": slug},
            )
        except ProjectNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"slug": slug},
            )

        body = _model_to_dict(project)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_patch_project(request: Request) -> Response:
    """
        ``PATCH /api/v1/projects/{slug}`` — update mutable fields
        (display_name, description, extension_fields).

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the updated project
                  dict, or problem response on failure.
    """
    slug = request.path_params.get("slug", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        try:
            project = project_service.patch_project(
                db_session=db_session,
                slug=slug,
                display_name=payload.get("display_name", None),
                description=payload.get("description", None),
                extension_fields=payload.get("extension_fields", None),
                actor_user_id=actor_user_id,
            )
        except ProjectNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"slug": slug},
            )
        except MetadataFieldValidationError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"slug": slug},
            )

        body = _model_to_dict(project)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_delete_project(request: Request) -> Response:
    """
        ``DELETE /api/v1/projects/{slug}`` — hard-delete an
        archived project. Returns 204 on success, 409 when the
        project is still active.

        :param request: Incoming webworks request.

        :returns: 204 (empty body) on success, problem response on
                  failure.
    """
    slug = request.path_params.get("slug", "")
    try:
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        try:
            project_service.delete_project(
                db_session=db_session,
                slug=slug,
                actor_user_id=actor_user_id,
            )
        except ProjectNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"slug": slug},
            )
        except ProjectStateTransitionError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"slug": slug},
            )

        rtnval: Response = Response(status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_archive_project(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{slug}/archive`` — archive a
        project.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the updated project
                  dict, or problem response on failure.
    """
    slug = request.path_params.get("slug", "")
    try:
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        try:
            project = project_service.archive_project(
                db_session=db_session,
                slug=slug,
                actor_user_id=actor_user_id,
            )
        except ProjectNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"slug": slug},
            )

        body = _model_to_dict(project)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_unarchive_project(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{slug}/unarchive`` — move a project
        out of ARCHIVED state.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the updated project
                  dict, or problem response on failure.
    """
    slug = request.path_params.get("slug", "")
    try:
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        try:
            project = project_service.unarchive_project(
                db_session=db_session,
                slug=slug,
                actor_user_id=actor_user_id,
            )
        except ProjectNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"slug": slug},
            )

        body = _model_to_dict(project)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Handlers — members
# ---------------------------------------------------------------------------


def handle_list_members(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{slug}/members`` — list members.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a list of binding
                  dicts, or problem response on failure.
    """
    slug = request.path_params.get("slug", "")
    try:
        db_session = _require_session(request=request)

        try:
            bindings = project_service.list_members(
                db_session=db_session, slug=slug
            )
        except ProjectNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"slug": slug},
            )

        body = [_binding_to_dict(binding) for binding in bindings]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_add_member(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{slug}/members`` — attach a user
        with a role.

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the binding dict, or
                  problem response on failure.
    """
    slug = request.path_params.get("slug", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        user_id = payload.get("user_id", "")
        role_name = payload.get("role_name", "")

        try:
            binding = project_service.add_member(
                db_session=db_session,
                slug=slug,
                user_id=user_id,
                role_name=role_name,
                actor_user_id=actor_user_id,
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={
                    "slug": slug,
                    "user_id": user_id,
                    "role_name": role_name,
                },
            )
        except ProjectNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"slug": slug},
            )

        body = _binding_to_dict(binding)
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_remove_member_owner_binding(request: Request) -> Response:
    """
        ``DELETE /api/v1/projects/{slug}/members/{user_id}`` —
        remove the :data:`PROJECT_OWNER_ROLE` binding for a user.
        Returns 409 when removing it would leave the project with
        no owner unless the caller passes ``?force=true``.

        :param request: Incoming webworks request.

        :returns: 204 (empty body) on success, problem response on
                  failure.
    """
    slug = request.path_params.get("slug", "")
    user_id = request.path_params.get("user_id", "")
    try:
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)
        force = _parse_force_flag(request=request)

        try:
            project_service.remove_member(
                db_session=db_session,
                slug=slug,
                user_id=user_id,
                role_name=PROJECT_OWNER_ROLE,
                actor_user_id=actor_user_id,
                force=force,
            )
        except ProjectNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"slug": slug},
            )
        except MemberBindingNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={
                    "slug": slug,
                    "user_id": user_id,
                    "role_name": PROJECT_OWNER_ROLE,
                },
            )
        except LastAdminRemovalError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"slug": slug, "user_id": user_id},
            )

        rtnval: Response = Response(status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_remove_member_specific_role(request: Request) -> Response:
    """
        ``DELETE /api/v1/projects/{slug}/members/{user_id}/{role_name}``
        — remove a specific ``(user_id, role_name)`` binding.

        :param request: Incoming webworks request.

        :returns: 204 (empty body) on success, problem response on
                  failure.
    """
    slug = request.path_params.get("slug", "")
    user_id = request.path_params.get("user_id", "")
    role_name = request.path_params.get("role_name", "")
    try:
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)
        force = _parse_force_flag(request=request)

        try:
            project_service.remove_member(
                db_session=db_session,
                slug=slug,
                user_id=user_id,
                role_name=role_name,
                actor_user_id=actor_user_id,
                force=force,
            )
        except ProjectNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"slug": slug},
            )
        except MemberBindingNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={
                    "slug": slug,
                    "user_id": user_id,
                    "role_name": role_name,
                },
            )
        except LastAdminRemovalError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={
                    "slug": slug,
                    "user_id": user_id,
                    "role_name": role_name,
                },
            )

        rtnval: Response = Response(status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_projects_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the project routes to a webworks application.

        These project-aggregate routes live under
        ``/projects/{slug}`` (depth 3) and ``/projects/{slug}/<sub>``
        (depth 4+). The pods port (#134) registers under
        ``/projects/{project_id}/<pod-or-related>`` with distinct
        fixed sub-paths -- no collision is possible.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix.

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH

    app.attach_route(base, methods=["POST"])(handle_create_project)

    app.attach_route(
        base + "/{slug}", methods=["GET"]
    )(handle_read_project)
    app.attach_route(
        base + "/{slug}", methods=["PATCH"]
    )(handle_patch_project)
    app.attach_route(
        base + "/{slug}", methods=["DELETE"]
    )(handle_delete_project)

    app.attach_route(
        base + "/{slug}/archive", methods=["POST"]
    )(handle_archive_project)
    app.attach_route(
        base + "/{slug}/unarchive", methods=["POST"]
    )(handle_unarchive_project)

    app.attach_route(
        base + "/{slug}/members", methods=["GET"]
    )(handle_list_members)
    app.attach_route(
        base + "/{slug}/members", methods=["POST"]
    )(handle_add_member)
    app.attach_route(
        base + "/{slug}/members/{user_id}", methods=["DELETE"]
    )(handle_remove_member_owner_binding)
    app.attach_route(
        base + "/{slug}/members/{user_id}/{role_name}", methods=["DELETE"]
    )(handle_remove_member_specific_role)

    return


__all__ = [
    "PROJECTS_PATH",
    "register_projects_routes",
    "handle_create_project",
    "handle_read_project",
    "handle_patch_project",
    "handle_delete_project",
    "handle_archive_project",
    "handle_unarchive_project",
    "handle_list_members",
    "handle_add_member",
    "handle_remove_member_owner_binding",
    "handle_remove_member_specific_role",
]
