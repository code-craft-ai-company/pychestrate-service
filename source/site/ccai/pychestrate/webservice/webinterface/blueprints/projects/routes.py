"""
.. module:: webinterface.blueprints.projects.routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /projects.

.. moduleauthor:: Code Craft AI LLC

The complete consumer-facing ``/projects`` UI on webworks.

Routes landed in this module (dashboard + project core +
members):

* ``GET  /projects/`` and ``/projects/dashboard``
* ``GET  /projects/list``
* ``GET  /projects/create``
* ``POST /projects/create``
* ``GET  /projects/{project_id}``
* ``GET  /projects/{project_id}/edit``
* ``POST /projects/{project_id}/edit``
* ``POST /projects/{project_id}/delete``
* ``GET  /projects/{project_id}/members``
* ``GET  /projects/{project_id}/members/add``
* ``POST /projects/{project_id}/members/add``
* ``GET  /projects/{project_id}/members/{user_id}/edit``
* ``POST /projects/{project_id}/members/{user_id}/edit``
* ``POST /projects/{project_id}/members/{user_id}/remove``

The remaining 39 routes live in the per-feature sub-modules
(``routes_repositories`` / ``routes_builds`` /
``routes_infrastructure`` / ``routes_tests`` /
``routes_releases`` / ``routes_calendar`` /
``routes_watches``) and are cascaded by
:func:`register_projects_routes`.

Permission model
----------------

The legacy ``@project_permission_required('admin' | 'owner')``
decorator gates writes by calling
``ProjectManager.check_permission(project_id, user_id,
permission)``. Ported as :func:`_require_project_permission_or_redirect`
-- analogous to config.routes._require_permission_or_redirect
but parameterized by project_id and using the project manager's
3-argument check rather than the security manager's 2-argument.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging
import uuid

from datetime import datetime

from typing import Any, Callable, Dict, List, Optional

from ccai.pychestrate.webservice.webinterface.site_shell import (
    ui_profile as _ui_profile_scope,
)

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    csrf,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.projects.dashboard_activity import (
    collect_run_activity,
)
from ccai.pychestrate.webservice.projects.bridge import bridge_tables_present
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    MultiFormView,
    _AuthResolution,
    _attach_session_to_response,
    _build_default_template_context,
    extract_fragment_title,
    _deny_redirect_target,
    _has_permission,
    _parse_form_multi,
    _parse_form_or_empty,
    _not_found_page_for,
    _not_found_redirect,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
)


PROJECTS_PATH = "/projects"

#: Permission that lets a user create accounts. The member picker
#: links to the Create User page only for users who hold it.
USERS_WRITE_PERMISSION = "system:users.write"

#: Upper bound on the users listed in the member picker; the search
#: box narrows the list when a deployment has more accounts.
MEMBER_PICKER_LIMIT = 200


_ROUTE_TABLE = (
    ("projects.list_root", "/", ("GET",)),
    ("projects.dashboard", "/dashboard", ("GET",)),
    ("projects.project_list", "/list", ("GET",)),
    ("projects.project_create", "/create", ("GET", "POST")),
    ("projects.project_detail", "/{project_id}", ("GET",)),
    (
        "projects.project_workspace_link",
        "/{project_id}/open/{destination}",
        ("GET",),
    ),
    (
        "projects.project_edit",
        "/{project_id}/edit",
        ("GET", "POST"),
    ),
    (
        "projects.project_delete",
        "/{project_id}/delete",
        ("POST",),
    ),
    (
        "projects.member_list",
        "/{project_id}/members",
        ("GET",),
    ),
    (
        "projects.member_add",
        "/{project_id}/members/add",
        ("GET", "POST"),
    ),
    (
        "projects.member_edit",
        "/{project_id}/members/{user_id}/edit",
        ("GET", "POST"),
    ),
    (
        "projects.member_remove",
        "/{project_id}/members/{user_id}/remove",
        ("POST",),
    ),
)


# All eleven projects sub-features (F1 dashboard / core / members,
# F2 repositories, F3 builds + infrastructure, F4 tests + releases,
# F5 calendar + watches) are now landed.  Nothing left to
# pre-register.
_FUTURE_ENDPOINT_PATTERNS: tuple = ()


# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _build_project_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ProjectManager` whose permission checks
        and project lists honour global project roles as well as
        membership (see :mod:`project_access`). Lazy-imports.

        :param db_session: Open SQLAlchemy session.

        :returns: ProjectManager instance.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.project_access import (  # noqa: E402
        build_access_aware_project_manager,
    )
    rtnval = build_access_aware_project_manager(db_session=db_session)
    return rtnval


def _build_user_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`UserManager`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.user_manager import (  # noqa: E402
        UserManager,
    )
    rtnval = UserManager(db_session)
    return rtnval


def _build_repository_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`RepositoryManager`. Used by the
        project_detail handler for the "recent repositories"
        summary panel. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.repository_manager import (  # noqa: E402
        RepositoryManager,
    )
    rtnval = RepositoryManager(db_session)
    return rtnval


def _build_build_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`BuildManager` for the project_detail
        recent-builds summary. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.build_manager import (  # noqa: E402
        BuildManager,
    )
    rtnval = BuildManager(db_session)
    return rtnval


def _build_test_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`TestManager` for the project_detail
        recent-tests summary. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.test_manager import (  # noqa: E402
        TestManager,
    )
    rtnval = TestManager(db_session)
    return rtnval


def _build_project_create_request(
        *, name: str, description: str, metadata: Dict[str, Any]
    ) -> Any:
    """
        Construct a :class:`ProjectCreateRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectCreateRequest,
    )
    rtnval = ProjectCreateRequest(
        name=name, description=description, metadata=metadata
    )
    return rtnval


def _build_project_update_request(
        *,
        name: Optional[str],
        description: Optional[str],
        metadata: Optional[Dict[str, Any]]
    ) -> Any:
    """
        Construct a :class:`ProjectUpdateRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectUpdateRequest,
    )
    rtnval = ProjectUpdateRequest(
        name=name, description=description, metadata=metadata
    )
    return rtnval


def _delete_project_rpa_rows(db_session: Any, project_id: int) -> None:
    """
        Related-rows cleanup handed to
        :meth:`ProjectManager.delete_project`: remove the project's RPA
        specifications, revisions and jobs in the same transaction.

        RPA rows refer to a project by id without a foreign key, so
        without this a deleted project's specifications stayed behind
        and a later project that reused the id showed them as its own.
        Refuses (and so rolls back the whole deletion) while any of the
        project's RPA jobs is still pending or running.

        :param db_session: The project manager's open session.
        :param project_id: Id of the project being deleted.

        :raises ProjectHasActiveJobsError: when RPA jobs are active.
    """
    from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectHasActiveJobsError,
    )
    from ccai.pychestrate.webservice.orchestration.rpa import (  # noqa: E402
        repository as rpa_repository,
    )

    project_ref = str(project_id)
    active_jobs = rpa_repository.count_active_jobs_for_project(
        db_session=db_session, project_id=project_ref
    )
    if active_jobs > 0:
        raise ProjectHasActiveJobsError(
            "Cannot delete the project while {} RPA job(s) are still "
            "pending or running. Wait for them to finish or cancel "
            "them first.".format(active_jobs)
        )
    rpa_repository.delete_project_rows(
        db_session=db_session, project_id=project_ref
    )
    return


def _resolve_project_role(*, role_str: str) -> Any:
    """
        Resolve a string to the :class:`ProjectRole` enum value.
        Raises ValueError on unknown.
    """
    from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectRole,
    )
    rtnval = ProjectRole(role_str)
    return rtnval


#: The inputs of the member forms, and their labels for the error summary.
_MEMBER_FORM_FIELDS = ("user_id", "role")
MEMBER_FIELD_LABELS: Dict[str, str] = {
    "user_id": "User",
    "role": "Role",
}


def _resolve_member_role(*, role_str: str) -> Any:
    """
        Like :func:`_resolve_project_role`, but an unknown role is a
        form error about the role input rather than a bare ValueError.
    """
    try:
        rtnval = _resolve_project_role(role_str=role_str)
    except ValueError:
        raise ProjectsFormError("Choose one of the listed roles.", field="role") from None
    return rtnval


#: What each project role may do, shown next to the role picker. The
#: global ``project-*`` roles (assigned on a user's page) give the
#: matching role on every project.
PROJECT_ROLE_DESCRIPTIONS: Dict[str, str] = {
    "owner": "Owner - everything, including deleting the project (global role: project-owner)",
    "administrator": "Administrator - manage members, settings and releases",
    "developer": "Developer - run builds, tests, infrastructure and RPA jobs (global role: project-editor)",
    "viewer": "Viewer - read-only access (global role: project-viewer)",
}


def _list_global_project_access(*, db_session: Any) -> List[Dict[str, Any]]:
    """
        Users who can open every project through a global role, for the
        Members page. Lazy-imports; any failure yields an empty list.

        :param db_session: Open SQLAlchemy session.

        :returns: Rows from :func:`project_access.list_global_project_access`.
    """
    try:
        from ccai.pychestrate.webservice.webinterface.blueprints.projects.project_access import (  # noqa: E402
            list_global_project_access,
        )
        rtnval = list_global_project_access(db_session=db_session)
    except Exception:
        _projects_ui_logger.exception(
            "pychestrate.ui.projects.global_access_lookup_failed"
        )
        rtnval = []
    return rtnval


def _enumerate_project_role_values() -> List[str]:
    """
        Return every :class:`ProjectRole` value as a string. For
        the role-selector <select> dropdown.
    """
    try:
        from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
            ProjectRole,
        )
    except ImportError:
        return []
    rtnval: List[str] = []
    for member in ProjectRole:
        rtnval.append(member.value)
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _legacy_id_for_registry_ref(*, db_session: Any, ref: Any) -> Optional[int]:
    """
        The web-UI project id of the registry project a slug or UUID
        names (see :mod:`projects.bridge`), or None.

        :param db_session: Open SQLAlchemy session.
        :param ref: Registry slug or UUID.
    """
    from ccai.pychestrate.webservice.projects.repository import (  # noqa: E402
        resolve_project_ref,
    )
    if ref is None or len(str(ref).strip()) == 0:
        return None
    try:
        project = resolve_project_ref(db_session=db_session, ref=str(ref).strip())
    except Exception:
        project = None
    if project is None or project.legacy_proj_id is None:
        return None
    rtnval = int(project.legacy_proj_id)
    return rtnval


def _registry_project_for_legacy(*, db_session: Any, legacy_proj_id: Optional[int]) -> Optional[Any]:
    """
        The registry project linked to a web-UI project (its UUID and
        slug are what the global views and the REST API use), or None.

        :param db_session: Open SQLAlchemy session.
        :param legacy_proj_id: Web-UI project id.
    """
    from ccai.pychestrate.webservice.projects.repository import (  # noqa: E402
        get_project_by_legacy_id,
    )
    if legacy_proj_id is None:
        return None
    try:
        rtnval = get_project_by_legacy_id(db_session=db_session, legacy_proj_id=int(legacy_proj_id))
    except Exception:
        rtnval = None
    return rtnval


def _coerce_int(*, raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        rtnval = int(raw)
    except (TypeError, ValueError):
        return None
    return rtnval


def _coerce_int_with_default(*, raw: Any, default: int) -> int:
    parsed = _coerce_int(raw=raw)
    if parsed is None:
        return default
    return parsed


def _coerce_user_id(*, raw: Any) -> Optional[str]:
    """
        Normalize a user id from a form field or path parameter.

        User ids are UUIDs (``user.user_id``), so they must never go
        through :func:`_coerce_int` -- that turned every real id into
        ``None`` and made adding, editing and removing members fail
        with "user_id is required".

        :param raw: Raw value (string, UUID or ``None``).

        :returns: The canonical lower-case UUID string, or ``None``
                  when the value is empty or not a UUID.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if len(text) == 0:
        return None
    try:
        parsed = uuid.UUID(text)
    except (TypeError, ValueError, AttributeError):
        return None
    rtnval = str(parsed)
    return rtnval


def _parse_pagination_params(
        *, request: Request,
        default_per_page: int = 20
    ) -> Dict[str, Any]:
    page = _coerce_int_with_default(
        raw=request.query_params.get("page", None), default=1
    )
    if page < 1:
        page = 1
    per_page = _coerce_int_with_default(
        raw=request.query_params.get("per_page", None),
        default=default_per_page,
    )
    if per_page < 1:
        per_page = default_per_page
    rtnval = {"page": page, "per_page": per_page}
    return rtnval


def _total_pages_from_count(*, total: int, per_page: int) -> int:
    """
        Compute the real page count from a list response's
        ``total`` field.

        :param total: Total matching rows reported by the manager.
        :param per_page: Page size.

        :returns: Number of pages (at least 1).
    """
    if total is None:
        return 1
    if total <= 0:
        return 1
    rtnval = (total + per_page - 1) // per_page
    return rtnval


def _parse_metadata_json_or_default(
        *, raw: str, default: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
    """
        Parse a JSON object string from the metadata textarea.
        Empty input yields ``default``; bad JSON raises
        ValueError; non-object JSON raises ValueError.
    """
    if raw is None or len(raw) == 0:
        return default
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProjectsFormError("Invalid JSON in metadata field.") from exc
    if not isinstance(parsed, dict):
        raise ProjectsFormError(
            "Metadata must be a JSON object, not a {}".format(
                type(parsed).__name__
            )
        )
    return parsed


def _require_project_permission_or_redirect(
        *,
        project_manager: Any,
        auth: _AuthResolution,
        project_id: int,
        permission: str,
        deny_redirect_url: str,
        deny_message: str = (
            "You do not have permission to perform this action."
        )
    ) -> Optional[Response]:
    """
        Project-permission gate. Calls
        :meth:`ProjectManager.check_permission` (3-arg signature:
        project_id, user_id, permission) and either returns
        ``None`` (allowed) or a redirect with an error flash
        queued on the session (denied).

        On the deny path the helper attaches the (mutated)
        session cookie to the redirect response. Treats any
        exception from check_permission as denial -- no
        fail-open.

        :param project_manager: Already-built ProjectManager.
        :param auth: Resolution from
                     :func:`_resolve_authenticated_request`.
        :param project_id: Target project id.
        :param permission: Permission level (e.g. ``'admin'``,
                           ``'owner'``, ``'view'``).
        :param deny_redirect_url: URL to redirect to on denial.
        :param deny_message: Optional flash message on denial.

        :returns: ``None`` when the user has the permission;
                  :class:`RedirectResponse` (302) on denial.
    """
    try:
        has_permission = project_manager.check_permission(
            project_id, auth.user_id, permission
        )
    except Exception:
        has_permission = False

    if has_permission is True:
        return None

    flash.add_flash(
        session=auth.session,
        message=deny_message,
        category=flash.CATEGORY_ERROR,
    )
    target_url = _deny_redirect_target(
        auth=auth, fallback_url=deny_redirect_url
    )
    rtnval = RedirectResponse(url=target_url, status_code=302)
    _attach_session_to_response(response=rtnval, session=auth.session)
    return rtnval


def _resolve_project_or_redirect(
        *,
        auth: _AuthResolution,
        project_manager: Any,
        project_id: Optional[int]
    ) -> Any:
    """
        Common detail-page setup: coerce + look up the project,
        return either the resolved project OR a redirect response
        (when project_id is None or the project doesn't exist).

        :returns: Either a project object on success, or a
                  ``RedirectResponse`` to /projects/list on
                  failure.
    """
    if project_id is None:
        rtnval = _not_found_redirect(
            session=auth.session,
            url=_url_for_module.url_for("projects.project_list"),
            message="Project not found.",
        )
        return rtnval

    project = project_manager.get_project(project_id)
    if project is None:
        rtnval = _not_found_redirect(
            session=auth.session,
            url=_url_for_module.url_for("projects.project_list"),
            message="Project not found.",
        )
        return rtnval
    return project


# ---------------------------------------------------------------------------
# Handlers — dashboard
# ---------------------------------------------------------------------------


def _created_at_sort_key(*, item: Any) -> Any:
    """
        Sort key for merging per-project recent-activity rows.
        Falls back to ``datetime.min`` when a row carries no
        ``created_at`` so mixed rows still sort deterministically.
    """
    created_at = getattr(item, "created_at", None)
    if created_at is None:
        return datetime.min
    return created_at


#: Projects the dashboard lists; the rest are behind "View all".
DASHBOARD_PROJECT_LIMIT = 10


def _collect_recent_activity(
        *, db_session: Any, project_ids: Optional[List[Any]], limit: int = 10
    ) -> Dict[str, List[Any]]:
    """
        Gather the most recent builds and test jobs across all of the
        user's projects for the dashboard activity panels: one query for
        each, not two per project (which also left out every project past
        the dashboard's first ten).

        :param db_session: Open SQLAlchemy session.
        :param project_ids: The ids of the projects the person can see, or
                            None for every project.
        :param limit: Maximum rows per activity list.

        :returns: Dict with ``builds`` and ``tests`` lists,
                  newest first.
    """
    build_manager = _build_build_manager(db_session=db_session)
    test_manager = _build_test_manager(db_session=db_session)

    builds = build_manager.list_builds(
        project_ids=project_ids, limit=limit
    ).builds
    jobs = test_manager.list_jobs(
        project_ids=project_ids, limit=limit
    ).jobs
    rtnval = {
        "builds": sorted(
            builds, key=lambda item: _created_at_sort_key(item=item), reverse=True
        )[:limit],
        "tests": sorted(
            jobs, key=lambda item: _created_at_sort_key(item=item), reverse=True
        )[:limit],
    }
    return rtnval


def handle_dashboard(request: Request) -> Response:
    """
        ``GET /projects/dashboard`` -- what needs attention first. ``/projects``
        itself is the list of projects (PRJ-27: the sidebar's "All Projects" and
        the project pages' "All Projects" opened different pages).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_manager = _build_project_manager(db_session=db_session)
        projects_response = project_manager.list_projects(
            auth.user_id, limit=DASHBOARD_PROJECT_LIMIT
        )
        projects = projects_response.projects
        project_total = getattr(projects_response, "total", None)
        if project_total is None:
            project_total = len(projects)

        accessible_ids = project_manager.accessible_project_ids(auth.user_id)
        recent_activity = _collect_recent_activity(
            db_session=db_session,
            project_ids=accessible_ids,
        )
        # What is broken first (PRJ-21): the runs that failed this week, the
        # latest runs and each listed project's last run, read from the runs the
        # service holds through the registry projects the web UI's are bridged to.
        run_activity = {"attention": [], "recent": [], "last_by_project": {}}
        if bridge_tables_present(db_session=db_session) is True:
            run_activity = collect_run_activity(
                db_session=db_session,
                accessible_legacy_ids=accessible_ids,
                listed_legacy_ids=[project.id for project in projects],
            )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.dashboard",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["projects"] = projects
        context["project_total"] = project_total
        context["recent_builds"] = recent_activity["builds"]
        context["recent_tests"] = recent_activity["tests"]
        context["dashboard_attention_runs"] = run_activity["attention"]
        context["dashboard_recent_runs"] = run_activity["recent"]
        context["dashboard_last_runs"] = run_activity["last_by_project"]
        context["dashboard_project_names"] = {project.id: project.name for project in projects}
        response = _render(
            template_name="projects/dashboard.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Handlers — project core
# ---------------------------------------------------------------------------


def _editable_project_ids(*, project_manager: Any, user_id: Any, projects: Any) -> List[Any]:
    """
        The ids of the listed projects the person may edit, so the list
        shows Edit only where it would not bounce them. It asks the same
        question the edit page does (the ``admin`` permission), and any
        failure to answer counts as "no".

        :param project_manager: Already-built ProjectManager.
        :param user_id: The signed-in person.
        :param projects: The projects on this page of the list.

        :returns: The ids of the editable ones.
    """
    rtnval: List[Any] = []
    for project in projects:
        try:
            allowed = project_manager.check_permission(project.id, user_id, "admin")
        except Exception:
            allowed = False
        if allowed is True:
            rtnval.append(project.id)
    return rtnval


def handle_project_list(request: Request) -> Response:
    """
        ``GET /projects`` and ``GET /projects/list`` -- the list of projects.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]
        search = request.query_params.get("search", "") or ""

        project_manager = _build_project_manager(db_session=db_session)
        projects_result = project_manager.list_projects(
            user_id=auth.user_id,
            offset=offset,
            limit=params["per_page"],
            search=search if len(search) > 0 else None,
        )
        projects = projects_result.projects

        total_pages = _total_pages_from_count(
            total=projects_result.total,
            per_page=params["per_page"],
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.project_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["projects"] = projects
        context["editable_project_ids"] = _editable_project_ids(
            project_manager=project_manager, user_id=auth.user_id, projects=projects,
        )
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["total"] = projects_result.total
        context["search"] = search

        response = _render(
            template_name="projects/projects/list.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


#: Inputs the project create and edit forms show errors for.
_PROJECT_FORM_FIELDS = ("name", "description", "metadata")

#: Visible labels of the project form fields, for the error summary.
PROJECT_FIELD_LABELS: Dict[str, str] = {
    "name": "Project Name",
    "description": "Description",
    "metadata": "Metadata (JSON)",
}


def _project_form_errors(*, exc: BaseException, parsing_field: str = "metadata") -> Dict[str, str]:
    """
        Inline errors for the project forms: the manager's field, or the
        input a ``ValueError`` from parsing the typed text is about
        (``parsing_field``, the metadata textarea). Empty when the error
        is about no single input; the caller then shows the message above
        the form so it is never lost.

        :param exc: The error being handled.
        :param parsing_field: The input a ``ValueError`` is about.

        :returns: ``{input name: message}`` for ``ui.field_error``.
    """
    if isinstance(exc, ValueError) is True:
        rtnval = {parsing_field: getattr(exc, "message", None) or str(exc)}
    else:
        rtnval = _field_errors_from(exc=exc, fields=_PROJECT_FORM_FIELDS)
    return rtnval


def _render_project_create_form(
        *, auth: _AuthResolution,
        form_data: Optional[MultiFormView],
        status_code: int = 200,
        errors: Optional[Dict[str, str]] = None
    ) -> HTMLResponse:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="projects.project_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["form_data"] = form_data
    context["errors"] = errors if errors is not None else {}
    context["error_labels"] = PROJECT_FIELD_LABELS
    response = _render(
        template_name="projects/projects/create.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(
        response=response, session=auth.session
    )
    return response


def handle_project_create(request: Request) -> Response:
    """
        ``GET /projects/create`` / ``POST /projects/create``.
        Login-only -- no project-permission gate (project does
        not yet exist).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        method = request.method.upper()

        if method == "GET":
            return _render_project_create_form(
                auth=auth, form_data=None
            )

        # POST
        single_form = _parse_form_or_empty(request=request)
        multi_form = _parse_form_multi(request=request)
        form_view = MultiFormView(data=multi_form)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "projects.project_create"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        description = str(single_form.get("description", "")).strip()
        metadata_str = str(single_form.get("metadata", "")).strip()
        errors: Dict[str, str] = {}

        try:
            metadata = _parse_metadata_json_or_default(
                raw=metadata_str, default={}
            )
            if metadata is None:
                metadata = {}
            create_request = _build_project_create_request(
                name=name, description=description, metadata=metadata
            )
            project_manager = _build_project_manager(db_session=db_session)
            project = project_manager.create_project(
                create_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.project_detail", project_id=project.id
                ),
                message='Project "{}" created successfully.'.format(name),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            errors = _project_form_errors(exc=exc)
            if len(errors) == 0:
                flash.add_flash(
                    session=auth.session,
                    message=_describe_failure(
                        exc=exc,
                        prefix="" if isinstance(exc, ValueError) else "Error creating project: ",
                        request_path=str(getattr(request, "path", "")),
                    ),
                    category=flash.CATEGORY_ERROR,
                )

        return _render_project_create_form(
            auth=auth, form_data=form_view, status_code=400, errors=errors
        )
    finally:
        try:
            db_session.close()
        except Exception:
            pass


#: The working pages a project's sidebar links to, by the name used in
#: ``/projects/{id}/open/{destination}``. Each opens the site-wide page
#: filtered to the project, so a person in a project reaches the pages
#: that can hold its data (PRJ-08) without knowing the registry's ids.
WORKSPACE_LINK_PATHS: Dict[str, str] = {
    "builds": "/builds",
    "runs": "/runs",
    "pipelines": "/pipelines",
    "test-catalog": "/test-catalog",
}


def handle_project_workspace_link(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/open/{destination}`` -- send the
        person to the site-wide Runs, Pipelines or Test catalog page
        filtered to this project. ``view``-permission gated; a project with
        no registry link opens the unfiltered page.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        destination = str(request.path_params.get("destination", "")).strip()
        target_path = WORKSPACE_LINK_PATHS.get(destination, None)
        raw_project_ref = request.path_params.get("project_id", None)
        project_id = _coerce_int(raw=raw_project_ref)
        if project_id is None:
            project_id = _legacy_id_for_registry_ref(db_session=db_session, ref=raw_project_ref)

        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        if target_path is None:
            rtnval = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("projects.project_detail", project_id=project_id),
                message="That page does not exist.",
                category=flash.CATEGORY_ERROR,
            )
            return rtnval

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="view",
            deny_redirect_url=_url_for_module.url_for("projects.project_list"),
            deny_message="You do not have permission to view this project.",
        )
        if deny_response is not None:
            return deny_response

        registry_project = _registry_project_for_legacy(
            db_session=db_session, legacy_proj_id=project_id,
        )
        location = target_path
        if registry_project is not None:
            location = target_path + "?project_id=" + str(registry_project.project_id)
        rtnval = RedirectResponse(url=location, status_code=302)
        _attach_session_to_response(response=rtnval, session=auth.session)
        return rtnval
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _count_or_none(value: Any) -> Optional[int]:
    """A count as an int, or ``None`` when it is not a number."""
    rtnval = value if isinstance(value, int) and not isinstance(value, bool) else None
    return rtnval


def _count_phrase(*, count: int, singular: str, plural: str) -> str:
    """``"1 repository"`` / ``"3 repositories"``."""
    rtnval = "{} {}".format(count, singular if count == 1 else plural)
    return rtnval


def describe_project_deletion(
        *,
        name: str,
        members: Optional[int],
        repositories: Optional[int],
        builds: Optional[int],
        tests: Optional[int]
    ) -> str:
    """
        The warning shown before a project is deleted: what goes with it, with the
        numbers the page knows (XC-15). A count that is not known or is zero is left out.

        :param name: The project's name.
        :param members: Members whose access goes.
        :param repositories: Repositories deleted with it.
        :param builds: Builds (and their artifacts) deleted with it.
        :param tests: Test jobs deleted with it.

        :returns: The message.
    """
    counted: List[str] = []
    for count, singular, plural in (
        (repositories, "repository", "repositories"),
        (builds, "build", "builds"),
        (tests, "test job", "test jobs"),
    ):
        if count is not None and count > 0:
            counted.append(_count_phrase(count=count, singular=singular, plural=plural))
    sentences = ['Delete the project "{}"?'.format(name)]
    if len(counted) > 0:
        sentences.append("This permanently deletes its {}.".format(", ".join(counted[:-1]) + (" and " if len(counted) > 1 else "") + counted[-1]))
    if members is not None and members > 0:
        sentences.append("{} lose{} access.".format(
            _count_phrase(count=members, singular="member", plural="members"), "s" if members == 1 else "",
        ))
    sentences.append(
        "Everything else in it goes too: infrastructure history, releases, watches and RPA specifications and jobs. This cannot be undone."
    )
    rtnval = " ".join(sentences)
    return rtnval


def handle_project_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}`` -- detail with summary
        cards (recent builds, recent tests, repos, members).
        ``view``-permission gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        raw_project_ref = request.path_params.get("project_id", None)
        project_id = _coerce_int(raw=raw_project_ref)
        if project_id is None:
            # A registry slug or UUID (how the REST API and the global
            # views name a project): show its web-UI page (PRJ-06).
            legacy_id = _legacy_id_for_registry_ref(db_session=db_session, ref=raw_project_ref)
            if legacy_id is not None:
                redirect = RedirectResponse(
                    url=_url_for_module.url_for("projects.project_detail", project_id=legacy_id),
                    status_code=302,
                )
                _attach_session_to_response(response=redirect, session=auth.session)
                return redirect

        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="view",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_list"
            ),
            deny_message=(
                "You do not have permission to view this project."
            ),
        )
        if deny_response is not None:
            return deny_response

        repository_manager = _build_repository_manager(
            db_session=db_session
        )
        build_manager = _build_build_manager(db_session=db_session)
        test_manager = _build_test_manager(db_session=db_session)

        repositories = repository_manager.list_repositories(
            project_id, limit=5
        ).repositories
        builds_page = build_manager.list_builds(
            project_id=project_id, limit=5
        )
        recent_builds = builds_page.builds
        tests_page = test_manager.list_jobs(
            project_id=project_id, limit=5
        )
        recent_tests = tests_page.jobs
        members = project_manager.list_members(
            project_id, limit=10
        ).members

        # Capability flags so the template only shows actions the
        # viewer can actually use (edit is admin-gated, delete is
        # owner-gated). A permission-probe failure means "no".
        try:
            can_edit = project_manager.check_permission(
                project_id, auth.user_id, "admin"
            )
        except Exception:
            can_edit = False
        try:
            can_delete = project_manager.check_permission(
                project_id, auth.user_id, "owner"
            )
        except Exception:
            can_delete = False

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.project_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["repositories"] = repositories
        context["recent_builds"] = recent_builds
        context["recent_tests"] = recent_tests
        context["members"] = members
        context["can_edit"] = can_edit
        context["can_delete"] = can_delete
        context["delete_warning"] = describe_project_deletion(
            name=project.name,
            members=_count_or_none(getattr(project, "member_count", None)),
            repositories=_count_or_none(getattr(project, "repository_count", None)),
            builds=_count_or_none(getattr(builds_page, "total", None)),
            tests=_count_or_none(getattr(tests_page, "total", None)),
        )
        context["registry_project"] = _registry_project_for_legacy(
            db_session=db_session, legacy_proj_id=project_id,
        )

        response = _render(
            template_name="projects/projects/detail.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_project_edit(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/edit`` /
        ``POST /projects/{project_id}/edit``. ``admin``-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )

        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="admin",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_detail", project_id=project_id
            ),
        )
        if deny_response is not None:
            return deny_response

        method = request.method.upper()

        # Populated on a POST that falls through to the re-render
        # so the form shows the submitted values rather than the
        # stale database copy.
        form_view: Optional[MultiFormView] = None
        errors: Dict[str, str] = {}

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)
            multi_form = _parse_form_multi(request=request)
            form_view = MultiFormView(data=multi_form)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "projects.project_edit", project_id=project_id
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            name = str(single_form.get("name", "")).strip()
            description = str(
                single_form.get("description", "")
            ).strip()
            metadata_str = str(single_form.get("metadata", "")).strip()

            try:
                metadata = _parse_metadata_json_or_default(
                    raw=metadata_str, default=None
                )
                update_request = _build_project_update_request(
                    name=name if len(name) > 0 else None,
                    description=(
                        description if len(description) > 0 else None
                    ),
                    metadata=metadata,
                )
                project_manager.update_project(
                    project_id, update_request, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "projects.project_detail",
                        project_id=project_id,
                    ),
                    message="Project updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except Exception as exc:
                errors = _project_form_errors(exc=exc)
                if len(errors) == 0:
                    flash.add_flash(
                        session=auth.session,
                        message=_describe_failure(
                            exc=exc,
                            prefix="" if isinstance(exc, ValueError) else "Error updating project: ",
                            request_path=str(getattr(request, "path", "")),
                        ),
                        category=flash.CATEGORY_ERROR,
                    )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.project_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["form_data"] = form_view
        context["errors"] = errors
        context["error_labels"] = PROJECT_FIELD_LABELS
        response = _render(
            template_name="projects/projects/edit.html",
            context=context,
            status_code=400 if form_view is not None else 200,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_project_delete(request: Request) -> Response:
    """
        ``POST /projects/{project_id}/delete``. ``owner``-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "projects.project_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if project_id is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for("projects.project_list"),
                message="Project not found.",
            )
            return response

        project_manager = _build_project_manager(db_session=db_session)

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="owner",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_detail", project_id=project_id
            ),
        )
        if deny_response is not None:
            return deny_response

        try:
            project_manager.delete_project(
                project_id,
                auth.user_id,
                related_rows_cleanup=_delete_project_rpa_rows,
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("projects.project_list"),
                message="Project deleted successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            # Stay on the project when it still exists: the message says
            # what to do (or carries a reference for an administrator).
            if getattr(exc, "error_code", None) == "PROJECT_NOT_FOUND":
                failure_url = _url_for_module.url_for("projects.project_list")
            else:
                failure_url = _url_for_module.url_for(
                    "projects.project_detail", project_id=project_id
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=failure_url,
                message=_describe_failure(
                    exc=exc,
                    prefix="Error deleting project: ",
                    request_path=str(getattr(request, "path", "")),
                ),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Handlers — members
# ---------------------------------------------------------------------------


def handle_member_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/members`` -- ``view``-gated.
        Also computes ``can_manage`` for the template.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="view",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_list"
            ),
            deny_message=(
                "You do not have permission to view this project."
            ),
        )
        if deny_response is not None:
            return deny_response

        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        members_result = project_manager.list_members(
            project_id, offset=offset, limit=params["per_page"]
        )
        members = members_result.members

        # Separate per-render permission probe (matches legacy
        # template's ``can_manage`` flag).
        try:
            can_manage = project_manager.check_permission(
                project_id, auth.user_id, "admin"
            )
        except Exception:
            can_manage = False

        total_pages = _total_pages_from_count(
            total=members_result.total,
            per_page=params["per_page"],
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.member_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["members"] = members
        context["can_manage"] = can_manage
        context["current_user_id"] = auth.user_id
        context["global_access"] = _list_global_project_access(
            db_session=db_session
        )
        context["role_descriptions"] = PROJECT_ROLE_DESCRIPTIONS
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["total"] = members_result.total

        response = _render(
            template_name="projects/members/list.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_member_add(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/members/add`` /
        ``POST /projects/{project_id}/members/add``.
        ``admin``-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="admin",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_detail", project_id=project_id
            ),
        )
        if deny_response is not None:
            return deny_response

        method = request.method.upper()
        form_data: Optional[MultiFormView] = None
        errors: Dict[str, str] = {}
        status_code = 200
        user_search = str(request.query_params.get("q", "") or "").strip()

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "projects.member_add", project_id=project_id
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            user_id_raw = single_form.get("user_id", None)
            user_id = _coerce_user_id(raw=user_id_raw)
            role_str = str(single_form.get("role", "viewer"))
            form_data = MultiFormView(data={
                "user_id": [str(user_id_raw or "")],
                "role": [role_str],
            })

            try:
                if user_id is None:
                    raise ProjectsFormError("Choose a user to add to the project.", field="user_id")
                role = _resolve_member_role(role_str=role_str)
                project_manager.add_member(
                    project_id, user_id, role, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "projects.member_list",
                        project_id=project_id,
                    ),
                    message="Member added successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except Exception as exc:
                status_code = 400
                errors = _field_errors_from(exc=exc, fields=_MEMBER_FORM_FIELDS)
                if len(errors) == 0:
                    flash.add_flash(
                        session=auth.session,
                        message=_describe_failure(exc=exc, prefix="Error adding member: ", request_path=str(getattr(request, "path", ""))),
                        category=flash.CATEGORY_ERROR,
                    )

        # GET, or POST that fell through.
        user_manager = _build_user_manager(db_session=db_session)
        current_members = project_manager.list_members(
            project_id, limit=1000
        ).members
        member_user_ids = set()
        for m in current_members:
            mid = getattr(m, "user_id", None)
            if mid is not None:
                member_user_ids.add(str(mid))

        # Only active accounts can be added; the search box narrows
        # the picker on deployments with many users.
        all_users_response = user_manager.list_users(
            limit=MEMBER_PICKER_LIMIT,
            search=user_search if len(user_search) > 0 else None,
            is_active=True,
        )
        all_users = getattr(all_users_response, "users", []) or []
        available_users = [
            u for u in all_users
            if str(getattr(u, "id", None)) not in member_user_ids
        ]

        roles = _enumerate_project_role_values()

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.member_add",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["available_users"] = available_users
        context["roles"] = roles
        context["role_descriptions"] = PROJECT_ROLE_DESCRIPTIONS
        context["form_data"] = form_data
        context["errors"] = errors
        context["error_labels"] = MEMBER_FIELD_LABELS
        context["user_search"] = user_search
        context["can_create_users"] = _has_permission(
            auth=auth, permission=USERS_WRITE_PERMISSION
        )
        response = _render(
            template_name="projects/members/add.html",
            context=context,
            status_code=status_code,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_member_edit(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/members/{user_id}/edit`` /
        ``POST /projects/{project_id}/members/{user_id}/edit``.
        ``admin``-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        target_user_id = _coerce_user_id(
            raw=request.path_params.get("user_id", None)
        )

        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="admin",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_detail", project_id=project_id
            ),
        )
        if deny_response is not None:
            return deny_response

        if target_user_id is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.member_list", project_id=project_id
                ),
                message="Member not found.",
            )
            return response

        method = request.method.upper()
        errors: Dict[str, str] = {}
        status_code = 200
        submitted_role: Optional[str] = None

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "projects.member_edit",
                    project_id=project_id,
                    user_id=target_user_id,
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            role_str = str(single_form.get("role", "viewer"))
            submitted_role = role_str

            try:
                role = _resolve_member_role(role_str=role_str)
                project_manager.update_member_role(
                    project_id, target_user_id, role, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "projects.member_list",
                        project_id=project_id,
                    ),
                    message="Member role updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except Exception as exc:
                status_code = 400
                errors = _field_errors_from(exc=exc, fields=_MEMBER_FORM_FIELDS)
                if len(errors) == 0:
                    flash.add_flash(
                        session=auth.session,
                        message=_describe_failure(exc=exc, prefix="Error updating member role: ", request_path=str(getattr(request, "path", ""))),
                        category=flash.CATEGORY_ERROR,
                    )

        # GET, or POST that fell through.
        members = project_manager.list_members(
            project_id, limit=1000
        ).members
        member = None
        for m in members:
            if str(getattr(m, "user_id", None)) == target_user_id:
                member = m
                break
        if member is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.member_list", project_id=project_id
                ),
                message="Member not found.",
            )
            return response

        roles = _enumerate_project_role_values()

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.member_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["member"] = member
        context["roles"] = roles
        context["role_descriptions"] = PROJECT_ROLE_DESCRIPTIONS
        context["errors"] = errors
        context["error_labels"] = MEMBER_FIELD_LABELS
        context["submitted_role"] = submitted_role
        response = _render(
            template_name="projects/members/edit.html",
            context=context,
            status_code=status_code,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_member_remove(request: Request) -> Response:
    """
        ``POST /projects/{project_id}/members/{user_id}/remove``.
        ``admin``-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        target_user_id = _coerce_user_id(
            raw=request.path_params.get("user_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "projects.project_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if project_id is None or target_user_id is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.project_list"
                ),
                message="Member not found.",
            )
            return response

        project_manager = _build_project_manager(db_session=db_session)

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="admin",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_detail", project_id=project_id
            ),
        )
        if deny_response is not None:
            return deny_response

        # Refuse self-removal: an admin removing themselves would
        # lock themselves out of the project mid-session. Both ids
        # are compared in canonical UUID form.
        if target_user_id == _coerce_user_id(raw=auth.user_id):
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.member_list", project_id=project_id
                ),
                message=(
                    "You cannot remove yourself from a project. "
                    "Ask another administrator to remove you."
                ),
                category=flash.CATEGORY_ERROR,
            )
            return response

        try:
            project_manager.remove_member(
                project_id, target_user_id, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.member_list", project_id=project_id
                ),
                message="Member removed successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.member_list", project_id=project_id
                ),
                message=_describe_failure(exc=exc, prefix="Error removing member: ", request_path=str(getattr(request, "path", ""))),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Site-shell wrapping
#
# Mirrors the /admin surface's strategy (config.routes
# _wrap_admin_handler_in_shell): the blueprint routes still own
# webworks dispatch for /projects/*, but every HTML render is
# re-emitted inside the shell document so the unified header +
# sidebar + theme render around the page. The templates extend the
# fragment-style projects/base.html; redirects (auth bounce to
# /login?next=..., post-POST redirects) pass through untouched.
# ---------------------------------------------------------------------------


_projects_ui_logger = logging.getLogger("pychestrate.ui.projects")


def _new_error_reference() -> str:
    """
        Mint a short reference that ties a message shown to a user to
        the log line recording the underlying exception.

        :returns: A 12-character hexadecimal reference.
    """
    rtnval = uuid.uuid4().hex[:12]
    return rtnval


def _log_unexpected_error(*, action: str, request_path: str) -> str:
    """
        Log the exception being handled (with its traceback) under a new
        reference. Call from inside an ``except`` block.

        :param action: Short description of what failed (handler name or
                       user action).
        :param request_path: Path of the request that failed.

        :returns: The reference to show the user.
    """
    reference = _new_error_reference()
    _projects_ui_logger.exception(
        "pychestrate.ui.projects.unexpected_error reference=%s action=%s path=%s",
        reference,
        action,
        request_path,
    )
    return reference


class ProjectsFormError(ValueError):
    """
        A problem with what the user submitted, raised by the projects
        route handlers themselves. Its message is written for the user
        and is shown as-is. ``field`` names the input it is about, so
        the form can show it next to that input.
    """

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        self.field: Optional[str] = field
        super().__init__(message)
        return


def _is_user_facing_error(*, exc: BaseException) -> bool:
    """
        Whether an exception's message was written for users.

        True for :class:`ProjectsFormError`, for the domain exceptions
        the core managers raise (classes defined under
        ``ccai.pychestrate.core.managers`` that carry an
        ``error_code``, such as ``ProjectHasActiveJobsError``) and for
        the RPA service's recoverable errors (``RpaError``). Anything
        else -- SQL errors, ``TypeError``, ``KeyError`` -- is an
        internal failure whose text must not reach the browser.

        :param exc: The exception being handled.

        :returns: ``True`` when the message may be shown to the user.
    """
    if isinstance(exc, ProjectsFormError):
        return True
    module_name = str(getattr(type(exc), "__module__", "") or "")
    # The RPA service's recoverable errors (RpaError and its subclasses)
    # are written for users too.
    rtnval = (
        (module_name.startswith("ccai.pychestrate.core.managers.") and hasattr(exc, "error_code"))
        or module_name == "ccai.pychestrate.webservice.orchestration.rpa.errors"
    )
    return rtnval


def _field_errors_from(
        *, exc: BaseException, fields: Any, aliases: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
    """
        The inline form error for a validation failure: the field the
        manager named (``exc.field``, renamed through ``aliases`` to the
        form's input name) with the error's message. Empty when the error
        is not user-facing or names no field the form shows an error
        for -- the caller then shows the message above the form, so it
        is never lost.

        :param exc: The exception being handled.
        :param fields: The input names the form renders errors for.
        :param aliases: ``{manager field (or prefix ending in "["): form
                        input name}``.

        :returns: ``{input name: message}`` for ``ui.field_error``.
    """
    rtnval: Dict[str, str] = {}
    field = getattr(exc, "field", None)
    if _is_user_facing_error(exc=exc) is True and isinstance(field, str) and len(field) > 0:
        name = field
        for source, target in (aliases or {}).items():
            if field == source or (source.endswith("[") and field.startswith(source)):
                name = target
                break
        if name in set(fields):
            rtnval[name] = getattr(exc, "message", None) or str(exc)
    return rtnval


def _describe_failure(
        *, exc: BaseException, prefix: str, request_path: str
    ) -> str:
    """
        Turn an exception caught by a handler into the flash message
        shown to the user. User-facing errors keep their message; any
        other exception is logged (with its traceback) under a new
        reference and replaced by a generic sentence carrying that
        reference, so SQL, Python and git error text never reaches the
        browser. Call from inside the ``except`` block.

        :param exc: The exception being handled.
        :param prefix: Message start, e.g. ``"Error deleting project: "``.
        :param request_path: Path of the failing request (logged).

        :returns: The flash message.
    """
    if _is_user_facing_error(exc=exc) is True:
        detail = getattr(exc, "message", None) or str(exc)
    else:
        reference = _log_unexpected_error(
            action=prefix.strip().rstrip(":"), request_path=request_path
        )
        detail = (
            "an unexpected problem occurred. If it keeps happening, give "
            "an administrator this reference: {}.".format(reference)
        )
        if len(prefix) == 0:
            detail = detail[0].upper() + detail[1:]
    rtnval = "{}{}".format(prefix, detail)
    return rtnval


def _render_unexpected_error_page(*, request: Request, action: str) -> Response:
    """
        Log the exception being handled and answer with the site
        shell's 500 page carrying the log reference. Falls back to the
        chromeless error page when the shell itself cannot render.

        :param request: The request whose handler failed.
        :param action: Handler name, recorded in the log line.

        :returns: A 500 :class:`Response`.
    """
    from ccai.pychestrate.webservice.webinterface.site_shell.error_pages import (  # noqa: E402
        render_error_response,
    )

    request_path = getattr(request, "path", "")
    reference = _log_unexpected_error(
        action=action, request_path=str(request_path)
    )
    message = (
        "This page could not be shown because of an unexpected problem. "
        "Try again, and if it keeps happening give an administrator this "
        "reference: {}.".format(reference)
    )
    try:
        rtnval = render_error_response(
            request=request, status_code=500, message=message
        )
    except Exception:
        _projects_ui_logger.exception(
            "pychestrate.ui.projects.error_page_failed reference=%s",
            reference,
        )
        rtnval = render_error_response(
            request=request,
            status_code=500,
            message=message,
            force_chromeless=True,
        )
    return rtnval


_DEFAULT_PROJECTS_PAGE_TITLE = "Pychestrate"


# Second path segment (/projects/<segment>) → tab label for the
# project-root pages. Anything else in that position is a project
# id, titled by the section table below.
_PROJECTS_ROOT_TITLE_LABELS: Dict[str, str] = {
    "dashboard": "Projects",
    "list": "All Projects",
    "create": "New Project",
}


# Third path segment (/projects/{id}/<segment>) → tab label for the
# project-scoped sections. Deeper paths inherit their section's
# label so e.g. /projects/7/builds/42/logs is titled "Builds".
_PROJECTS_SECTION_TITLE_LABELS: Dict[str, str] = {
    "edit": "Edit Project",
    "members": "Members",
    "repositories": "Repositories",
    "builds": "Builds",
    "infrastructure": "Infrastructure",
    "tests": "Tests",
    "releases": "Releases",
    "release-templates": "Release Templates",
    "calendar": "Calendar",
    "watches": "Watches",
}


def _resolve_projects_page_title(*, path: str) -> str:
    """
        Resolve the shell document ``<title>`` for a projects page
        from the request path. Sibling of the admin surface's
        ``_resolve_admin_page_title`` but segment-based, because
        project paths embed dynamic ids
        (``/projects/{id}/builds/...``) that a longest-prefix
        table cannot match.

        :param path: Request path (e.g. ``"/projects/7/builds"``).

        :returns: Title string (e.g. ``"Builds · Pychestrate"``).
    """
    if path is None or len(path) == 0:
        return _DEFAULT_PROJECTS_PAGE_TITLE

    segments = [
        segment for segment in path.split("/") if len(segment) > 0
    ]
    if len(segments) == 0 or segments[0] != "projects":
        return _DEFAULT_PROJECTS_PAGE_TITLE

    label = "Projects"
    if len(segments) >= 2:
        second = segments[1]
        if second in _PROJECTS_ROOT_TITLE_LABELS:
            label = _PROJECTS_ROOT_TITLE_LABELS[second]
        else:
            # Second segment is a project id.
            label = "Project"
            if len(segments) >= 3:
                section = segments[2]
                if section in _PROJECTS_SECTION_TITLE_LABELS:
                    label = _PROJECTS_SECTION_TITLE_LABELS[section]

    rtnval = "{} · {}".format(label, _DEFAULT_PROJECTS_PAGE_TITLE)
    return rtnval


def _wrap_projects_handler_in_shell(handler: Any) -> Any:
    """
        Wrap a projects-blueprint handler so its HTML response body
        renders as a content fragment inside the site shell's main
        slot.

        The handlers render templates extending the fragment-style
        ``projects/base.html`` -- no ``<html>/<head>/<body>``, no
        standalone chrome. This wrapper takes the rendered fragment
        and re-emits it inside the shell document so the unified
        header + sidebar render around it. The server-rendered
        fragment counts as mounted route content to the shell's
        landing-state check, so the client-side not-found view never
        fires on these pages.

        Non-HTML responses (the auth redirect to ``/login?next=``,
        post-POST redirects) pass through unchanged. The inner
        response's status code, cookies (the signed session cookie
        that carries consumed-flash state), and non-content-type
        headers are all carried onto the shell response.

        :param handler: The original handler taking a webworks
                        ``Request`` and returning a ``Response``.

        :returns: A new callable with the same signature that wraps
                  the response body in the shell document when the
                  response is an HTML render.
    """
    from ccai.pychestrate.webservice.webinterface.site_shell.shell_document import (  # noqa: E402
        render_shell_document,
    )

    def _wrapped(request: Request) -> Response:
        try:
            with _ui_profile_scope.request_profile_scope():
                inner = handler(request)
        except Exception:
            # An unexpected failure (a template error, a manager bug)
            # used to escape as the framework's bare JSON 500 with no
            # shell. Log it under a reference and show the shell's
            # error page with that reference instead.
            rtnval = _render_unexpected_error_page(
                request=request,
                action=getattr(handler, "__name__", "projects_handler"),
            )
            return rtnval
        not_found = _not_found_page_for(
            request=request, inner=inner, title_resolver=_resolve_projects_page_title
        )
        if not_found is not None:
            return not_found
        if isinstance(inner, HTMLResponse) is False:
            return inner

        try:
            inner_body_bytes = inner._body
        except AttributeError:
            return inner

        if inner_body_bytes is None:
            inner_html = ""
        else:
            try:
                inner_html = inner_body_bytes.decode("utf-8")
            except Exception:
                return inner

        request_path = getattr(request, "path", "")
        if isinstance(request_path, str) is False:
            request_path = ""
        page_title = _resolve_projects_page_title(path=request_path)
        inner_html, fragment_title = extract_fragment_title(html=inner_html)
        if fragment_title is not None:
            page_title = fragment_title
        rtnval = render_shell_document(
            request=request,
            page_title=page_title,
            content_html=inner_html,
        )
        try:
            rtnval._status_code = inner._status_code
        except AttributeError:
            pass

        # Carry the inner response's cookies across -- the session
        # cookie re-signed by _attach_session_to_response records
        # that queued flashes were consumed; dropping it would make
        # every flash reappear on the next page.
        try:
            inner_cookies = inner._cookies
        except AttributeError:
            inner_cookies = None
        if inner_cookies is not None:
            for cookie_name in inner_cookies:
                rtnval._cookies[cookie_name] = inner_cookies[cookie_name]

        # Carry any extra headers too, but keep the shell render's
        # own Content-Type.
        try:
            inner_headers = inner._headers
        except AttributeError:
            inner_headers = None
        if inner_headers is not None:
            for header_name, header_value in inner_headers.items():
                if header_name.lower() == "content-type":
                    continue
                rtnval._headers[header_name] = header_value

        return rtnval

    _wrapped.__name__ = "{}_in_shell".format(
        getattr(handler, "__name__", "projects_handler")
    )
    return _wrapped


class _ShellWrappingApp:
    """
        Registration adapter that wraps every attached handler in
        :func:`_wrap_projects_handler_in_shell` before delegating
        to the real webworks app. Passed to every per-feature
        ``register_*_routes`` function by
        :func:`register_projects_routes` so all 60+ projects routes
        get shell-wrapped without touching each sub-module.
    """

    def __init__(self, *, app: Any) -> None:
        self._app = app
        return

    def attach_route(
            self, path: str, methods: Optional[List[str]] = None
        ) -> Callable:
        """
            Mirror of ``app.attach_route``: returns a decorator
            that registers the shell-wrapped handler on the real
            app and hands the original handler back to the caller.

            :param path: Route pattern.
            :param methods: HTTP methods for the route.

            :returns: Decorator callable.
        """
        inner_decorator = self._app.attach_route(path, methods=methods)

        def decorator(handler: Any) -> Any:
            wrapped_handler = _wrap_projects_handler_in_shell(handler)
            inner_decorator(wrapped_handler)
            return handler

        return decorator


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "projects.list_root": handle_project_list,
    "projects.dashboard": handle_dashboard,
    "projects.project_list": handle_project_list,
    "projects.project_create": handle_project_create,
    "projects.project_detail": handle_project_detail,
    "projects.project_workspace_link": handle_project_workspace_link,
    "projects.project_edit": handle_project_edit,
    "projects.project_delete": handle_project_delete,
    "projects.member_list": handle_member_list,
    "projects.member_add": handle_member_add,
    "projects.member_edit": handle_member_edit,
    "projects.member_remove": handle_member_remove,
}


def register_projects_routes(*, app: Any) -> None:
    """
        Attach all projects web UI routes to a webworks app and
        register their endpoint names with the url_for shim.
        Cascades through every per-feature sub-module (F1 .. F5).

        Every handler is registered through the
        :class:`_ShellWrappingApp` adapter so its HTML renders are
        re-emitted inside the site shell document -- the /projects
        surface shares the unified header / sidebar / theme with
        the rest of the site instead of its retired standalone
        chrome.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.

        :returns: None.
    """
    shell_app = _ShellWrappingApp(app=app)

    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = PROJECTS_PATH + relative_path
        if full_path.endswith("/") and full_path != "/":
            full_path = (
                PROJECTS_PATH if relative_path == "/" else full_path
            )

        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        shell_app.attach_route(full_path, methods=list(methods))(handler)

    for endpoint_name, relative_path in _FUTURE_ENDPOINT_PATTERNS:
        full_path = PROJECTS_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )

    # F2 features -- repositories. Lazy-imported so this module
    # remains importable when a per-feature module fails to load.
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes_repositories import (  # noqa: E402
        register_repositories_routes,
    )
    register_repositories_routes(app=shell_app)

    # F3 features -- builds + infrastructure.
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes_builds import (  # noqa: E402
        register_builds_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes_infrastructure import (  # noqa: E402
        register_infrastructure_routes,
    )
    register_builds_routes(app=shell_app)
    register_infrastructure_routes(app=shell_app)

    # F4 features -- tests + releases.
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes_tests import (  # noqa: E402
        register_tests_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes_releases import (  # noqa: E402
        register_releases_routes,
    )
    register_tests_routes(app=shell_app)
    register_releases_routes(app=shell_app)

    # Project-scoped release templates UI.
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes_release_templates import (  # noqa: E402
        register_release_templates_routes,
    )
    register_release_templates_routes(app=shell_app)

    # Phase 11 -- RPA (6-rpa-orchestration) project pages.
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes_rpa import (  # noqa: E402
        register_rpa_routes,
    )
    register_rpa_routes(app=shell_app)

    # F5 features -- calendar + watches (final slice).
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes_calendar import (  # noqa: E402
        register_calendar_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes_watches import (  # noqa: E402
        register_watches_routes,
    )
    register_calendar_routes(app=shell_app)
    register_watches_routes(app=shell_app)

    return


__all__ = [
    "PROJECTS_PATH",
    "register_projects_routes",
    "_wrap_projects_handler_in_shell",
    "handle_dashboard",
    "handle_project_list",
    "handle_project_create",
    "handle_project_detail",
    "handle_project_edit",
    "handle_project_delete",
    "handle_member_list",
    "handle_member_add",
    "handle_member_edit",
    "handle_member_remove",
]
