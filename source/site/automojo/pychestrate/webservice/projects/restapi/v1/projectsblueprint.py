"""
.. module:: projects.restapi.v1.projectsblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/projects.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict

from automojo.errors.exceptions import SemanticError

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response
from automojo.webworks.security.accesspolicy import AccessPolicy


_ADMIN_POLICY = AccessPolicy(roles=("system-admin",))

from automojo.pychestrate.webservice.dbsessionmiddleware import (
    get_request_actor_user_id,
)
from automojo.pychestrate.webservice.projects import (
    service as project_service,
)
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


PROJECTS_BASE_PATH = "/api/v1/projects"


def _model_to_dict(project) -> Dict[str, Any]:
    """
        Render a :class:`Project` as the REST response dict.
    """
    if project.state is not None:
        state_field = project.state.value
    else:
        state_field = None
    if project.owning_group_id is not None:
        owning_group_field = str(project.owning_group_id)
    else:
        owning_group_field = None
    if project.extension_fields is not None:
        extension_fields_value = dict(project.extension_fields)
    else:
        extension_fields_value = {}
    if project.created_at is not None:
        created_at_field = project.created_at.isoformat()
    else:
        created_at_field = None
    if project.updated_at is not None:
        updated_at_field = project.updated_at.isoformat()
    else:
        updated_at_field = None
    if project.archived_at is not None:
        archived_at_field = project.archived_at.isoformat()
    else:
        archived_at_field = None
    rtnval = {
        "project_id": str(project.project_id),
        "slug": project.slug,
        "display_name": project.display_name,
        "description": project.description,
        "state": state_field,
        "owning_group_id": owning_group_field,
        "template_id": project.template_id,
        "template_version": project.template_version,
        "extension_fields": extension_fields_value,
        "created_at": created_at_field,
        "updated_at": updated_at_field,
        "archived_at": archived_at_field,
    }
    return rtnval


def _binding_to_dict(binding) -> Dict[str, Any]:
    """
        Render a :class:`ProjectMemberBinding` as a dict.
    """
    if binding.added_at is not None:
        added_at_field = binding.added_at.isoformat()
    else:
        added_at_field = None
    if binding.added_by_user_id is not None:
        added_by_field = str(binding.added_by_user_id)
    else:
        added_by_field = None
    rtnval = {
        "binding_id": str(binding.binding_id),
        "project_id": str(binding.project_id),
        "user_id": str(binding.user_id),
        "role_name": binding.role_name,
        "added_at": added_at_field,
        "added_by_user_id": added_by_field,
    }
    return rtnval


def _require_db_session(*, request: Request) -> Any:
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        err_lines = [
            "Request-scoped db_session not configured.",
            "DbSessionMiddleware must be installed in the pipeline.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise HTTPException(status_code=503, detail=err_msg)
    return db_session


def _read_json_body(*, request: Request) -> Dict[str, Any]:
    raw_body = request.body
    if raw_body is None:
        raise HTTPException(status_code=400, detail="request body required")
    if len(raw_body) == 0:
        raise HTTPException(status_code=400, detail="request body required")
    try:
        decoded = request.json()
    except Exception as exc:
        err_msg = "request body must be valid JSON"
        raise HTTPException(status_code=400, detail=err_msg) from exc
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object",
        )
    rtnval = decoded
    return rtnval


def _parse_force_flag(*, request: Request) -> bool:
    raw = request.query_params.get("force", "")
    if raw is None:
        return False
    if str(raw).strip().lower() in ("1", "true", "yes"):
        return True
    return False


class ProjectsBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/projects`` endpoints.
    """

    base_path = PROJECTS_BASE_PATH
    tags = ["projects", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/projects",
        methods=["POST"],
        doc=Doc(summary="Create project"),
        access_policy=_ADMIN_POLICY,
    )
    def create_project_endpoint(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)

        try:
            project = project_service.create_project(
                db_session=db_session,
                slug=payload.get("slug", ""),
                display_name=payload.get("display_name", ""),
                description=payload.get("description", ""),
                owning_group_id=payload.get("owning_group_id", None),
                template_id=payload.get("template_id", None),
                template_version=payload.get("template_version", None),
                actor_user_id=actor_user_id,
            )
        except SlugValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProjectAlreadyExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        body = _model_to_dict(project=project)
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{slug}",
        methods=["GET"],
        doc=Doc(summary="Read project"),
    )
    def read_project(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        slug = request.path_params.get("slug", "")

        try:
            project = project_service.read_project_by_slug(
                db_session=db_session, slug=slug,
            )
        except SlugValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        body = _model_to_dict(project=project)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{slug}",
        methods=["PATCH"],
        doc=Doc(summary="Patch project"),
    )
    def patch_project(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        slug = request.path_params.get("slug", "")

        try:
            project = project_service.patch_project(
                db_session=db_session,
                slug=slug,
                display_name=payload.get("display_name", None),
                description=payload.get("description", None),
                extension_fields=payload.get("extension_fields", None),
                actor_user_id=actor_user_id,
            )
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MetadataFieldValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        body = _model_to_dict(project=project)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{slug}",
        methods=["DELETE"],
        doc=Doc(summary="Delete archived project"),
    )
    def delete_project(request: Request) -> Response:
        db_session = _require_db_session(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        slug = request.path_params.get("slug", "")

        try:
            project_service.delete_project(
                db_session=db_session,
                slug=slug,
                actor_user_id=actor_user_id,
            )
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ProjectStateTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        rtnval = Response(status_code=204, body=b"")
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{slug}/archive",
        methods=["POST"],
        doc=Doc(summary="Archive project"),
    )
    def archive_project(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        slug = request.path_params.get("slug", "")

        try:
            project = project_service.archive_project(
                db_session=db_session,
                slug=slug,
                actor_user_id=actor_user_id,
            )
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        body = _model_to_dict(project=project)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{slug}/unarchive",
        methods=["POST"],
        doc=Doc(summary="Unarchive project"),
    )
    def unarchive_project(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        slug = request.path_params.get("slug", "")

        try:
            project = project_service.unarchive_project(
                db_session=db_session,
                slug=slug,
                actor_user_id=actor_user_id,
            )
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        body = _model_to_dict(project=project)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{slug}/members",
        methods=["GET"],
        doc=Doc(summary="List project members"),
    )
    def list_members(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        slug = request.path_params.get("slug", "")

        try:
            bindings = project_service.list_members(
                db_session=db_session, slug=slug,
            )
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        body = [_binding_to_dict(binding=b) for b in bindings]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{slug}/members",
        methods=["POST"],
        doc=Doc(summary="Add project member"),
    )
    def add_member(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        slug = request.path_params.get("slug", "")

        try:
            binding = project_service.add_member(
                db_session=db_session,
                slug=slug,
                user_id=payload.get("user_id", ""),
                role_name=payload.get("role_name", ""),
                actor_user_id=actor_user_id,
            )
        except SemanticError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        body = _binding_to_dict(binding=binding)
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{slug}/members/{user_id}",
        methods=["DELETE"],
        doc=Doc(
            summary="Remove project owner binding for user",
            description=(
                "Removes the PROJECT_OWNER_ROLE binding. Returns 409 "
                "when removing it would leave the project with no "
                "owner unless ``?force=true`` is supplied by an admin."
            ),
        ),
    )
    def remove_owner_binding(request: Request) -> Response:
        db_session = _require_db_session(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        force = _parse_force_flag(request=request)
        slug = request.path_params.get("slug", "")
        user_id = request.path_params.get("user_id", "")

        try:
            project_service.remove_member(
                db_session=db_session,
                slug=slug,
                user_id=user_id,
                role_name=PROJECT_OWNER_ROLE,
                actor_user_id=actor_user_id,
                force=force,
            )
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MemberBindingNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LastAdminRemovalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        rtnval = Response(status_code=204, body=b"")
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{slug}/members/{user_id}/{role_name}",
        methods=["DELETE"],
        doc=Doc(summary="Remove specific role binding"),
    )
    def remove_role_binding(request: Request) -> Response:
        db_session = _require_db_session(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        force = _parse_force_flag(request=request)
        slug = request.path_params.get("slug", "")
        user_id = request.path_params.get("user_id", "")
        role_name = request.path_params.get("role_name", "")

        try:
            project_service.remove_member(
                db_session=db_session,
                slug=slug,
                user_id=user_id,
                role_name=role_name,
                actor_user_id=actor_user_id,
                force=force,
            )
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MemberBindingNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LastAdminRemovalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        rtnval = Response(status_code=204, body=b"")
        return rtnval
