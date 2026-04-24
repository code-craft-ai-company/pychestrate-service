"""
.. module:: projects.restapi.v1.projects_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/projects.

.. moduleauthor:: Automation Mojo LLC

Implements the 2-projects M1 + M2 endpoints:

* ``POST  /api/v1/projects`` — create a project.
* ``GET   /api/v1/projects/{slug}`` — fetch a project.
* ``PATCH /api/v1/projects/{slug}`` — update mutable fields.
* ``POST  /api/v1/projects/{slug}/archive`` — archive a project.
* ``POST  /api/v1/projects/{slug}/unarchive`` — unarchive a project.
* ``DELETE /api/v1/projects/{slug}`` — hard-delete an archived project.
* ``GET/POST /api/v1/projects/{slug}/members`` — members list & add.
* ``DELETE /api/v1/projects/{slug}/members/{user_id}`` — remove a
  member's owner binding with the last-admin safeguard.
* ``DELETE /api/v1/projects/{slug}/members/{user_id}/{role_name}`` —
  remove a specific ``(user_id, role_name)`` binding.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Optional

from flask import g, request
from flask_restx import Namespace, Resource, fields

from automojo.errors.exceptions import SemanticError

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


PROJECTS_NAMESPACE_PATH = "/projects"


projects_ns = Namespace(
    "Projects v1",
    description="Project aggregates (2-projects).",
)


project_create_model = projects_ns.model(
    "ProjectCreate",
    {
        "slug": fields.String(required=True, description="Canonical URL slug"),
        "display_name": fields.String(required=True, description="Human-facing name"),
        "description": fields.String(required=False, default="", description="Free-form description"),
        "owning_group_id": fields.String(required=False, description="Owning group id"),
        "template_id": fields.String(required=False, description="Project template id"),
        "template_version": fields.String(required=False, description="Project template version (SemVer)"),
    },
)


project_response_model = projects_ns.model(
    "ProjectResponse",
    {
        "project_id": fields.String(description="Server-generated UUID"),
        "slug": fields.String(description="Canonical URL slug"),
        "display_name": fields.String(description="Human-facing name"),
        "description": fields.String(description="Free-form description"),
        "state": fields.String(description="ACTIVE | ARCHIVED"),
        "owning_group_id": fields.String(description="Owning group id"),
        "template_id": fields.String(description="Project template id"),
        "template_version": fields.String(description="Project template version"),
        "extension_fields": fields.Raw(description="Metadata fields"),
        "created_at": fields.String(description="Create timestamp (ISO-8601)"),
        "updated_at": fields.String(description="Update timestamp (ISO-8601)"),
        "archived_at": fields.String(description="Archive timestamp (ISO-8601)"),
    },
)


project_patch_model = projects_ns.model(
    "ProjectPatch",
    {
        "display_name": fields.String(required=False),
        "description": fields.String(required=False),
        "extension_fields": fields.Raw(required=False, description="Metadata fields mapping"),
    },
)


project_member_add_model = projects_ns.model(
    "ProjectMemberAdd",
    {
        "user_id": fields.String(required=True),
        "role_name": fields.String(required=True),
    },
)


project_member_response_model = projects_ns.model(
    "ProjectMemberResponse",
    {
        "binding_id": fields.String,
        "project_id": fields.String,
        "user_id": fields.String,
        "role_name": fields.String,
        "added_at": fields.String,
        "added_by_user_id": fields.String,
    },
)


def _model_to_dict(project) -> dict:
    """
        Render a :class:`Project` as the REST response dict.

        :param project: The persistent model instance.

        :returns: A plain dict suitable for JSON serialization.
    """
    rtnval = {
        "project_id": str(project.project_id),
        "slug": project.slug,
        "display_name": project.display_name,
        "description": project.description,
        "state": project.state.value if project.state is not None else None,
        "owning_group_id": str(project.owning_group_id) if project.owning_group_id is not None else None,
        "template_id": project.template_id,
        "template_version": project.template_version,
        "extension_fields": dict(project.extension_fields) if project.extension_fields is not None else {},
        "created_at": project.created_at.isoformat() if project.created_at is not None else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at is not None else None,
        "archived_at": project.archived_at.isoformat() if project.archived_at is not None else None,
    }
    return rtnval


def _binding_to_dict(binding) -> dict:
    """
        Render a :class:`ProjectMemberBinding` as a dict.

        :param binding: The persistent binding instance.

        :returns: A plain dict suitable for JSON serialization.
    """
    rtnval = {
        "binding_id": str(binding.binding_id),
        "project_id": str(binding.project_id),
        "user_id": str(binding.user_id),
        "role_name": binding.role_name,
        "added_at": binding.added_at.isoformat() if binding.added_at is not None else None,
        "added_by_user_id": str(binding.added_by_user_id) if binding.added_by_user_id is not None else None,
    }
    return rtnval


def _get_request_db_session():
    """
        Resolve the request-scoped SQLAlchemy session.

        :returns: The SQLAlchemy Session.
    """
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        projects_ns.abort(503, "Request-scoped db_session not configured")
    return db_session


def _get_request_actor_user_id() -> Optional[str]:
    """
        Resolve the acting principal's user id.

        :returns: The acting user id string, or None.
    """
    actor = getattr(g, "actor_user_id", None)
    return actor


def _parse_force_flag() -> bool:
    """
        Read the ``force`` query parameter coercing to bool.

        :returns: True when the caller passed ``?force=true`` (case
                  insensitive); False otherwise.
    """
    raw = request.args.get("force", "")
    rtnval = False
    if raw is not None and str(raw).strip().lower() in ("1", "true", "yes"):
        rtnval = True
    return rtnval


@projects_ns.route("")
class ProjectsList(Resource):
    """
        Resource that exposes POST ``/api/v1/projects`` for creation.
    """

    @projects_ns.expect(project_create_model, validate=True)
    @projects_ns.marshal_with(project_response_model, code=201)
    def post(self):
        """
            Create a new project.
        """
        payload = request.get_json(force=True, silent=False)

        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

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
        except SlugValidationError as xcpt:
            projects_ns.abort(400, str(xcpt))
        except ProjectAlreadyExistsError as xcpt:
            projects_ns.abort(409, str(xcpt))

        rtnval = _model_to_dict(project)
        return rtnval, 201


@projects_ns.route("/<string:slug>")
@projects_ns.param("slug", "The canonical project slug")
class ProjectDetail(Resource):
    """
        Resource that exposes GET/PATCH/DELETE ``/api/v1/projects/{slug}``.
    """

    @projects_ns.marshal_with(project_response_model)
    def get(self, slug: str):
        """
            Fetch a project by slug.
        """
        db_session = _get_request_db_session()
        try:
            project = project_service.read_project_by_slug(db_session=db_session, slug=slug)
        except SlugValidationError as xcpt:
            projects_ns.abort(400, str(xcpt))
        except ProjectNotFoundError as xcpt:
            projects_ns.abort(404, str(xcpt))

        rtnval = _model_to_dict(project)
        return rtnval

    @projects_ns.expect(project_patch_model, validate=True)
    @projects_ns.marshal_with(project_response_model)
    def patch(self, slug: str):
        """
            Update mutable fields.
        """
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

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
            projects_ns.abort(404, str(xcpt))
        except MetadataFieldValidationError as xcpt:
            projects_ns.abort(422, str(xcpt))

        rtnval = _model_to_dict(project)
        return rtnval

    def delete(self, slug: str):
        """
            Hard-delete an archived project.
        """
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

        try:
            project_service.delete_project(
                db_session=db_session, slug=slug, actor_user_id=actor_user_id,
            )
        except ProjectNotFoundError as xcpt:
            projects_ns.abort(404, str(xcpt))
        except ProjectStateTransitionError as xcpt:
            projects_ns.abort(409, str(xcpt))

        return "", 204


@projects_ns.route("/<string:slug>/archive")
@projects_ns.param("slug", "The canonical project slug")
class ProjectArchiveResource(Resource):
    """
        POST ``/api/v1/projects/{slug}/archive``.
    """

    @projects_ns.marshal_with(project_response_model)
    def post(self, slug: str):
        """
            Archive a project.
        """
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

        try:
            project = project_service.archive_project(
                db_session=db_session, slug=slug, actor_user_id=actor_user_id,
            )
        except ProjectNotFoundError as xcpt:
            projects_ns.abort(404, str(xcpt))

        rtnval = _model_to_dict(project)
        return rtnval


@projects_ns.route("/<string:slug>/unarchive")
@projects_ns.param("slug", "The canonical project slug")
class ProjectUnarchiveResource(Resource):
    """
        POST ``/api/v1/projects/{slug}/unarchive``.
    """

    @projects_ns.marshal_with(project_response_model)
    def post(self, slug: str):
        """
            Move a project out of archived state.
        """
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

        try:
            project = project_service.unarchive_project(
                db_session=db_session, slug=slug, actor_user_id=actor_user_id,
            )
        except ProjectNotFoundError as xcpt:
            projects_ns.abort(404, str(xcpt))

        rtnval = _model_to_dict(project)
        return rtnval


@projects_ns.route("/<string:slug>/members")
@projects_ns.param("slug", "The canonical project slug")
class ProjectMembersResource(Resource):
    """
        GET/POST on the project members collection.
    """

    @projects_ns.marshal_list_with(project_member_response_model)
    def get(self, slug: str):
        """
            List members.
        """
        db_session = _get_request_db_session()
        try:
            bindings = project_service.list_members(
                db_session=db_session, slug=slug,
            )
        except ProjectNotFoundError as xcpt:
            projects_ns.abort(404, str(xcpt))

        rtnval = [_binding_to_dict(b) for b in bindings]
        return rtnval

    @projects_ns.expect(project_member_add_model, validate=True)
    @projects_ns.marshal_with(project_member_response_model, code=201)
    def post(self, slug: str):
        """
            Attach a user with a role.
        """
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

        try:
            binding = project_service.add_member(
                db_session=db_session,
                slug=slug,
                user_id=payload.get("user_id", ""),
                role_name=payload.get("role_name", ""),
                actor_user_id=actor_user_id,
            )
        except SemanticError as xcpt:
            projects_ns.abort(400, str(xcpt))
        except ProjectNotFoundError as xcpt:
            projects_ns.abort(404, str(xcpt))

        rtnval = _binding_to_dict(binding)
        return rtnval, 201


@projects_ns.route("/<string:slug>/members/<string:user_id>")
@projects_ns.param("slug", "The canonical project slug")
@projects_ns.param("user_id", "The user id")
class ProjectMemberByUserIdDetail(Resource):
    """
        DELETE ``/api/v1/projects/{slug}/members/{user_id}``.

        Removes the :data:`PROJECT_OWNER_ROLE` binding for the user.
        Returns 409 when removing that binding would leave the project
        with no owner, unless the caller passes ``?force=true`` and
        holds platform admin.
    """

    def delete(self, slug: str, user_id: str):
        """
            Detach the ProjectOwner binding for a user (last-admin safeguard).
        """
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()
        force = _parse_force_flag()

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
            projects_ns.abort(404, str(xcpt))
        except MemberBindingNotFoundError as xcpt:
            projects_ns.abort(404, str(xcpt))
        except LastAdminRemovalError as xcpt:
            projects_ns.abort(409, str(xcpt))

        return "", 204


@projects_ns.route("/<string:slug>/members/<string:user_id>/<string:role_name>")
@projects_ns.param("slug", "The canonical project slug")
@projects_ns.param("user_id", "The user id")
@projects_ns.param("role_name", "The role name")
class ProjectMemberRoleDetail(Resource):
    """
        DELETE ``/api/v1/projects/{slug}/members/{user_id}/{role_name}``.
    """

    def delete(self, slug: str, user_id: str, role_name: str):
        """
            Detach a specific binding.
        """
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()
        force = _parse_force_flag()

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
            projects_ns.abort(404, str(xcpt))
        except MemberBindingNotFoundError as xcpt:
            projects_ns.abort(404, str(xcpt))
        except LastAdminRemovalError as xcpt:
            projects_ns.abort(409, str(xcpt))

        return "", 204


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(projects_ns, version_prefix + PROJECTS_NAMESPACE_PATH)]
    return rtnval
