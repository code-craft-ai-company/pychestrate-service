"""
.. module:: webinterface.blueprints.projects.routes_builds
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /projects/*/builds
               (F3 slice -- build management).

.. moduleauthor:: Code Craft AI LLC

The eight build routes served under the projects blueprint:

* ``GET  /projects/{project_id}/builds``                          -- build
                                                                     list
                                                                     (status
                                                                     / spec
                                                                     filter).
* ``GET  /projects/{project_id}/builds/specs``                    -- spec list.
* ``GET  /projects/{project_id}/builds/specs/create``             -- spec
                                                                     form
                                                                     (developer).
* ``POST /projects/{project_id}/builds/specs/create``             -- create
                                                                     spec.
* ``GET  /projects/{project_id}/builds/specs/{spec_id}``          -- spec
                                                                     detail.
* ``GET  /projects/{project_id}/builds/{build_id}``               -- build
                                                                     detail.
* ``GET  /projects/{project_id}/builds/{build_id}/logs``          -- build
                                                                     logs.
* ``POST /projects/{project_id}/builds/trigger``                  -- trigger
                                                                     (developer).
* ``POST /projects/{project_id}/builds/{build_id}/cancel``        -- cancel
                                                                     (developer).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Callable, Dict, List, Optional

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
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
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
from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes import (
    PROJECTS_PATH,
    _require_project_permission_or_redirect,
    _resolve_project_or_redirect,
)


_ROUTE_TABLE = (
    ("projects.build_list", "/{project_id}/builds", ("GET",)),
    (
        "projects.build_spec_list",
        "/{project_id}/builds/specs",
        ("GET",),
    ),
    (
        "projects.build_spec_create",
        "/{project_id}/builds/specs/create",
        ("GET", "POST"),
    ),
    (
        "projects.build_spec_detail",
        "/{project_id}/builds/specs/{spec_id}",
        ("GET",),
    ),
    (
        "projects.build_detail",
        "/{project_id}/builds/{build_id}",
        ("GET",),
    ),
    (
        "projects.build_logs",
        "/{project_id}/builds/{build_id}/logs",
        ("GET",),
    ),
    (
        "projects.build_trigger",
        "/{project_id}/builds/trigger",
        ("POST",),
    ),
    (
        "projects.build_cancel",
        "/{project_id}/builds/{build_id}/cancel",
        ("POST",),
    ),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams
# ---------------------------------------------------------------------------


def _build_project_manager(*, db_session: Any) -> Any:
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.project_access import (  # noqa: E402
        build_access_aware_project_manager,
    )
    rtnval = build_access_aware_project_manager(db_session=db_session)
    return rtnval


def _build_build_manager(*, db_session: Any) -> Any:
    from ccai.pychestrate.core.managers.build_manager import (  # noqa: E402
        BuildManager,
    )
    rtnval = BuildManager(db_session)
    return rtnval


def _build_repository_manager(*, db_session: Any) -> Any:
    from ccai.pychestrate.core.managers.repository_manager import (  # noqa: E402
        RepositoryManager,
    )
    rtnval = RepositoryManager(db_session)
    return rtnval


def _build_build_spec_create_request(
        *,
        name: str,
        repository_id: Optional[int],
        branch: str,
        steps: Any,
        environment: Dict[str, Any],
        timeout_minutes: int,
        description: str
    ) -> Any:
    from ccai.pychestrate.core.managers.build_manager import (  # noqa: E402
        BuildSpecCreateRequest,
    )
    rtnval = BuildSpecCreateRequest(
        name=name,
        repository_id=repository_id,
        branch=branch,
        steps=steps,
        environment=environment,
        timeout_minutes=timeout_minutes,
        description=description,
    )
    return rtnval


def _build_build_trigger_request(
        *,
        spec_id: Optional[int],
        branch: Optional[str],
        commit_sha: Optional[str]
    ) -> Any:
    from ccai.pychestrate.core.managers.build_manager import (  # noqa: E402
        BuildTriggerRequest,
    )
    rtnval = BuildTriggerRequest(
        spec_id=spec_id, branch=branch, commit_sha=commit_sha
    )
    return rtnval


def _resolve_job_status(*, value: Optional[str]) -> Any:
    """
        Resolve a ``status`` query-param string to the
        :class:`JobStatus` enum member the manager's filter
        expects (``list_builds`` dereferences ``status.value``,
        so a raw string would crash the query). ``None`` / empty
        / unknown values yield ``None`` (no filter).

        :param value: Raw query-param value.

        :returns: JobStatus member or ``None``.
    """
    if value is None:
        return None
    if len(value) == 0:
        return None
    from ccai.pychestrate.core.managers.build_manager import (  # noqa: E402
        JobStatus,
    )
    try:
        rtnval = JobStatus(value)
    except ValueError:
        return None
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
        *, request: Request, default_per_page: int = 20
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


def _parse_json_or_default(
        *, raw: str, default: Any
    ) -> Any:
    """
        Parse a JSON value from a textarea. Empty input yields
        ``default``. Bad JSON raises ValueError -- caller flashes
        the error and re-renders.
    """
    if raw is None or len(raw) == 0:
        return default
    try:
        rtnval = json.loads(raw)
        return rtnval
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Invalid JSON in steps or environment field."
        ) from exc


def _resolve_view_authorized_project(
        *, request: Request, auth: _AuthResolution
    ) -> Any:
    """
        The shared "load project, gate on view permission" head
        for read-only handlers in this module. Returns either
        the project (success) or a RedirectResponse (failure).
    """
    project_id = _coerce_int(
        raw=request.path_params.get("project_id", None)
    )
    project_manager = _build_project_manager(
        db_session=auth.db_session
    )
    resolved = _resolve_project_or_redirect(
        auth=auth,
        project_manager=project_manager,
        project_id=project_id,
    )
    if isinstance(resolved, RedirectResponse):
        return (project_id, project_manager, resolved)
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
        return (project_id, project_manager, deny_response)
    return (project_id, project_manager, project)


def _can_manage(
        *,
        project_manager: Any, project_id: int, user_id: str
    ) -> bool:
    """
        Computes the ``can_manage`` flag the templates branch
        on (developer-permission probe; treats exceptions as
        denial).
    """
    try:
        rtnval = project_manager.check_permission(
            project_id, user_id, "developer"
        )
    except Exception:
        rtnval = False
    return rtnval


def _resolve_owned_resource_or_redirect(
        *,
        auth: _AuthResolution,
        project_id: int,
        manager: Any,
        getter_name: str,
        target_id: Optional[int],
        list_endpoint: str,
        not_found_message: str
    ) -> Any:
    """
        Shared "look up + verify project_id match" helper for
        build / spec / job lookups. Mirrors
        routes_repositories._resolve_repository_or_redirect's
        shape.
    """
    if target_id is None:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for(
                list_endpoint, project_id=project_id
            ),
            message=not_found_message,
            category=flash.CATEGORY_ERROR,
        )
        return rtnval

    getter = getattr(manager, getter_name)
    target = getter(target_id)
    if target is None:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for(
                list_endpoint, project_id=project_id
            ),
            message=not_found_message,
            category=flash.CATEGORY_ERROR,
        )
        return rtnval
    if getattr(target, "project_id", None) != project_id:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for(
                list_endpoint, project_id=project_id
            ),
            message=not_found_message,
            category=flash.CATEGORY_ERROR,
        )
        return rtnval
    return target


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_build_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/builds``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(request=request, auth=auth)
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]
        status = (
            request.query_params.get("status", None) or None
        )
        spec_id = _coerce_int(
            raw=request.query_params.get("spec_id", None)
        )

        build_manager = _build_build_manager(db_session=db_session)
        builds_result = build_manager.list_builds(
            project_id=project_id,
            spec_id=spec_id,
            status=_resolve_job_status(value=status),
            offset=offset,
            limit=params["per_page"],
        )
        builds = builds_result.builds
        specs = build_manager.list_specs(project_id, limit=100).specs
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )
        total_pages = _total_pages_from_count(
            total=builds_result.total,
            per_page=params["per_page"],
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.build_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["builds"] = builds
        context["specs"] = specs
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["selected_status"] = status
        context["selected_spec_id"] = spec_id

        response = _render(
            template_name="projects/builds/list.html",
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


def handle_build_spec_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/builds/specs``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(request=request, auth=auth)
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        build_manager = _build_build_manager(db_session=db_session)
        specs_result = build_manager.list_specs(
            project_id, offset=offset, limit=params["per_page"]
        )
        specs = specs_result.specs
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )
        total_pages = _total_pages_from_count(
            total=specs_result.total,
            per_page=params["per_page"],
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.build_spec_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["specs"] = specs
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages

        response = _render(
            template_name="projects/builds/spec_list.html",
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


def _render_build_spec_create_form(
        *,
        auth: _AuthResolution,
        project: Any,
        repositories: List[Any],
        form_data: Optional[MultiFormView],
        status_code: int = 200
    ) -> HTMLResponse:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="projects.build_spec_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["project"] = project
    context["repositories"] = repositories
    context["form_data"] = form_data
    response = _render(
        template_name="projects/builds/spec_create.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(
        response=response, session=auth.session
    )
    return response


def handle_build_spec_create(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/builds/specs/create`` /
        ``POST .../specs/create``. ``developer``-gated.
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
            permission="developer",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_detail", project_id=project_id
            ),
        )
        if deny_response is not None:
            return deny_response

        repository_manager = _build_repository_manager(
            db_session=db_session
        )
        build_manager = _build_build_manager(db_session=db_session)
        method = request.method.upper()

        if method == "GET":
            repositories = repository_manager.list_repositories(
                project_id, limit=100
            ).repositories
            return _render_build_spec_create_form(
                auth=auth,
                project=project,
                repositories=repositories,
                form_data=None,
            )

        # POST
        single_form = _parse_form_or_empty(request=request)
        multi_form = _parse_form_multi(request=request)
        form_view = MultiFormView(data=multi_form)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "projects.build_spec_create",
                project_id=project_id,
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        repository_id = _coerce_int(
            raw=single_form.get("repository_id", None)
        )
        branch = str(single_form.get("branch", "main")).strip()
        if len(branch) == 0:
            branch = "main"
        steps_json = str(single_form.get("steps", "")).strip()
        environment_json = str(
            single_form.get("environment", "")
        ).strip()
        timeout_minutes = _coerce_int_with_default(
            raw=single_form.get("timeout_minutes", None),
            default=60,
        )
        description = str(
            single_form.get("description", "")
        ).strip()

        try:
            steps = _parse_json_or_default(raw=steps_json, default=[])
            environment = _parse_json_or_default(
                raw=environment_json, default={}
            )
            create_request = _build_build_spec_create_request(
                name=name,
                repository_id=repository_id,
                branch=branch,
                steps=steps,
                environment=(
                    environment
                    if isinstance(environment, dict)
                    else {}
                ),
                timeout_minutes=timeout_minutes,
                description=description,
            )
            spec = build_manager.create_spec(
                project_id, create_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.build_spec_detail",
                    project_id=project_id,
                    spec_id=spec.id,
                ),
                message=(
                    'Build specification "{}" created '
                    "successfully.".format(name)
                ),
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
                message="Error creating build specification: {}".format(
                    str(exc)
                ),
                category=flash.CATEGORY_ERROR,
            )

        repositories = repository_manager.list_repositories(
            project_id, limit=100
        ).repositories
        return _render_build_spec_create_form(
            auth=auth,
            project=project,
            repositories=repositories,
            form_data=form_view,
            status_code=400,
        )
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_build_spec_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/builds/specs/{spec_id}``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(request=request, auth=auth)
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        spec_id = _coerce_int(
            raw=request.path_params.get("spec_id", None)
        )
        build_manager = _build_build_manager(db_session=db_session)
        spec_or_redirect = _resolve_owned_resource_or_redirect(
            auth=auth,
            project_id=project_id,
            manager=build_manager,
            getter_name="get_spec",
            target_id=spec_id,
            list_endpoint="projects.build_spec_list",
            not_found_message="Build specification not found.",
        )
        if isinstance(spec_or_redirect, RedirectResponse):
            return spec_or_redirect
        spec = spec_or_redirect

        recent_builds = build_manager.list_builds(
            spec_id=spec_id, limit=10
        ).builds
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.build_spec_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["spec"] = spec
        context["recent_builds"] = recent_builds
        context["can_manage"] = can_manage

        response = _render(
            template_name="projects/builds/spec_detail.html",
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


def handle_build_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/builds/{build_id}``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(request=request, auth=auth)
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        build_id = _coerce_int(
            raw=request.path_params.get("build_id", None)
        )
        build_manager = _build_build_manager(db_session=db_session)
        build_or_redirect = _resolve_owned_resource_or_redirect(
            auth=auth,
            project_id=project_id,
            manager=build_manager,
            getter_name="get_build",
            target_id=build_id,
            list_endpoint="projects.build_list",
            not_found_message="Build not found.",
        )
        if isinstance(build_or_redirect, RedirectResponse):
            return build_or_redirect
        build = build_or_redirect

        artifacts = build_manager.list_artifacts(build_id).artifacts
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.build_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["build"] = build
        context["artifacts"] = artifacts
        context["can_manage"] = can_manage

        response = _render(
            template_name="projects/builds/detail.html",
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


def handle_build_logs(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/builds/{build_id}/logs``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(request=request, auth=auth)
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        build_id = _coerce_int(
            raw=request.path_params.get("build_id", None)
        )
        build_manager = _build_build_manager(db_session=db_session)
        build_or_redirect = _resolve_owned_resource_or_redirect(
            auth=auth,
            project_id=project_id,
            manager=build_manager,
            getter_name="get_build",
            target_id=build_id,
            list_endpoint="projects.build_list",
            not_found_message="Build not found.",
        )
        if isinstance(build_or_redirect, RedirectResponse):
            return build_or_redirect
        build = build_or_redirect

        step_name = request.query_params.get("step", None) or None
        logs = build_manager.get_build_logs(
            build_id, step_name=step_name
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.build_logs",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["build"] = build
        context["logs"] = logs
        context["selected_step"] = step_name

        response = _render(
            template_name="projects/builds/logs.html",
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


def handle_build_trigger(request: Request) -> Response:
    """
        ``POST /projects/{project_id}/builds/trigger``.
        ``developer``-gated.
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
                "projects.build_list", project_id=project_id
            )
            if project_id is not None
            else _url_for_module.url_for("projects.project_list"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if project_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.project_list"
                ),
                message="Project not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        project_manager = _build_project_manager(db_session=db_session)
        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="developer",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_detail", project_id=project_id
            ),
        )
        if deny_response is not None:
            return deny_response

        spec_id = _coerce_int(raw=single_form.get("spec_id", None))
        branch = str(single_form.get("branch", "")).strip()
        commit_sha = str(
            single_form.get("commit_sha", "")
        ).strip()

        build_manager = _build_build_manager(db_session=db_session)
        # The permission check above is for the project in the URL; the
        # spec id comes from the form, so confirm it belongs to that
        # project before triggering (otherwise a developer on one
        # project could trigger builds in any other).
        spec_or_redirect = _resolve_owned_resource_or_redirect(
            auth=auth,
            project_id=project_id,
            manager=build_manager,
            getter_name="get_spec",
            target_id=spec_id,
            list_endpoint="projects.build_list",
            not_found_message="Build specification not found.",
        )
        if isinstance(spec_or_redirect, RedirectResponse):
            return spec_or_redirect

        try:
            trigger_request = _build_build_trigger_request(
                spec_id=spec_id,
                branch=branch if len(branch) > 0 else None,
                commit_sha=(
                    commit_sha if len(commit_sha) > 0 else None
                ),
            )
            build = build_manager.trigger_build(
                trigger_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.build_detail",
                    project_id=project_id,
                    build_id=build.id,
                ),
                message="Build #{} triggered successfully.".format(
                    build.id
                ),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.build_list", project_id=project_id
                ),
                message="Error triggering build: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_build_cancel(request: Request) -> Response:
    """
        ``POST /projects/{project_id}/builds/{build_id}/cancel``.
        ``developer``-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        build_id = _coerce_int(
            raw=request.path_params.get("build_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "projects.build_list", project_id=project_id
            )
            if project_id is not None
            else _url_for_module.url_for("projects.project_list"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if project_id is None or build_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.project_list"
                ),
                message="Build not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        project_manager = _build_project_manager(db_session=db_session)
        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="developer",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_detail", project_id=project_id
            ),
        )
        if deny_response is not None:
            return deny_response

        detail_url = _url_for_module.url_for(
            "projects.build_detail",
            project_id=project_id,
            build_id=build_id,
        )

        build_manager = _build_build_manager(db_session=db_session)
        # Cancel only builds that belong to the project in the URL, the
        # one the permission check above was evaluated for.
        build_or_redirect = _resolve_owned_resource_or_redirect(
            auth=auth,
            project_id=project_id,
            manager=build_manager,
            getter_name="get_build",
            target_id=build_id,
            list_endpoint="projects.build_list",
            not_found_message="Build not found.",
        )
        if isinstance(build_or_redirect, RedirectResponse):
            return build_or_redirect

        try:
            build_manager.cancel_build(build_id, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=detail_url,
                message="Build cancelled successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=detail_url,
                message="Error cancelling build: {}".format(str(exc)),
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
    "projects.build_list": handle_build_list,
    "projects.build_spec_list": handle_build_spec_list,
    "projects.build_spec_create": handle_build_spec_create,
    "projects.build_spec_detail": handle_build_spec_detail,
    "projects.build_detail": handle_build_detail,
    "projects.build_logs": handle_build_logs,
    "projects.build_trigger": handle_build_trigger,
    "projects.build_cancel": handle_build_cancel,
}


def register_builds_routes(*, app: Any) -> None:
    """
        Attach the F3 build routes to a webworks app.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = PROJECTS_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        app.attach_route(full_path, methods=list(methods))(handler)
    return


__all__ = [
    "register_builds_routes",
    "handle_build_list",
    "handle_build_spec_list",
    "handle_build_spec_create",
    "handle_build_spec_detail",
    "handle_build_detail",
    "handle_build_logs",
    "handle_build_trigger",
    "handle_build_cancel",
]
