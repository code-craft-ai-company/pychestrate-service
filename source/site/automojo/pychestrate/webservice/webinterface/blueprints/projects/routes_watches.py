"""
.. module:: webinterface.blueprints.projects.routes_watches
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /projects/*/watches
               (F5 slice -- watch CRUD + lifecycle actions).

.. moduleauthor:: Automation Mojo LLC

The eight watch routes served under the projects blueprint:

* ``GET  /projects/{project_id}/watches``                       -- list.
* ``GET  /projects/{project_id}/watches/create``                -- form
                                                                   (developer).
* ``POST /projects/{project_id}/watches/create``                -- create
                                                                   (developer).
* ``GET  /projects/{project_id}/watches/{watch_id}``            -- detail.
* ``GET  /projects/{project_id}/watches/{watch_id}/edit``       -- form
                                                                   (developer).
* ``POST /projects/{project_id}/watches/{watch_id}/edit``       -- update
                                                                   (developer).
* ``POST /projects/{project_id}/watches/{watch_id}/delete``     -- delete
                                                                   (admin).
* ``POST /projects/{project_id}/watches/{watch_id}/enable``     -- enable
                                                                   (developer).
* ``POST /projects/{project_id}/watches/{watch_id}/disable``    -- disable
                                                                   (developer).
* ``POST /projects/{project_id}/watches/{watch_id}/test``       -- test-run
                                                                   (developer).

Permission tiers used here:

* ``view`` -- list + detail pages (read-only).
* ``developer`` -- create / edit / enable / disable / test.
* ``admin`` -- delete (destructive).

The create / edit form's actual posted fields
(``event_type`` / ``repository_id`` / ``branch_pattern`` /
``action_type`` / ``action_spec_id`` / ``enabled``) are
translated into the manager's dataclass shape
(``trigger_source`` / ``source_id`` / ``conditions`` /
``actions``) by :func:`_build_watch_create_request` and
:func:`_build_watch_update_request`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from automojo.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
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
from automojo.pychestrate.webservice.webinterface.blueprints.projects.routes import (
    PROJECTS_PATH,
    _require_project_permission_or_redirect,
    _resolve_project_or_redirect,
)


_ROUTE_TABLE = (
    (
        "projects.watch_list",
        "/{project_id}/watches",
        ("GET",),
    ),
    (
        "projects.watch_create",
        "/{project_id}/watches/create",
        ("GET", "POST"),
    ),
    (
        "projects.watch_detail",
        "/{project_id}/watches/{watch_id}",
        ("GET",),
    ),
    (
        "projects.watch_edit",
        "/{project_id}/watches/{watch_id}/edit",
        ("GET", "POST"),
    ),
    (
        "projects.watch_delete",
        "/{project_id}/watches/{watch_id}/delete",
        ("POST",),
    ),
    (
        "projects.watch_enable",
        "/{project_id}/watches/{watch_id}/enable",
        ("POST",),
    ),
    (
        "projects.watch_disable",
        "/{project_id}/watches/{watch_id}/disable",
        ("POST",),
    ),
    (
        "projects.watch_test",
        "/{project_id}/watches/{watch_id}/test",
        ("POST",),
    ),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams (defined locally per the E2 lesson)
# ---------------------------------------------------------------------------


def _build_project_manager(*, db_session: Any) -> Any:
    from automojo.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectManager,
    )
    rtnval = ProjectManager(db_session)
    return rtnval


def _build_repository_manager(*, db_session: Any) -> Any:
    from automojo.pychestrate.core.managers.repository_manager import (  # noqa: E402
        RepositoryManager,
    )
    rtnval = RepositoryManager(db_session)
    return rtnval


def _build_watch_manager(*, db_session: Any) -> Any:
    from automojo.pychestrate.core.managers.watch_manager import (  # noqa: E402
        WatchManager,
    )
    rtnval = WatchManager(db_session)
    return rtnval


def _resolve_trigger_source(*, value: str) -> Any:
    """
        Resolve an ``event_type`` form-field value (e.g.
        ``"repository_commit"``) to the matching
        :class:`WatchTriggerSource` enum member.

        :raises: ValueError on an unknown value.
    """
    from automojo.pychestrate.core.managers.watch_manager import (  # noqa: E402
        WatchTriggerSource,
    )
    rtnval = WatchTriggerSource(value)
    return rtnval


def _resolve_watch_action(*, value: str) -> Any:
    """
        Resolve an ``action_type`` form-field value (e.g.
        ``"trigger_build"``) to the matching :class:`WatchAction`
        enum member.

        :raises: ValueError on an unknown value.
    """
    from automojo.pychestrate.core.managers.watch_manager import (  # noqa: E402
        WatchAction,
    )
    rtnval = WatchAction(value)
    return rtnval


def _enumerate_trigger_source_values() -> List[str]:
    """
        Return every :class:`WatchTriggerSource` value as a string,
        for the create / edit form's ``event_type`` selector.
    """
    try:
        from automojo.pychestrate.core.managers.watch_manager import (  # noqa: E402
            WatchTriggerSource,
        )
    except ImportError:
        return []
    rtnval: List[str] = []
    for member in WatchTriggerSource:
        rtnval.append(member.value)
    return rtnval


def _enumerate_watch_action_values() -> List[str]:
    """
        Return every :class:`WatchAction` value as a string, for
        the create / edit form's ``action_type`` selector.
    """
    try:
        from automojo.pychestrate.core.managers.watch_manager import (  # noqa: E402
            WatchAction,
        )
    except ImportError:
        return []
    rtnval: List[str] = []
    for member in WatchAction:
        rtnval.append(member.value)
    return rtnval


def _build_watch_condition(*, branch_pattern: str) -> Any:
    """
        Construct a :class:`WatchCondition` from the form's
        single ``branch_pattern`` field. The dataclass also
        carries ``tag_pattern`` / ``file_pattern`` / ``build_status``
        slots, but the create / edit forms only expose a branch
        pattern today; the other slots stay ``None``.
    """
    from automojo.pychestrate.core.managers.watch_manager import (  # noqa: E402
        WatchCondition,
    )
    pattern = branch_pattern if len(branch_pattern) > 0 else None
    rtnval = WatchCondition(branch_pattern=pattern)
    return rtnval


def _build_watch_action_config(
        *, action_type: str, action_spec_id: int
    ) -> Any:
    """
        Construct a single-element list of
        :class:`WatchActionConfig` for the form's
        ``action_type`` + ``action_spec_id`` pair.

        :raises: ValueError on an unknown ``action_type`` (raised
                 by :func:`_resolve_watch_action`) or when
                 ``action_spec_id`` is ``None``.
    """
    from automojo.pychestrate.core.managers.watch_manager import (  # noqa: E402
        WatchActionConfig,
    )
    if action_spec_id is None:
        raise ValueError(
            "action_spec_id is required for the selected action"
        )
    action_enum = _resolve_watch_action(value=action_type)
    rtnval = WatchActionConfig(
        action=action_enum,
        target_id=action_spec_id,
    )
    return rtnval


def _build_watch_create_request(
        *,
        name: str,
        event_type: str,
        repository_id: int,
        branch_pattern: str,
        action_type: str,
        action_spec_id: Optional[int],
        enabled: bool,
        description: str
    ) -> Any:
    """
        Construct a :class:`WatchCreateRequest` from the create
        form's actual posted fields. Translates the
        template-side names (``event_type`` / ``repository_id``
        / ``branch_pattern`` / ``action_type`` /
        ``action_spec_id``) to the manager dataclass shape
        (``trigger_source`` / ``source_id`` / ``conditions`` /
        ``actions``).

        :raises: ValueError on an unknown ``event_type`` /
                 ``action_type``, or when ``action_spec_id`` is
                 missing.
    """
    from automojo.pychestrate.core.managers.watch_manager import (  # noqa: E402
        WatchCreateRequest,
    )
    trigger_source = _resolve_trigger_source(value=event_type)
    conditions = _build_watch_condition(branch_pattern=branch_pattern)
    action_config = _build_watch_action_config(
        action_type=action_type,
        action_spec_id=action_spec_id,
    )
    rtnval = WatchCreateRequest(
        name=name,
        trigger_source=trigger_source,
        source_id=repository_id,
        conditions=conditions,
        actions=[action_config],
        enabled=enabled,
        description=description,
    )
    return rtnval


def _build_watch_update_request(
        *,
        name: Optional[str],
        branch_pattern: Optional[str],
        action_type: Optional[str],
        action_spec_id: Optional[int],
        enabled: Optional[bool],
        description: Optional[str]
    ) -> Any:
    """
        Construct a :class:`WatchUpdateRequest` from the edit
        form's posted fields. Each parameter is ``None`` to
        indicate "no change"; the conditions / actions slots
        are rebuilt only when the form supplied the
        corresponding field.

        :raises: ValueError on an unknown ``action_type``.
    """
    from automojo.pychestrate.core.managers.watch_manager import (  # noqa: E402
        WatchUpdateRequest,
    )
    conditions = None
    if branch_pattern is not None:
        conditions = _build_watch_condition(branch_pattern=branch_pattern)
    actions: Optional[List[Any]] = None
    if action_type is not None and action_spec_id is not None:
        actions = [
            _build_watch_action_config(
                action_type=action_type,
                action_spec_id=action_spec_id,
            )
        ]
    rtnval = WatchUpdateRequest(
        name=name,
        conditions=conditions,
        actions=actions,
        enabled=enabled,
        description=description,
    )
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


def _approximate_total_pages(
        *, page: int, per_page: int, returned_count: int
    ) -> int:
    if returned_count < per_page:
        if page == 1:
            return 1
        return page
    return page + 1


def _resolve_view_authorized_project(
        *, request: Request, auth: _AuthResolution
    ) -> Any:
    """
        ``view``-tier resolver shared by the read-only handlers
        (``watch_list``, ``watch_detail``).
    """
    project_id = _coerce_int(
        raw=request.path_params.get("project_id", None)
    )
    project_manager = _build_project_manager(db_session=auth.db_session)
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


def _resolve_project_for_action(
        *,
        auth: _AuthResolution,
        project_id: Optional[int],
        permission: str,
    ) -> Any:
    """
        Fetch the project, then enforce a write-tier permission.
        Returns the project on success or a
        :class:`RedirectResponse` to a sane fallback URL
        otherwise.
    """
    project_manager = _build_project_manager(db_session=auth.db_session)
    resolved = _resolve_project_or_redirect(
        auth=auth,
        project_manager=project_manager,
        project_id=project_id,
    )
    if isinstance(resolved, RedirectResponse):
        return (project_manager, resolved)
    project = resolved

    deny_response = _require_project_permission_or_redirect(
        project_manager=project_manager,
        auth=auth,
        project_id=project_id,
        permission=permission,
        deny_redirect_url=_url_for_module.url_for(
            "projects.project_detail", project_id=project_id
        ),
    )
    if deny_response is not None:
        return (project_manager, deny_response)
    return (project_manager, project)


def _resolve_owned_watch_or_redirect(
        *,
        auth: _AuthResolution,
        watch_manager: Any,
        project_id: int,
        watch_id: Optional[int]
    ) -> Any:
    """
        Look up a watch and verify it belongs to the supplied
        project (mirrors the legacy
        ``watch.project_id != project_id`` guard).
    """
    list_url = _url_for_module.url_for(
        "projects.watch_list", project_id=project_id
    )
    if watch_id is None:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=list_url,
            message="Watch not found.",
            category=flash.CATEGORY_ERROR,
        )
        return rtnval

    watch = watch_manager.get_watch(watch_id)
    if watch is None:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=list_url,
            message="Watch not found.",
            category=flash.CATEGORY_ERROR,
        )
        return rtnval
    if getattr(watch, "project_id", None) != project_id:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=list_url,
            message="Watch not found.",
            category=flash.CATEGORY_ERROR,
        )
        return rtnval
    return watch


# ---------------------------------------------------------------------------
# Form rendering helpers
# ---------------------------------------------------------------------------


def _render_watch_create_form(
        *,
        auth: _AuthResolution,
        project: Any,
        repositories: Any,
        form_data: Optional[MultiFormView],
        status_code: int = 200,
        build_specs: Optional[List[Any]] = None
    ) -> HTMLResponse:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="projects.watch_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["project"] = project
    context["repositories"] = repositories
    context["form_data"] = form_data
    context["event_types"] = _enumerate_trigger_source_values()
    context["action_types"] = _enumerate_watch_action_values()
    context["build_specs"] = (
        build_specs if build_specs is not None else []
    )
    response = _render(
        template_name="projects/watches/create.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(
        response=response, session=auth.session
    )
    return response


def _render_watch_edit_form(
        *,
        auth: _AuthResolution,
        project: Any,
        watch: Any,
        status_code: int = 200,
        repositories: Optional[List[Any]] = None,
        build_specs: Optional[List[Any]] = None
    ) -> HTMLResponse:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="projects.watch_edit",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["project"] = project
    context["watch"] = watch
    context["event_types"] = _enumerate_trigger_source_values()
    context["action_types"] = _enumerate_watch_action_values()
    context["repositories"] = (
        repositories if repositories is not None else []
    )
    context["build_specs"] = (
        build_specs if build_specs is not None else []
    )
    response = _render(
        template_name="projects/watches/edit.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(
        response=response, session=auth.session
    )
    return response


# ---------------------------------------------------------------------------
# Read-only handlers
# ---------------------------------------------------------------------------


def handle_watch_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/watches`` -- ``view``-gated
        paginated list.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(
                request=request, auth=auth
            )
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        watch_manager = _build_watch_manager(db_session=db_session)
        watches = watch_manager.list_watches(
            project_id, offset=offset, limit=params["per_page"]
        ).watches
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )
        total_pages = _approximate_total_pages(
            page=params["page"],
            per_page=params["per_page"],
            returned_count=len(watches),
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.watch_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["watches"] = watches
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages

        response = _render(
            template_name="projects/watches/list.html",
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


def handle_watch_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/watches/{watch_id}`` --
        ``view``-gated detail with the most-recent 20 trigger logs.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(
                request=request, auth=auth
            )
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        watch_id = _coerce_int(
            raw=request.path_params.get("watch_id", None)
        )
        watch_manager = _build_watch_manager(db_session=db_session)
        watch_or_redirect = _resolve_owned_watch_or_redirect(
            auth=auth,
            watch_manager=watch_manager,
            project_id=project_id,
            watch_id=watch_id,
        )
        if isinstance(watch_or_redirect, RedirectResponse):
            return watch_or_redirect
        watch = watch_or_redirect

        trigger_logs = watch_manager.get_trigger_logs(
            watch_id, limit=20
        )
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.watch_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["watch"] = watch
        context["trigger_logs"] = trigger_logs
        context["can_manage"] = can_manage

        response = _render(
            template_name="projects/watches/detail.html",
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
# Create / edit handlers (developer-gated)
# ---------------------------------------------------------------------------


def handle_watch_create(request: Request) -> Response:
    """
        ``GET  /projects/{project_id}/watches/create`` /
        ``POST .../create``. ``developer``-gated; CSRF-checked
        on POST.

        The legacy form is preserved 1:1, including the
        out-of-sync ``trigger_conditions`` / ``actions`` JSON
        kwargs (see module docstring).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        project_manager, resolved = _resolve_project_for_action(
            auth=auth, project_id=project_id, permission="developer"
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        repository_manager = _build_repository_manager(
            db_session=db_session
        )
        repositories = repository_manager.list_repositories(
            project_id, limit=100
        ).repositories

        method = request.method.upper()
        if method == "GET":
            return _render_watch_create_form(
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
                "projects.watch_create", project_id=project_id
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        event_type = str(
            single_form.get("event_type", "")
        ).strip()
        repository_id = _coerce_int(
            raw=single_form.get("repository_id", None)
        )
        branch_pattern = str(
            single_form.get("branch_pattern", "")
        ).strip()
        action_type = str(
            single_form.get("action_type", "")
        ).strip()
        action_spec_id = _coerce_int(
            raw=single_form.get("action_spec_id", None)
        )
        enabled_raw = single_form.get("enabled", None)
        enabled = (
            enabled_raw is not None
            and str(enabled_raw).lower() in ("true", "1", "on")
        )
        description = str(
            single_form.get("description", "")
        ).strip()

        if repository_id is None:
            flash.add_flash(
                session=auth.session,
                message=(
                    "A repository is required to create a watch."
                ),
                category=flash.CATEGORY_ERROR,
            )
            return _render_watch_create_form(
                auth=auth,
                project=project,
                repositories=repositories,
                form_data=form_view,
                status_code=400,
            )

        watch_manager = _build_watch_manager(db_session=db_session)
        try:
            create_request = _build_watch_create_request(
                name=name,
                event_type=event_type,
                repository_id=repository_id,
                branch_pattern=branch_pattern,
                action_type=action_type,
                action_spec_id=action_spec_id,
                enabled=enabled,
                description=description,
            )
            watch = watch_manager.create_watch(
                project_id, create_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.watch_detail",
                    project_id=project_id,
                    watch_id=watch.id,
                ),
                message='Watch "{}" created successfully.'.format(
                    name
                ),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message="Error creating watch: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return _render_watch_create_form(
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


def handle_watch_edit(request: Request) -> Response:
    """
        ``GET  /projects/{project_id}/watches/{watch_id}/edit`` /
        ``POST .../edit``. ``developer``-gated; CSRF-checked
        on POST.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        watch_id = _coerce_int(
            raw=request.path_params.get("watch_id", None)
        )

        project_manager, resolved = _resolve_project_for_action(
            auth=auth, project_id=project_id, permission="developer"
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        watch_manager = _build_watch_manager(db_session=db_session)
        watch_or_redirect = _resolve_owned_watch_or_redirect(
            auth=auth,
            watch_manager=watch_manager,
            project_id=project_id,
            watch_id=watch_id,
        )
        if isinstance(watch_or_redirect, RedirectResponse):
            return watch_or_redirect
        watch = watch_or_redirect

        method = request.method.upper()
        if method == "GET":
            return _render_watch_edit_form(
                auth=auth, project=project, watch=watch
            )

        # POST
        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "projects.watch_edit",
                project_id=project_id,
                watch_id=watch_id,
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name_raw = str(single_form.get("name", "")).strip()
        description_raw = str(
            single_form.get("description", "")
        ).strip()
        # Edit form: every field comes through on POST. We treat
        # an empty submitted value as "no change" for the
        # ``Optional``-typed fields on :class:`WatchUpdateRequest`,
        # except ``branch_pattern`` (an empty branch_pattern is
        # legitimate -- "match all branches"), so we forward it
        # unchanged when the field key is in the form at all.
        if "branch_pattern" in single_form:
            branch_pattern: Optional[str] = str(
                single_form.get("branch_pattern", "")
            ).strip()
        else:
            branch_pattern = None

        action_type_raw = str(
            single_form.get("action_type", "")
        ).strip()
        action_type: Optional[str] = (
            action_type_raw if len(action_type_raw) > 0 else None
        )
        action_spec_id = _coerce_int(
            raw=single_form.get("action_spec_id", None)
        )

        # ``enabled`` is a checkbox in the edit form; absence means
        # "not enabled", presence (any of "true"/"1"/"on") means
        # enabled. Edit always sends the value either way, so
        # always forward a definite bool.
        enabled_raw = single_form.get("enabled", None)
        enabled: Optional[bool] = (
            enabled_raw is not None
            and str(enabled_raw).lower() in ("true", "1", "on")
        )

        try:
            update_request = _build_watch_update_request(
                name=name_raw if len(name_raw) > 0 else None,
                branch_pattern=branch_pattern,
                action_type=action_type,
                action_spec_id=action_spec_id,
                enabled=enabled,
                description=(
                    description_raw
                    if len(description_raw) > 0 else None
                ),
            )
            watch_manager.update_watch(
                watch_id, update_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.watch_detail",
                    project_id=project_id,
                    watch_id=watch_id,
                ),
                message="Watch updated successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message="Error updating watch: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return _render_watch_edit_form(
                auth=auth, project=project, watch=watch,
                status_code=400,
            )
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Action handlers (delete / enable / disable / test)
# ---------------------------------------------------------------------------


def _handle_watch_action(
        *,
        request: Request,
        permission: str,
        action_callable_name: str,
        invokes_with_user_id: bool,
        success_truthy_message: str,
        success_falsey_message: Optional[str],
        success_falsey_category: str,
        error_message_prefix: str,
        success_redirect: str,
    ) -> Response:
    """
        Shared body for the four watch action handlers
        (``delete`` / ``enable`` / ``disable`` / ``test``).

        :param permission: Permission tier required (e.g.
                           ``"developer"`` or ``"admin"``).
        :param action_callable_name: Method name on
                                     :class:`WatchManager`.
        :param invokes_with_user_id: ``True`` for the manager
                                     calls that take a
                                     ``user_id`` second arg
                                     (``delete`` / ``enable`` /
                                     ``disable``); ``False`` for
                                     :meth:`WatchManager.test_watch`
                                     which takes only the id.
        :param success_falsey_message: When non-``None`` and the
                                       method returns a
                                       falsey-but-not-exception
                                       value, flash this instead
                                       of the success message.
                                       Used by ``test`` to
                                       distinguish "no matches"
                                       from "test failed".
        :param success_redirect: Either ``"watch_list"`` or
                                 ``"watch_detail"``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        watch_id = _coerce_int(
            raw=request.path_params.get("watch_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        list_fallback_url = (
            _url_for_module.url_for(
                "projects.watch_list", project_id=project_id
            )
            if project_id is not None
            else _url_for_module.url_for("projects.project_list")
        )

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=list_fallback_url,
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if project_id is None or watch_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=list_fallback_url,
                message="Watch not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        project_manager, project_resolved = (
            _resolve_project_for_action(
                auth=auth,
                project_id=project_id,
                permission=permission,
            )
        )
        if isinstance(project_resolved, RedirectResponse):
            return project_resolved

        success_url = (
            list_fallback_url
            if success_redirect == "watch_list"
            else _url_for_module.url_for(
                "projects.watch_detail",
                project_id=project_id,
                watch_id=watch_id,
            )
        )

        watch_manager = _build_watch_manager(db_session=db_session)
        action = getattr(watch_manager, action_callable_name)
        try:
            if invokes_with_user_id:
                result = action(watch_id, auth.user_id)
            else:
                result = action(watch_id)

            if (
                success_falsey_message is not None
                and result is False
            ):
                response = _redirect_with_flash(
                    session=auth.session,
                    url=success_url,
                    message=success_falsey_message,
                    category=success_falsey_category,
                )
                return response

            response = _redirect_with_flash(
                session=auth.session,
                url=success_url,
                message=success_truthy_message,
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=success_url,
                message="{}{}".format(
                    error_message_prefix, str(exc)
                ),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_watch_delete(request: Request) -> Response:
    """
        ``POST .../{watch_id}/delete``. ``admin``-gated.
        Redirects to the watch list on success.
    """
    rtnval = _handle_watch_action(
        request=request,
        permission="admin",
        action_callable_name="delete_watch",
        invokes_with_user_id=True,
        success_truthy_message="Watch deleted successfully.",
        success_falsey_message=None,
        success_falsey_category=flash.CATEGORY_INFO,
        error_message_prefix="Error deleting watch: ",
        success_redirect="watch_list",
    )
    return rtnval


def handle_watch_enable(request: Request) -> Response:
    """
        ``POST .../{watch_id}/enable``. ``developer``-gated.
    """
    rtnval = _handle_watch_action(
        request=request,
        permission="developer",
        action_callable_name="enable_watch",
        invokes_with_user_id=True,
        success_truthy_message="Watch enabled successfully.",
        success_falsey_message=None,
        success_falsey_category=flash.CATEGORY_INFO,
        error_message_prefix="Error enabling watch: ",
        success_redirect="watch_detail",
    )
    return rtnval


def handle_watch_disable(request: Request) -> Response:
    """
        ``POST .../{watch_id}/disable``. ``developer``-gated.
    """
    rtnval = _handle_watch_action(
        request=request,
        permission="developer",
        action_callable_name="disable_watch",
        invokes_with_user_id=True,
        success_truthy_message="Watch disabled successfully.",
        success_falsey_message=None,
        success_falsey_category=flash.CATEGORY_INFO,
        error_message_prefix="Error disabling watch: ",
        success_redirect="watch_detail",
    )
    return rtnval


def handle_watch_test(request: Request) -> Response:
    """
        ``POST .../{watch_id}/test``. ``developer``-gated.

        :class:`WatchManager.test_watch` returns truthy/falsey;
        truthy -> success flash, falsey -> info "no matches"
        flash.
    """
    rtnval = _handle_watch_action(
        request=request,
        permission="developer",
        action_callable_name="test_watch",
        invokes_with_user_id=False,
        success_truthy_message="Watch test successful.",
        success_falsey_message=(
            "Watch test completed with no matches."
        ),
        success_falsey_category=flash.CATEGORY_INFO,
        error_message_prefix="Error testing watch: ",
        success_redirect="watch_detail",
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "projects.watch_list": handle_watch_list,
    "projects.watch_create": handle_watch_create,
    "projects.watch_detail": handle_watch_detail,
    "projects.watch_edit": handle_watch_edit,
    "projects.watch_delete": handle_watch_delete,
    "projects.watch_enable": handle_watch_enable,
    "projects.watch_disable": handle_watch_disable,
    "projects.watch_test": handle_watch_test,
}


def register_watches_routes(*, app: Any) -> None:
    """
        Attach the F5 watch routes to a webworks app and register
        their endpoint names with the url_for shim.
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
    "register_watches_routes",
    "handle_watch_list",
    "handle_watch_create",
    "handle_watch_detail",
    "handle_watch_edit",
    "handle_watch_delete",
    "handle_watch_enable",
    "handle_watch_disable",
    "handle_watch_test",
]
