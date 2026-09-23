"""
.. module:: webinterface.blueprints.projects.routes_releases
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /projects/*/releases
               (F4 slice -- read-only release viewer).

.. moduleauthor:: Code Craft AI LLC

The six release routes served under the projects blueprint.
All read-only -- release lifecycle
(triggering / promoting) goes through the build pipeline +
REST API, not the consumer UI.

* ``GET /projects/{project_id}/releases``                          -- list
                                                                      (status
                                                                      /
                                                                      channel
                                                                      filter).
* ``GET /projects/{project_id}/releases/{release_id}``             -- detail
                                                                      with
                                                                      artifacts.
* ``GET /projects/{project_id}/releases/pipelines``                -- pipeline
                                                                      list.
* ``GET /projects/{project_id}/releases/pipelines/{pipeline_id}``  -- pipeline
                                                                      detail.
* ``GET /projects/{project_id}/releases/channels``                 -- channel
                                                                      list.
* ``GET /projects/{project_id}/releases/schedules``                -- schedule
                                                                      list.
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
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    _AuthResolution,
    _attach_session_to_response,
    _build_default_template_context,
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
    ("projects.release_list", "/{project_id}/releases", ("GET",)),
    (
        "projects.release_detail",
        "/{project_id}/releases/{release_id}",
        ("GET",),
    ),
    (
        "projects.pipeline_list",
        "/{project_id}/releases/pipelines",
        ("GET",),
    ),
    (
        "projects.pipeline_detail",
        "/{project_id}/releases/pipelines/{pipeline_id}",
        ("GET",),
    ),
    (
        "projects.channel_list",
        "/{project_id}/releases/channels",
        ("GET",),
    ),
    (
        "projects.schedule_list",
        "/{project_id}/releases/schedules",
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


def _resolve_release_status(*, value: Optional[str]) -> Any:
    """
        Resolve a ``status`` query-param string to the
        :class:`ReleaseStatus` enum member the manager's filter
        expects (``list_releases`` dereferences ``status.value``,
        so a raw string would crash the query). ``None`` / empty
        / unknown values yield ``None`` (no filter).

        :param value: Raw query-param value.

        :returns: ReleaseStatus member or ``None``.
    """
    if value is None:
        return None
    if len(value) == 0:
        return None
    from ccai.pychestrate.core.managers.release_manager import (  # noqa: E402
        ReleaseStatus,
    )
    try:
        rtnval = ReleaseStatus(value)
    except ValueError:
        return None
    return rtnval


def _build_release_manager(*, db_session: Any) -> Any:
    from ccai.pychestrate.core.managers.release_manager import (  # noqa: E402
        ReleaseManager,
    )
    rtnval = ReleaseManager(db_session)
    return rtnval


def _build_release_template_manager(*, db_session: Any) -> Any:
    from ccai.pychestrate.core.managers.release_template_manager import (  # noqa: E402
        ReleaseTemplateManager,
    )
    rtnval = ReleaseTemplateManager(db_session=db_session)
    return rtnval


def _build_repository_manager(*, db_session: Any) -> Any:
    from ccai.pychestrate.core.managers.repository_manager import (  # noqa: E402
        RepositoryManager,
    )
    rtnval = RepositoryManager(db_session)
    return rtnval


def _release_provenance(
        *, db_session: Any, project_id: int, metadata: Any
    ) -> Optional[Dict[str, Any]]:
    """
        Describe where a release came from, for the release page.

        Releases created from a release template carry the template's
        id (and, since templates can be renamed or deleted, its name)
        and the defaults it contributed -- channel, repositories,
        pipeline and schedule -- in their metadata. Repository ids are
        resolved to names; a template that no longer exists is shown by
        its recorded name without a link.

        :param db_session: Open SQLAlchemy session.
        :param project_id: The release's project.
        :param metadata: ``ReleaseResponse.metadata``.

        :returns: A dict for the template, or ``None`` when the release
                  was not created from a template.
    """
    if not isinstance(metadata, dict):
        return None
    template_id = metadata.get("template_id", None)
    if template_id is None:
        return None

    template = None
    try:
        template_manager = _build_release_template_manager(db_session=db_session)
        template = template_manager.get(int(template_id))
    except Exception:
        template = None
    if template is not None and template.project_id != project_id:
        template = None

    repository_names: Dict[int, str] = {}
    try:
        repository_manager = _build_repository_manager(db_session=db_session)
        for repository in repository_manager.list_repositories(project_id, limit=500).repositories:
            repository_names[int(repository.id)] = str(repository.name)
    except Exception:
        repository_names = {}

    repositories: List[Dict[str, Any]] = []
    for raw_id in metadata.get("repository_ids", None) or []:
        try:
            repo_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        repositories.append({"id": repo_id, "name": repository_names.get(repo_id, None)})

    pipeline = metadata.get("pipeline", None)
    schedule = metadata.get("schedule", None)
    rtnval = {
        "template_id": template.id if template is not None else None,
        "template_name": (
            template.name if template is not None
            else str(metadata.get("template_name", "") or "")
        ),
        "channel": metadata.get("channel", None),
        "version_pattern": metadata.get("version_pattern", None),
        "repositories": repositories,
        "pipeline_json": json.dumps(pipeline, indent=2, sort_keys=True) if pipeline is not None else "",
        "schedule_json": json.dumps(schedule, indent=2, sort_keys=True) if schedule is not None else "",
    }
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers (mirror the test+infra modules)
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
        *, project_manager: Any, project_id: int, user_id: str
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


def handle_release_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/releases``.
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
        channel_id = _coerce_int(
            raw=request.query_params.get("channel_id", None)
        )

        release_manager = _build_release_manager(
            db_session=db_session
        )
        releases_result = release_manager.list_releases(
            project_id=project_id,
            status=_resolve_release_status(value=status),
            channel_id=channel_id,
            offset=offset,
            limit=params["per_page"],
        )
        releases = releases_result.releases
        channels = release_manager.list_channels(project_id).channels
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )
        total_pages = _total_pages_from_count(
            total=releases_result.total,
            per_page=params["per_page"],
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.release_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["releases"] = releases
        context["channels"] = channels
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["selected_status"] = status
        context["selected_channel_id"] = channel_id

        response = _render(
            template_name="projects/releases/list.html",
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


def handle_release_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/releases/{release_id}``.
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

        release_id = _coerce_int(
            raw=request.path_params.get("release_id", None)
        )
        release_manager = _build_release_manager(
            db_session=db_session
        )
        release_or_redirect = _resolve_owned_resource_or_redirect(
            auth=auth,
            project_id=project_id,
            manager=release_manager,
            getter_name="get_release",
            target_id=release_id,
            list_endpoint="projects.release_list",
            not_found_message="Release not found.",
        )
        if isinstance(release_or_redirect, RedirectResponse):
            return release_or_redirect
        release = release_or_redirect

        artifacts = release_manager.list_artifacts(release_id).artifacts
        channels = release_manager.list_channels(project_id).channels
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.release_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["release"] = release
        context["artifacts"] = artifacts
        context["channels"] = channels
        context["can_manage"] = can_manage
        context["provenance"] = _release_provenance(
            db_session=db_session,
            project_id=project_id,
            metadata=getattr(release, "metadata", None),
        )

        response = _render(
            template_name="projects/releases/detail.html",
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


def handle_pipeline_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/releases/pipelines``.
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

        release_manager = _build_release_manager(
            db_session=db_session
        )
        pipelines_result = release_manager.list_pipelines(
            project_id, offset=offset, limit=params["per_page"]
        )
        pipelines = pipelines_result.pipelines
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )
        total_pages = _total_pages_from_count(
            total=pipelines_result.total,
            per_page=params["per_page"],
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.pipeline_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["pipelines"] = pipelines
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages

        response = _render(
            template_name="projects/releases/pipeline_list.html",
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


def handle_pipeline_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/releases/pipelines/{pipeline_id}``.
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

        pipeline_id = _coerce_int(
            raw=request.path_params.get("pipeline_id", None)
        )
        release_manager = _build_release_manager(
            db_session=db_session
        )
        pipeline_or_redirect = _resolve_owned_resource_or_redirect(
            auth=auth,
            project_id=project_id,
            manager=release_manager,
            getter_name="get_pipeline",
            target_id=pipeline_id,
            list_endpoint="projects.pipeline_list",
            not_found_message="Pipeline not found.",
        )
        if isinstance(pipeline_or_redirect, RedirectResponse):
            return pipeline_or_redirect
        pipeline = pipeline_or_redirect

        recent_runs = release_manager.list_pipeline_runs(
            pipeline_id=pipeline_id, limit=10
        ).runs
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.pipeline_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["pipeline"] = pipeline
        context["recent_runs"] = recent_runs
        context["can_manage"] = can_manage

        response = _render(
            template_name="projects/releases/pipeline_detail.html",
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


def handle_channel_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/releases/channels`` --
        unpaginated list (channels are typically a small set).
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

        release_manager = _build_release_manager(
            db_session=db_session
        )
        channels = release_manager.list_channels(project_id).channels
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.channel_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["channels"] = channels
        context["can_manage"] = can_manage

        response = _render(
            template_name="projects/releases/channel_list.html",
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


def handle_schedule_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/releases/schedules``.
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

        release_manager = _build_release_manager(
            db_session=db_session
        )
        schedules = release_manager.list_schedules(project_id).schedules
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.schedule_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["schedules"] = schedules
        context["can_manage"] = can_manage

        response = _render(
            template_name="projects/releases/schedule_list.html",
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
    "projects.release_list": handle_release_list,
    "projects.release_detail": handle_release_detail,
    "projects.pipeline_list": handle_pipeline_list,
    "projects.pipeline_detail": handle_pipeline_detail,
    "projects.channel_list": handle_channel_list,
    "projects.schedule_list": handle_schedule_list,
}


def register_releases_routes(*, app: Any) -> None:
    """
        Attach the F4 release routes to a webworks app.
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
    "register_releases_routes",
    "handle_release_list",
    "handle_release_detail",
    "handle_pipeline_list",
    "handle_pipeline_detail",
    "handle_channel_list",
    "handle_schedule_list",
]
