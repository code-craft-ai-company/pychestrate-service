"""
.. module:: webinterface.blueprints.projects.routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /projects (F1
               slice -- dashboard + project core + members).

.. moduleauthor:: Automation Mojo LLC

The flask projects blueprint at
``webinterface/blueprints/projects/endpoints.py`` (2,529 LOC,
53 routes) is being ported to webworks across multiple PRs.
This first slice (F1) lands the dashboard + the project-core
CRUD + the members surface:

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

Pre-registers the URL patterns for the remaining F2/F3/F4/F5
endpoints (repositories / builds / infrastructure / tests /
releases / calendar / watches) so the dashboard sidebar's
``url_for(...)`` calls resolve at template render time before
those handlers ship.

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

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Callable, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from automojo.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    csrf,
    flash,
    url_for as _url_for_module,
)
from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (
    MultiFormView,
    _AuthResolution,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
)


PROJECTS_PATH = "/projects"


_ROUTE_TABLE = (
    ("projects.dashboard_root", "/", ("GET",)),
    ("projects.dashboard", "/dashboard", ("GET",)),
    ("projects.project_list", "/list", ("GET",)),
    ("projects.project_create", "/create", ("GET", "POST")),
    ("projects.project_detail", "/{project_id}", ("GET",)),
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


# Pre-register URL patterns for F2/F3/F4/F5. Each future PR
# moves the entry from this table into ``_ROUTE_TABLE`` and
# lands the handler at the same time.
_FUTURE_ENDPOINT_PATTERNS = (
    # F4 -- tests + releases
    ("projects.test_job_list", "/{project_id}/tests"),
    ("projects.test_spec_list", "/{project_id}/tests/specs"),
    (
        "projects.test_spec_detail",
        "/{project_id}/tests/specs/{spec_id}",
    ),
    (
        "projects.test_job_detail",
        "/{project_id}/tests/{job_id}",
    ),
    (
        "projects.test_job_logs",
        "/{project_id}/tests/{job_id}/logs",
    ),
    ("projects.release_list", "/{project_id}/releases"),
    (
        "projects.release_detail",
        "/{project_id}/releases/{release_id}",
    ),
    (
        "projects.pipeline_list",
        "/{project_id}/releases/pipelines",
    ),
    (
        "projects.pipeline_detail",
        "/{project_id}/releases/pipelines/{pipeline_id}",
    ),
    (
        "projects.channel_list",
        "/{project_id}/releases/channels",
    ),
    (
        "projects.schedule_list",
        "/{project_id}/releases/schedules",
    ),
    # F5 -- calendar + watches
    ("projects.calendar_view", "/{project_id}/calendar"),
    (
        "projects.calendar_event_list",
        "/{project_id}/calendar/events",
    ),
    (
        "projects.calendar_event_detail",
        "/{project_id}/calendar/events/{event_id}",
    ),
    ("projects.watch_list", "/{project_id}/watches"),
    (
        "projects.watch_create",
        "/{project_id}/watches/create",
    ),
    (
        "projects.watch_detail",
        "/{project_id}/watches/{watch_id}",
    ),
    (
        "projects.watch_edit",
        "/{project_id}/watches/{watch_id}/edit",
    ),
    (
        "projects.watch_delete",
        "/{project_id}/watches/{watch_id}/delete",
    ),
    (
        "projects.watch_enable",
        "/{project_id}/watches/{watch_id}/enable",
    ),
    (
        "projects.watch_disable",
        "/{project_id}/watches/{watch_id}/disable",
    ),
    (
        "projects.watch_test",
        "/{project_id}/watches/{watch_id}/test",
    ),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _build_project_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ProjectManager`. Lazy-imports.

        :param db_session: Open SQLAlchemy session.

        :returns: ProjectManager instance.
    """
    from automojo.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectManager,
    )
    rtnval = ProjectManager(db_session)
    return rtnval


def _build_user_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`UserManager`. Lazy-imports.
    """
    from automojo.pychestrate.core.managers.user_manager import (  # noqa: E402
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
    from automojo.pychestrate.core.managers.repository_manager import (  # noqa: E402
        RepositoryManager,
    )
    rtnval = RepositoryManager(db_session)
    return rtnval


def _build_build_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`BuildManager` for the project_detail
        recent-builds summary. Lazy-imports.
    """
    from automojo.pychestrate.core.managers.build_manager import (  # noqa: E402
        BuildManager,
    )
    rtnval = BuildManager(db_session)
    return rtnval


def _build_test_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`TestManager` for the project_detail
        recent-tests summary. Lazy-imports.
    """
    from automojo.pychestrate.core.managers.test_manager import (  # noqa: E402
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
    from automojo.pychestrate.core.managers.project_manager import (  # noqa: E402
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
    from automojo.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectUpdateRequest,
    )
    rtnval = ProjectUpdateRequest(
        name=name, description=description, metadata=metadata
    )
    return rtnval


def _resolve_project_role(*, role_str: str) -> Any:
    """
        Resolve a string to the :class:`ProjectRole` enum value.
        Raises ValueError on unknown.
    """
    from automojo.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectRole,
    )
    rtnval = ProjectRole(role_str)
    return rtnval


def _enumerate_project_role_values() -> List[str]:
    """
        Return every :class:`ProjectRole` value as a string. For
        the role-selector <select> dropdown.
    """
    try:
        from automojo.pychestrate.core.managers.project_manager import (  # noqa: E402
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


def _approximate_total_pages(
        *, page: int, per_page: int, returned_count: int
    ) -> int:
    if returned_count < per_page:
        if page == 1:
            return 1
        return page
    return page + 1


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
        raise ValueError("Invalid JSON in metadata field.") from exc
    if not isinstance(parsed, dict):
        raise ValueError(
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
        Mirror the legacy flask
        ``@project_permission_required(permission)`` decorator.
        Calls :meth:`ProjectManager.check_permission` (3-arg
        signature: project_id, user_id, permission) and either
        returns ``None`` (allowed) or a redirect with an error
        flash queued on the session (denied).

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
    rtnval = RedirectResponse(url=deny_redirect_url, status_code=302)
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
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("projects.project_list"),
            message="Project not found.",
            category=flash.CATEGORY_ERROR,
        )
        return rtnval

    project = project_manager.get_project(project_id)
    if project is None:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("projects.project_list"),
            message="Project not found.",
            category=flash.CATEGORY_ERROR,
        )
        return rtnval
    return project


# ---------------------------------------------------------------------------
# Handlers — dashboard
# ---------------------------------------------------------------------------


def handle_dashboard(request: Request) -> Response:
    """
        ``GET /projects/`` and ``/projects/dashboard``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_manager = _build_project_manager(db_session=db_session)
        projects = project_manager.list_projects(
            auth.user_id, limit=10
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.dashboard",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["projects"] = projects
        context["recent_builds"] = []
        context["recent_tests"] = []
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


def handle_project_list(request: Request) -> Response:
    """
        ``GET /projects/list``.
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
        projects = project_manager.list_projects(
            user_id=auth.user_id,
            offset=offset,
            limit=params["per_page"],
            search=search if len(search) > 0 else None,
        )

        total_pages = _approximate_total_pages(
            page=params["page"],
            per_page=params["per_page"],
            returned_count=len(projects),
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.project_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["projects"] = projects
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
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


def _render_project_create_form(
        *, auth: _AuthResolution,
        form_data: Optional[MultiFormView],
        status_code: int = 200
    ) -> HTMLResponse:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="projects.project_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["form_data"] = form_data
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
        except ValueError as exc:
            flash.add_flash(
                session=auth.session,
                message=str(exc),
                category=flash.CATEGORY_ERROR,
            )
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message="Error creating project: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )

        return _render_project_create_form(
            auth=auth, form_data=form_view, status_code=400
        )
    finally:
        try:
            db_session.close()
        except Exception:
            pass


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

        repository_manager = _build_repository_manager(
            db_session=db_session
        )
        build_manager = _build_build_manager(db_session=db_session)
        test_manager = _build_test_manager(db_session=db_session)

        repositories = repository_manager.list_repositories(
            project_id, limit=5
        )
        recent_builds = build_manager.list_builds(
            project_id=project_id, limit=5
        )
        recent_tests = test_manager.list_jobs(
            project_id=project_id, limit=5
        )
        members = project_manager.list_members(
            project_id, limit=10
        )

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

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)

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
            except ValueError as exc:
                flash.add_flash(
                    session=auth.session,
                    message=str(exc),
                    category=flash.CATEGORY_ERROR,
                )
            except Exception as exc:
                flash.add_flash(
                    session=auth.session,
                    message="Error updating project: {}".format(
                        str(exc)
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
        response = _render(
            template_name="projects/projects/edit.html",
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
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("projects.project_list"),
                message="Project not found.",
                category=flash.CATEGORY_ERROR,
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
            project_manager.delete_project(project_id, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("projects.project_list"),
                message="Project deleted successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("projects.project_list"),
                message="Error deleting project: {}".format(str(exc)),
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

        members = project_manager.list_members(
            project_id, offset=offset, limit=params["per_page"]
        )

        # Separate per-render permission probe (matches legacy
        # template's ``can_manage`` flag).
        try:
            can_manage = project_manager.check_permission(
                project_id, auth.user_id, "admin"
            )
        except Exception:
            can_manage = False

        total_pages = _approximate_total_pages(
            page=params["page"],
            per_page=params["per_page"],
            returned_count=len(members),
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
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages

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
            user_id = _coerce_int(raw=user_id_raw)
            role_str = str(single_form.get("role", "viewer"))

            try:
                if user_id is None:
                    raise ValueError("user_id is required.")
                role = _resolve_project_role(role_str=role_str)
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
                flash.add_flash(
                    session=auth.session,
                    message="Error adding member: {}".format(str(exc)),
                    category=flash.CATEGORY_ERROR,
                )

        # GET, or POST that fell through.
        user_manager = _build_user_manager(db_session=db_session)
        current_members = project_manager.list_members(
            project_id, limit=1000
        )
        member_user_ids = set()
        for m in current_members:
            mid = getattr(m, "user_id", None)
            if mid is not None:
                member_user_ids.add(mid)

        all_users_response = user_manager.list_users(limit=1000)
        all_users = getattr(all_users_response, "users", []) or []
        available_users = [
            u for u in all_users
            if getattr(u, "id", None) not in member_user_ids
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
        response = _render(
            template_name="projects/members/add.html",
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
        target_user_id = _coerce_int(
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
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.member_list", project_id=project_id
                ),
                message="Member not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        method = request.method.upper()

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

            try:
                role = _resolve_project_role(role_str=role_str)
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
                flash.add_flash(
                    session=auth.session,
                    message="Error updating member role: {}".format(
                        str(exc)
                    ),
                    category=flash.CATEGORY_ERROR,
                )

        # GET, or POST that fell through.
        members = project_manager.list_members(project_id, limit=1000)
        member = None
        for m in members:
            if getattr(m, "user_id", None) == target_user_id:
                member = m
                break
        if member is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.member_list", project_id=project_id
                ),
                message="Member not found.",
                category=flash.CATEGORY_ERROR,
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
        response = _render(
            template_name="projects/members/edit.html",
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
        target_user_id = _coerce_int(
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
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.project_list"
                ),
                message="Member not found.",
                category=flash.CATEGORY_ERROR,
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
                message="Error removing member: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "projects.dashboard_root": handle_dashboard,
    "projects.dashboard": handle_dashboard,
    "projects.project_list": handle_project_list,
    "projects.project_create": handle_project_create,
    "projects.project_detail": handle_project_detail,
    "projects.project_edit": handle_project_edit,
    "projects.project_delete": handle_project_delete,
    "projects.member_list": handle_member_list,
    "projects.member_add": handle_member_add,
    "projects.member_edit": handle_member_edit,
    "projects.member_remove": handle_member_remove,
}


def register_projects_routes(*, app: Any) -> None:
    """
        Attach the F1 projects routes to a webworks app and
        register their endpoint names with the url_for shim.
        Also pre-registers the URL patterns for F2/F3/F4/F5
        endpoints so the dashboard sidebar's url_for() calls
        resolve before those handlers ship.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.

        :returns: None.
    """
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
        app.attach_route(full_path, methods=list(methods))(handler)

    for endpoint_name, relative_path in _FUTURE_ENDPOINT_PATTERNS:
        full_path = PROJECTS_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )

    # F2 features -- repositories. Lazy-imported so this module
    # remains importable when a per-feature module fails to load.
    from automojo.pychestrate.webservice.webinterface.blueprints.projects.routes_repositories import (  # noqa: E402
        register_repositories_routes,
    )
    register_repositories_routes(app=app)

    # F3 features -- builds + infrastructure.
    from automojo.pychestrate.webservice.webinterface.blueprints.projects.routes_builds import (  # noqa: E402
        register_builds_routes,
    )
    from automojo.pychestrate.webservice.webinterface.blueprints.projects.routes_infrastructure import (  # noqa: E402
        register_infrastructure_routes,
    )
    register_builds_routes(app=app)
    register_infrastructure_routes(app=app)

    return


__all__ = [
    "PROJECTS_PATH",
    "register_projects_routes",
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
