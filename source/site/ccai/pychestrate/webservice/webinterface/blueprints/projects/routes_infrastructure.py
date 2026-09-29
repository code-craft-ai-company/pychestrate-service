"""
.. module:: webinterface.blueprints.projects.routes_infrastructure
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /projects/*/infrastructure
               (F3 slice -- read-only infrastructure viewer).

.. moduleauthor:: Code Craft AI LLC

The five infrastructure routes served under the projects
blueprint. All read-only -- this blueprint does not expose
form-based creation / triggering through the UI
(infrastructure jobs are produced by the build pipeline or via
the REST API).

* ``GET /projects/{project_id}/infrastructure``                   -- job
                                                                     list
                                                                     (status
                                                                     /
                                                                     spec
                                                                     filter).
* ``GET /projects/{project_id}/infrastructure/specs``             -- spec
                                                                     list.
* ``GET /projects/{project_id}/infrastructure/specs/{spec_id}``   -- spec
                                                                     detail.
* ``GET /projects/{project_id}/infrastructure/{job_id}``          -- job
                                                                     detail.
* ``GET /projects/{project_id}/infrastructure/{job_id}/logs``     -- job
                                                                     logs.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.webinterface.foundation import (
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    _AuthResolution,
    _attach_session_to_response,
    _build_default_template_context,
    _not_found_redirect,
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
    (
        "projects.infra_job_list",
        "/{project_id}/infrastructure",
        ("GET",),
    ),
    (
        "projects.infra_spec_list",
        "/{project_id}/infrastructure/specs",
        ("GET",),
    ),
    (
        "projects.infra_spec_detail",
        "/{project_id}/infrastructure/specs/{spec_id}",
        ("GET",),
    ),
    (
        "projects.infra_job_detail",
        "/{project_id}/infrastructure/{job_id}",
        ("GET",),
    ),
    (
        "projects.infra_job_logs",
        "/{project_id}/infrastructure/{job_id}/logs",
        ("GET",),
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


def _resolve_job_status(*, value: Optional[str]) -> Any:
    """
        Resolve a ``status`` query-param string to the
        :class:`JobStatus` enum member the manager's filter
        expects (``list_jobs`` dereferences ``status.value``, so
        a raw string would crash the query). ``None`` / empty /
        unknown values yield ``None`` (no filter).

        :param value: Raw query-param value.

        :returns: JobStatus member or ``None``.
    """
    if value is None:
        return None
    if len(value) == 0:
        return None
    from ccai.pychestrate.core.managers.infrastructure_manager import (  # noqa: E402
        JobStatus,
    )
    try:
        rtnval = JobStatus(value)
    except ValueError:
        return None
    return rtnval


def _build_infra_manager(*, db_session: Any) -> Any:
    from ccai.pychestrate.core.managers.infrastructure_manager import (  # noqa: E402
        InfrastructureManager,
    )
    rtnval = InfrastructureManager(db_session)
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


def _resolve_view_authorized_project(
        *, request: Request, auth: _AuthResolution
    ) -> Any:
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
    if target_id is None:
        rtnval = _not_found_redirect(
            session=auth.session,
            url=_url_for_module.url_for(
                list_endpoint, project_id=project_id
            ),
            message=not_found_message,
        )
        return rtnval

    getter = getattr(manager, getter_name)
    target = getter(target_id)
    if target is None:
        rtnval = _not_found_redirect(
            session=auth.session,
            url=_url_for_module.url_for(
                list_endpoint, project_id=project_id
            ),
            message=not_found_message,
        )
        return rtnval
    if getattr(target, "project_id", None) != project_id:
        rtnval = _not_found_redirect(
            session=auth.session,
            url=_url_for_module.url_for(
                list_endpoint, project_id=project_id
            ),
            message=not_found_message,
        )
        return rtnval
    return target


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_infra_job_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/infrastructure`` -- job list
        with ``status`` / ``spec_id`` filters.
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

        infra_manager = _build_infra_manager(db_session=db_session)
        jobs_result = infra_manager.list_jobs(
            project_id=project_id,
            spec_id=spec_id,
            status=_resolve_job_status(value=status),
            offset=offset,
            limit=params["per_page"],
        )
        jobs = jobs_result.jobs
        specs = infra_manager.list_specs(project_id, limit=100).specs
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )
        total_pages = _total_pages_from_count(
            total=jobs_result.total,
            per_page=params["per_page"],
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.infra_job_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["jobs"] = jobs
        context["specs"] = specs
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["total"] = jobs_result.total
        context["selected_status"] = status
        context["selected_spec_id"] = spec_id

        response = _render(
            template_name="projects/infrastructure/list.html",
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


def handle_infra_spec_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/infrastructure/specs``.
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

        infra_manager = _build_infra_manager(db_session=db_session)
        specs_result = infra_manager.list_specs(
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
            request_endpoint="projects.infra_spec_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["specs"] = specs
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["total"] = specs_result.total

        response = _render(
            template_name="projects/infrastructure/spec_list.html",
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


def handle_infra_spec_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/infrastructure/specs/{spec_id}``.
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
        infra_manager = _build_infra_manager(db_session=db_session)
        spec_or_redirect = _resolve_owned_resource_or_redirect(
            auth=auth,
            project_id=project_id,
            manager=infra_manager,
            getter_name="get_spec",
            target_id=spec_id,
            list_endpoint="projects.infra_spec_list",
            not_found_message=(
                "Infrastructure specification not found."
            ),
        )
        if isinstance(spec_or_redirect, RedirectResponse):
            return spec_or_redirect
        spec = spec_or_redirect

        recent_jobs = infra_manager.list_jobs(
            spec_id=spec_id, limit=10
        ).jobs
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.infra_spec_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["spec"] = spec
        context["recent_jobs"] = recent_jobs
        context["can_manage"] = can_manage

        response = _render(
            template_name="projects/infrastructure/spec_detail.html",
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


def handle_infra_job_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/infrastructure/{job_id}``.
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

        job_id = _coerce_int(
            raw=request.path_params.get("job_id", None)
        )
        infra_manager = _build_infra_manager(db_session=db_session)
        job_or_redirect = _resolve_owned_resource_or_redirect(
            auth=auth,
            project_id=project_id,
            manager=infra_manager,
            getter_name="get_job",
            target_id=job_id,
            list_endpoint="projects.infra_job_list",
            not_found_message="Infrastructure job not found.",
        )
        if isinstance(job_or_redirect, RedirectResponse):
            return job_or_redirect
        job = job_or_redirect

        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.infra_job_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["job"] = job
        context["can_manage"] = can_manage

        response = _render(
            template_name="projects/infrastructure/detail.html",
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


def handle_infra_job_logs(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/infrastructure/{job_id}/logs``.
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

        job_id = _coerce_int(
            raw=request.path_params.get("job_id", None)
        )
        infra_manager = _build_infra_manager(db_session=db_session)
        job_or_redirect = _resolve_owned_resource_or_redirect(
            auth=auth,
            project_id=project_id,
            manager=infra_manager,
            getter_name="get_job",
            target_id=job_id,
            list_endpoint="projects.infra_job_list",
            not_found_message="Infrastructure job not found.",
        )
        if isinstance(job_or_redirect, RedirectResponse):
            return job_or_redirect
        job = job_or_redirect

        logs = infra_manager.get_job_logs(job_id)

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.infra_job_logs",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["job"] = job
        context["logs"] = logs

        response = _render(
            template_name="projects/infrastructure/logs.html",
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
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "projects.infra_job_list": handle_infra_job_list,
    "projects.infra_spec_list": handle_infra_spec_list,
    "projects.infra_spec_detail": handle_infra_spec_detail,
    "projects.infra_job_detail": handle_infra_job_detail,
    "projects.infra_job_logs": handle_infra_job_logs,
}


def register_infrastructure_routes(*, app: Any) -> None:
    """
        Attach the F3 infrastructure routes to a webworks app.
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
    "register_infrastructure_routes",
    "handle_infra_job_list",
    "handle_infra_spec_list",
    "handle_infra_spec_detail",
    "handle_infra_job_detail",
    "handle_infra_job_logs",
]
