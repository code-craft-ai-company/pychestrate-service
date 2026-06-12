"""
.. module:: test_p13p_projects_calendar_watches_final_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the F5 (FINAL) slice of the projects port
               (calendar + watches + flask scaffold removal).

.. moduleauthor:: Code Craft AI LLC

PR F5 ports the three calendar routes plus the eight watch
routes -- the final eleven of the 53-route legacy projects
blueprint -- and deletes the flask scaffold (``endpoints.py``,
``register_web_blueprints``) entirely now that ``/projects``
is the last consumer-facing surface to leave flask.

Tests cover route registration, the calendar default window,
custom start_date/end_date passthrough, release-event detail
+ cross-project guard, watch list / detail / create / edit /
delete / enable / disable / test handlers, and a pair of
post-condition assertions that the legacy flask scaffold is
gone.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from ccai.pychestrate.webservice.webinterface.blueprints.config import (
    routes as config_routes,
)
from ccai.pychestrate.webservice.webinterface.blueprints.projects import (
    routes as projects_routes,
    routes_calendar as projects_routes_calendar,
    routes_watches as projects_routes_watches,
)
from ccai.pychestrate.webservice.webinterface.foundation import (
    cookie_session,
    csrf,
    flash,
    templating,
    url_for as url_for_module,
)


_TEST_UI_COOKIE_SECRET: bytes = b"\x00" * 32


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeQueryParams:
    def __init__(self, *, mapping: Optional[Dict[str, str]] = None) -> None:
        self._mapping: Dict[str, str] = mapping if mapping is not None else {}
        return

    def get(
            self, key: str, default: Optional[str] = None
        ) -> Optional[str]:
        return self._mapping.get(key, default)


class _FakeHeaders:
    def __init__(self, *, mapping: Optional[Dict[str, str]] = None) -> None:
        self._mapping: Dict[str, str] = mapping if mapping is not None else {}
        return

    def get(
            self, key: str, default: Optional[str] = None
        ) -> Optional[str]:
        return self._mapping.get(key, default)


class _FakeRequest:
    def __init__(
        self,
        *,
        method: str = "GET",
        cookies: Optional[Dict[str, str]] = None,
        body: bytes = b"",
        path_params: Optional[Dict[str, Any]] = None,
        query_mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        self.method: str = method
        self.cookies: Dict[str, str] = cookies if cookies is not None else {}
        self.body: bytes = body
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(
            mapping=query_mapping
        )
        self.headers: _FakeHeaders = _FakeHeaders()
        return

    def form(self) -> Dict[str, str]:
        from urllib.parse import parse_qs
        try:
            parsed = parse_qs(
                self.body.decode("utf-8"), keep_blank_values=True
            )
        except Exception:
            return {}
        rtnval: Dict[str, str] = {}
        for key, values in parsed.items():
            if len(values) > 0:
                rtnval[key] = values[0]
        return rtnval


class _FakeApp:
    def __init__(self) -> None:
        self.calls: List[Any] = []
        return

    def attach_route(
        self, path: str, methods: Optional[List[str]] = None
    ) -> Callable:
        resolved_methods = tuple(methods if methods is not None else ["GET"])

        def decorator(func: Callable) -> Callable:
            self.calls.append((path, resolved_methods, func))
            return func

        return decorator


class _FakeDbSession:
    def __init__(self) -> None:
        self.close_count: int = 0
        return

    def close(self) -> None:
        self.close_count = self.close_count + 1
        return


class _FakeSessionInfo:
    def __init__(
            self, *, user_id: str, username: str, csrf_token: str
        ) -> None:
        self.user_id: str = user_id
        self.username: str = username
        self.csrf_token: str = csrf_token
        return


class _FakeSecurityManager:
    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.validate_token_response: Optional[_FakeSessionInfo] = None
        return

    def validate_token(self, token: str) -> Optional[_FakeSessionInfo]:
        return self.validate_token_response

    def check_permission(self, user_id: str, permission: str) -> bool:
        return True


class _StubTemplate:
    def __init__(self, *, name: str) -> None:
        self.name: str = name
        self.render_calls: List[Dict[str, Any]] = []
        return

    def render(self, ctx: Dict[str, Any]) -> str:
        self.render_calls.append(ctx)
        return "RENDERED:{}".format(self.name)


class _StubJinjaEnvironment:
    def __init__(self) -> None:
        self.template_lookups: List[str] = []
        self.last_template: Optional[_StubTemplate] = None
        self.globals: Dict[str, Any] = {}
        return

    def get_template(self, name: str) -> _StubTemplate:
        self.template_lookups.append(name)
        self.last_template = _StubTemplate(name=name)
        return self.last_template


# ---- Project / calendar / watch fakes -------------------------------------


class _FakeProject:
    def __init__(self, *, project_id: int, name: str = "p") -> None:
        self.id: int = project_id
        self.name: str = name
        return


class _FakeReleaseEvent:
    def __init__(
            self, *, event_id: int, project_id: int = 1
        ) -> None:
        self.id: int = event_id
        self.project_id: int = project_id
        return


class _FakeWatch:
    def __init__(
            self, *, watch_id: int, project_id: int = 1,
            enabled: bool = True
        ) -> None:
        self.id: int = watch_id
        self.project_id: int = project_id
        self.enabled: bool = enabled
        return


class _FakeRepository:
    def __init__(self, *, repo_id: int, project_id: int = 1) -> None:
        self.id: int = repo_id
        self.project_id: int = project_id
        return


class _FakeProjectManager:
    last_instance: Optional["_FakeProjectManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.get_project_response: Optional[_FakeProject] = None
        self.default_check_permission_response: bool = True
        self.check_permission_responses: Dict[str, bool] = {}
        _FakeProjectManager.last_instance = self
        return

    def get_project(self, project_id: int) -> Optional[_FakeProject]:
        return self.get_project_response

    def check_permission(
            self, project_id: int, user_id: str, permission: str
        ) -> bool:
        return self.check_permission_responses.get(
            permission, self.default_check_permission_response
        )


class _FakeRepositoryManager:
    last_instance: Optional["_FakeRepositoryManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_repositories_response: List[_FakeRepository] = []
        _FakeRepositoryManager.last_instance = self
        return

    def list_repositories(
            self, project_id: int, **kwargs: Any
        ) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            repositories=self.list_repositories_response,
            total=len(self.list_repositories_response),
            offset=0,
            limit=len(self.list_repositories_response),
        )


class _FakeReleaseManager:
    last_instance: Optional["_FakeReleaseManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.calendar_events_response: List[Any] = []
        self.calendar_events_calls: List[Dict[str, Any]] = []
        self.list_release_events_response: List[Any] = []
        self.get_release_event_response: Optional[_FakeReleaseEvent] = (
            None
        )
        self.list_phase_events_response: List[Any] = []
        self.list_release_branches_response: List[Any] = []
        self.list_merge_events_response: List[Any] = []
        self.list_pull_events_response: List[Any] = []
        _FakeReleaseManager.last_instance = self
        return

    def get_calendar_events(
            self, project_id: int, start_date: Any, end_date: Any
        ) -> List[Any]:
        self.calendar_events_calls.append({
            "project_id": project_id,
            "start_date": start_date,
            "end_date": end_date,
        })
        return self.calendar_events_response

    def list_release_events(
            self, project_id: int, **kwargs: Any
        ) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            events=self.list_release_events_response,
            total=len(self.list_release_events_response),
            offset=0,
            limit=len(self.list_release_events_response),
        )

    def get_release_event(
            self, event_id: int
        ) -> Optional[_FakeReleaseEvent]:
        return self.get_release_event_response

    def list_phase_events(self, event_id: int) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            phases=self.list_phase_events_response,
            total=len(self.list_phase_events_response),
        )

    def list_release_branches(self, event_id: int) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            branches=self.list_release_branches_response,
            total=len(self.list_release_branches_response),
        )

    def list_merge_events(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            events=self.list_merge_events_response,
            total=len(self.list_merge_events_response),
            offset=0,
            limit=len(self.list_merge_events_response),
        )

    def list_pull_events(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            events=self.list_pull_events_response,
            total=len(self.list_pull_events_response),
            offset=0,
            limit=len(self.list_pull_events_response),
        )


class _FakeWatchManager:
    last_instance: Optional["_FakeWatchManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_watches_response: List[_FakeWatch] = []
        self.get_watch_response: Optional[_FakeWatch] = None
        self.get_trigger_logs_response: List[Any] = []
        self.create_watch_response: Optional[_FakeWatch] = None
        self.create_watch_calls: List[Dict[str, Any]] = []
        self.update_watch_called: bool = False
        self.update_watch_calls: List[Dict[str, Any]] = []
        self.delete_watch_called: bool = False
        self.enable_watch_called: bool = False
        self.disable_watch_called: bool = False
        self.test_watch_response: Any = True
        self.test_watch_called: bool = False
        _FakeWatchManager.last_instance = self
        return

    def list_watches(
            self, project_id: int, **kwargs: Any
        ) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            watches=self.list_watches_response,
            total=len(self.list_watches_response),
            offset=0,
            limit=len(self.list_watches_response),
        )

    def get_watch(self, watch_id: int) -> Optional[_FakeWatch]:
        return self.get_watch_response

    def get_trigger_logs(self, watch_id: int, **kwargs: Any) -> List[Any]:
        return self.get_trigger_logs_response

    def create_watch(
            self, project_id: int, request: Any, user_id: str
        ) -> Optional[_FakeWatch]:
        self.create_watch_calls.append({
            "project_id": project_id,
            "request": request,
            "user_id": user_id,
        })
        return self.create_watch_response

    def update_watch(
            self, watch_id: int, request: Any, user_id: str
        ) -> None:
        self.update_watch_called = True
        self.update_watch_calls.append({
            "watch_id": watch_id,
            "request": request,
            "user_id": user_id,
        })
        return

    def delete_watch(self, watch_id: int, user_id: str) -> None:
        self.delete_watch_called = True
        return

    def enable_watch(self, watch_id: int, user_id: str) -> None:
        self.enable_watch_called = True
        return

    def disable_watch(self, watch_id: int, user_id: str) -> None:
        self.disable_watch_called = True
        return

    def test_watch(self, watch_id: int) -> Any:
        self.test_watch_called = True
        return self.test_watch_response


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _install_stub_environment() -> _StubJinjaEnvironment:
    env = _StubJinjaEnvironment()
    templating.set_default_environment(environment=env)
    return env


def _install_ui_cookie_secret() -> None:
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = _TEST_UI_COOKIE_SECRET
    return


def _install_db_session_factory(*, db_session: Any) -> None:
    def factory() -> Any:
        return db_session
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = factory
    return


def _reset_global_state() -> None:
    url_for_module.reset_registry_for_testing()
    templating.reset_default_environment_for_testing()
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = None
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = None
    _FakeProjectManager.last_instance = None
    _FakeRepositoryManager.last_instance = None
    _FakeReleaseManager.last_instance = None
    _FakeWatchManager.last_instance = None
    return


def _patch_security_manager() -> Any:
    info = _FakeSessionInfo(
        user_id="u-admin", username="admin", csrf_token="csrf-fresh"
    )

    def _builder(*, db_session: Any) -> _FakeSecurityManager:
        instance = _FakeSecurityManager(db_session)
        instance.validate_token_response = info
        return instance

    patch = create_module_patch(config_routes, "_build_security_manager")
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_project_manager_in(
        *,
        target_module: Any,
        configure: Optional[Callable[[_FakeProjectManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeProjectManager:
        instance = _FakeProjectManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(target_module, "_build_project_manager")
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_repository_manager_in(
        *,
        target_module: Any,
        configure: Optional[
            Callable[[_FakeRepositoryManager], None]
        ] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeRepositoryManager:
        instance = _FakeRepositoryManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        target_module, "_build_repository_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_release_manager(
        *,
        configure: Optional[Callable[[_FakeReleaseManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeReleaseManager:
        instance = _FakeReleaseManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        projects_routes_calendar, "_build_release_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_watch_manager(
        *,
        configure: Optional[Callable[[_FakeWatchManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeWatchManager:
        instance = _FakeWatchManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        projects_routes_watches, "_build_watch_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_watch_create_request_builder() -> Any:
    """
        Patch the lazy ``_build_watch_create_request`` seam so
        tests don't trip on the preserved legacy
        ``trigger_conditions``/``actions`` kwarg bitrot
        (see ``routes_watches.py`` module docstring). The
        builder returns an opaque sentinel that flows through
        the patched ``WatchManager.create_watch`` stub.
    """
    def _builder(**kwargs: Any) -> Dict[str, Any]:
        rtnval = dict(kwargs)
        return rtnval

    patch = create_module_patch(
        projects_routes_watches, "_build_watch_create_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_watch_update_request_builder() -> Any:
    """
        Sibling of :func:`_patch_watch_create_request_builder`
        for the update path.
    """
    def _builder(**kwargs: Any) -> Dict[str, Any]:
        rtnval = dict(kwargs)
        return rtnval

    patch = create_module_patch(
        projects_routes_watches, "_build_watch_update_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _build_authenticated_cookie() -> str:
    payload = {
        "user_id": "u-admin",
        "username": "admin",
        "session_token": "tok-abc",
    }
    rtnval = cookie_session.sign_session_payload(
        payload=payload, secret=_TEST_UI_COOKIE_SECRET
    )
    return rtnval


def _register_url_for_endpoints() -> None:
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
        register_config_routes,
    )
    app = _FakeApp()
    register_config_routes(app=app)
    projects_routes.register_projects_routes(app=app)
    return


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_calendar_routes_attaches_documented_routes():
    """
    **Feature: webworks projects calendar T13.1 (F5)**
    **Property: register_calendar_routes attaches the three
    calendar routes at /projects/{id}/calendar*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        projects_routes_calendar.register_calendar_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/projects/{project_id}/calendar", ("GET",)),
            (
                "/projects/{project_id}/calendar/events",
                ("GET",),
            ),
            (
                "/projects/{project_id}/calendar/events/{event_id}",
                ("GET",),
            ),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_watches_routes_attaches_documented_routes():
    """
    **Feature: webworks projects watches T13.2 (F5)**
    **Property: register_watches_routes attaches all eight watch
    routes covering list / create / detail / edit / delete /
    enable / disable / test.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        projects_routes_watches.register_watches_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/projects/{project_id}/watches", ("GET",)),
            (
                "/projects/{project_id}/watches/create",
                ("GET", "POST"),
            ),
            (
                "/projects/{project_id}/watches/{watch_id}",
                ("GET",),
            ),
            (
                "/projects/{project_id}/watches/{watch_id}/edit",
                ("GET", "POST"),
            ),
            (
                "/projects/{project_id}/watches/{watch_id}/delete",
                ("POST",),
            ),
            (
                "/projects/{project_id}/watches/{watch_id}/enable",
                ("POST",),
            ),
            (
                "/projects/{project_id}/watches/{watch_id}/disable",
                ("POST",),
            ),
            (
                "/projects/{project_id}/watches/{watch_id}/test",
                ("POST",),
            ),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_projects_routes_cascades_to_all_sub_features():
    """
    **Feature: webworks projects all-features T13.0 (F5)**
    **Property: register_projects_routes cascades through every
    F1..F5 sub-feature; the union of attached routes contains
    every documented endpoint.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        projects_routes.register_projects_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected_subset = {
            # F1
            ("/projects", ("GET",)),
            ("/projects/list", ("GET",)),
            # F2
            ("/projects/{project_id}/repositories", ("GET",)),
            # F3
            ("/projects/{project_id}/builds", ("GET",)),
            (
                "/projects/{project_id}/infrastructure",
                ("GET",),
            ),
            # F4
            ("/projects/{project_id}/tests", ("GET",)),
            ("/projects/{project_id}/releases", ("GET",)),
            # F5
            ("/projects/{project_id}/calendar", ("GET",)),
            ("/projects/{project_id}/watches", ("GET",)),
            (
                "/projects/{project_id}/watches/{watch_id}/test",
                ("POST",),
            ),
        }
        missing = expected_subset - actual
        testbase.assert_equal(missing, set())
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Calendar
# ===========================================================================


def test_handle_calendar_view_uses_default_window():
    """
    **Feature: webworks projects calendar T13.3 (F5)**
    **Property: GET .../calendar with no start/end query params
    forwards a sane default window to ReleaseManager.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    rm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_calendar,
            configure=_seed_pm,
        )
        rm_patch = _patch_release_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = (
            projects_routes_calendar.handle_calendar_view(request)
        )

        testbase.assert_equal(response.status_code, 200)
        rm = _FakeReleaseManager.last_instance
        call = rm.calendar_events_calls[0]
        testbase.assert_equal(call["project_id"], 7)
        # Default window: start of current month, end-of-month.
        testbase.assert_equal(
            isinstance(call["start_date"], datetime), True
        )
        testbase.assert_equal(
            isinstance(call["end_date"], datetime), True
        )
        testbase.assert_equal(call["start_date"].day, 1)
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_calendar_view_honors_custom_start_and_end():
    """
    **Feature: webworks projects calendar T13.4 (F5)**
    **Property: GET .../calendar?start_date=...&end_date=...
    forwards the parsed values verbatim.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    rm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_calendar,
            configure=_seed_pm,
        )
        rm_patch = _patch_release_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
            query_mapping={
                "start_date": "2026-03-01T00:00:00",
                "end_date": "2026-03-31T23:59:59",
            },
        )
        response = (
            projects_routes_calendar.handle_calendar_view(request)
        )

        testbase.assert_equal(response.status_code, 200)
        rm = _FakeReleaseManager.last_instance
        call = rm.calendar_events_calls[0]
        testbase.assert_equal(call["start_date"].year, 2026)
        testbase.assert_equal(call["start_date"].month, 3)
        testbase.assert_equal(call["start_date"].day, 1)
        testbase.assert_equal(call["end_date"].year, 2026)
        testbase.assert_equal(call["end_date"].month, 3)
        testbase.assert_equal(call["end_date"].day, 31)
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_release_event_detail_renders_with_phases_and_branches():
    """
    **Feature: webworks projects calendar T13.5 (F5)**
    **Property: GET .../calendar/events/{eid} renders the detail
    template populated with phases / branches / merge_events /
    pull_events from the release manager.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    rm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_calendar,
            configure=_seed_pm,
        )

        def _seed_rm(instance: _FakeReleaseManager) -> None:
            instance.get_release_event_response = _FakeReleaseEvent(
                event_id=42, project_id=7
            )
            instance.list_phase_events_response = ["phase-a"]
            instance.list_release_branches_response = ["main"]
            instance.list_merge_events_response = ["m1"]
            instance.list_pull_events_response = ["p1"]
            return

        rm_patch = _patch_release_manager(configure=_seed_rm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "event_id": "42"},
        )
        response = (
            projects_routes_calendar
            .handle_release_event_detail(request)
        )

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["event"].id, 42)
        testbase.assert_equal(ctx["phases"], ["phase-a"])
        testbase.assert_equal(ctx["branches"], ["main"])
        testbase.assert_equal(ctx["merge_events"], ["m1"])
        testbase.assert_equal(ctx["pull_events"], ["p1"])
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_release_event_detail_redirects_when_cross_project():
    """
    **Feature: webworks projects calendar T13.6 (F5)**
    **Property: A release event whose project_id doesn't match
    the URL is treated as not-found.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    rm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_calendar,
            configure=_seed_pm,
        )

        def _seed_rm(instance: _FakeReleaseManager) -> None:
            instance.get_release_event_response = _FakeReleaseEvent(
                event_id=42, project_id=99
            )
            return

        rm_patch = _patch_release_manager(configure=_seed_rm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "event_id": "42"},
        )
        response = (
            projects_routes_calendar
            .handle_release_event_detail(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/projects/7/calendar/events",
        )
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Watches
# ===========================================================================


def test_handle_watch_list_renders_with_can_manage_flag():
    """
    **Feature: webworks projects watches T13.7 (F5)**
    **Property: GET .../watches renders the list template;
    can_manage is True when the user has developer permission.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    wm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            instance.check_permission_responses = {
                "view": True, "developer": True
            }
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )

        def _seed_wm(instance: _FakeWatchManager) -> None:
            instance.list_watches_response = [
                _FakeWatch(watch_id=1, project_id=7),
                _FakeWatch(watch_id=2, project_id=7),
            ]
            return

        wm_patch = _patch_watch_manager(configure=_seed_wm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = projects_routes_watches.handle_watch_list(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["can_manage"], True)
        testbase.assert_equal(len(ctx["watches"]), 2)
    finally:
        for p in (wm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_detail_renders_with_trigger_logs():
    """
    **Feature: webworks projects watches T13.8 (F5)**
    **Property: GET .../watches/{wid} renders the detail
    template populated with the trigger_logs from the manager.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    wm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )

        def _seed_wm(instance: _FakeWatchManager) -> None:
            instance.get_watch_response = _FakeWatch(
                watch_id=42, project_id=7
            )
            instance.get_trigger_logs_response = ["log-a", "log-b"]
            return

        wm_patch = _patch_watch_manager(configure=_seed_wm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "watch_id": "42"},
        )
        response = projects_routes_watches.handle_watch_detail(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["watch"].id, 42)
        testbase.assert_equal(ctx["trigger_logs"], ["log-a", "log-b"])
    finally:
        for p in (wm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_detail_redirects_when_cross_project():
    """
    **Feature: webworks projects watches T13.9 (F5)**
    **Property: A watch whose project_id doesn't match the URL
    is treated as not-found.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    wm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )

        def _seed_wm(instance: _FakeWatchManager) -> None:
            instance.get_watch_response = _FakeWatch(
                watch_id=42, project_id=99
            )
            return

        wm_patch = _patch_watch_manager(configure=_seed_wm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "watch_id": "42"},
        )
        response = projects_routes_watches.handle_watch_detail(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/watches"
        )
    finally:
        for p in (wm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_create_get_renders_form_with_repositories():
    """
    **Feature: webworks projects watches T13.10 (F5)**
    **Property: GET .../watches/create renders the create form
    with the developer's repository list as context.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    repo_patch = None
    wm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )

        def _seed_repo(instance: _FakeRepositoryManager) -> None:
            instance.list_repositories_response = [
                _FakeRepository(repo_id=1, project_id=7),
                _FakeRepository(repo_id=2, project_id=7),
            ]
            return

        repo_patch = _patch_repository_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_repo,
        )
        wm_patch = _patch_watch_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = projects_routes_watches.handle_watch_create(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["repositories"]), 2)
        # GET path should not have invoked create_watch.
        testbase.assert_equal(
            _FakeWatchManager.last_instance, None
        )
    finally:
        for p in (wm_patch, repo_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_create_post_developer_denied_redirects():
    """
    **Feature: webworks projects watches T13.11 (F5)**
    **Property: POST .../watches/create from a non-developer
    user redirects back to the project detail with a permission
    denied flash, and never invokes create_watch.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    repo_patch = None
    wm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            instance.check_permission_responses = {
                "view": True, "developer": False
            }
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )
        repo_patch = _patch_repository_manager_in(
            target_module=projects_routes_watches
        )
        wm_patch = _patch_watch_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
            body=b"csrf_token=csrf-fresh&name=watch-a",
        )
        response = projects_routes_watches.handle_watch_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7"
        )
        # Watch manager builder should never have been called.
        testbase.assert_equal(
            _FakeWatchManager.last_instance, None
        )
    finally:
        for p in (wm_patch, repo_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_edit_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks projects watches T13.12 (F5)**
    **Property: POST .../watches/{wid}/edit with valid CSRF +
    fields invokes update_watch and redirects to the detail
    page. The ``_build_watch_update_request`` seam is patched
    so the test doesn't trip on the preserved legacy
    ``trigger_conditions`` kwarg bitrot.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    wm_patch = None
    upd_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )

        def _seed_wm(instance: _FakeWatchManager) -> None:
            instance.get_watch_response = _FakeWatch(
                watch_id=42, project_id=7
            )
            return

        wm_patch = _patch_watch_manager(configure=_seed_wm)
        upd_patch = _patch_watch_update_request_builder()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "watch_id": "42"},
            body=(
                b"csrf_token=csrf-fresh"
                b"&name=renamed-watch"
                b"&description=updated"
            ),
        )
        response = projects_routes_watches.handle_watch_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/watches/42"
        )
        testbase.assert_equal(
            _FakeWatchManager.last_instance.update_watch_called, True
        )
    finally:
        for p in (upd_patch, wm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_delete_admin_required_redirects_when_denied():
    """
    **Feature: webworks projects watches T13.13 (F5)**
    **Property: POST .../watches/{wid}/delete from a
    non-admin user redirects to the project detail and never
    invokes delete_watch.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    wm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            instance.check_permission_responses = {
                "admin": False, "view": True
            }
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )
        wm_patch = _patch_watch_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "watch_id": "42"},
            body=b"csrf_token=csrf-fresh",
        )
        response = projects_routes_watches.handle_watch_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7"
        )
        testbase.assert_equal(
            _FakeWatchManager.last_instance, None
        )
    finally:
        for p in (wm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_test_truthy_yields_success_flash_redirect():
    """
    **Feature: webworks projects watches T13.14 (F5)**
    **Property: POST .../watches/{wid}/test with a truthy
    test_watch result redirects to the detail page (success
    flash); the watch_id was passed to the manager.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    wm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )

        def _seed_wm(instance: _FakeWatchManager) -> None:
            instance.test_watch_response = True
            return

        wm_patch = _patch_watch_manager(configure=_seed_wm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "watch_id": "42"},
            body=b"csrf_token=csrf-fresh",
        )
        response = projects_routes_watches.handle_watch_test(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/watches/42"
        )
        testbase.assert_equal(
            _FakeWatchManager.last_instance.test_watch_called, True
        )
    finally:
        for p in (wm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_test_falsey_yields_no_matches_flash():
    """
    **Feature: webworks projects watches T13.15 (F5)**
    **Property: POST .../watches/{wid}/test with a False
    test_watch result still 302s back to the detail (info
    flash for the "no matches" case), distinct from the
    exception-raised error path.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    wm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )

        def _seed_wm(instance: _FakeWatchManager) -> None:
            instance.test_watch_response = False
            return

        wm_patch = _patch_watch_manager(configure=_seed_wm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "watch_id": "42"},
            body=b"csrf_token=csrf-fresh",
        )
        response = projects_routes_watches.handle_watch_test(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/watches/42"
        )
        testbase.assert_equal(
            _FakeWatchManager.last_instance.test_watch_called, True
        )
    finally:
        for p in (wm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_enable_redirects_to_detail():
    """
    **Feature: webworks projects watches T13.16 (F5)**
    **Property: POST .../watches/{wid}/enable invokes
    enable_watch and redirects to the detail page.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    wm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )
        wm_patch = _patch_watch_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "watch_id": "42"},
            body=b"csrf_token=csrf-fresh",
        )
        response = projects_routes_watches.handle_watch_enable(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/watches/42"
        )
        testbase.assert_equal(
            _FakeWatchManager.last_instance.enable_watch_called, True
        )
    finally:
        for p in (wm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Flask scaffold removal
# ===========================================================================


def test_legacy_flask_endpoints_module_no_longer_importable():
    """
    **Feature: webworks projects scaffold-cleanup T13.17 (F5)**
    **Property: ``webinterface.blueprints.projects.endpoints``
    is gone -- the legacy 2,529-LOC flask blueprint was deleted
    once F5 landed the calendar + watches port.**
    """
    raised = False
    try:
        from ccai.pychestrate.webservice.webinterface.blueprints.projects import (  # noqa: F401, E402
            endpoints,
        )
    except ImportError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_register_web_blueprints_no_longer_exposed():
    """
    **Feature: webworks projects scaffold-cleanup T13.18 (F5)**
    **Property: The legacy ``register_web_blueprints`` shim was
    deleted from ``webinterface.blueprints`` once /projects was
    the last consumer surface to leave flask.**
    """
    raised = False
    try:
        from ccai.pychestrate.webservice.webinterface.blueprints import (  # noqa: F401, E402
            register_web_blueprints,
        )
    except ImportError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ===========================================================================
# Form-translation regression tests (PR p13s)
# ===========================================================================
#
# The F5 port preserved the legacy flask handler's call to
# ``WatchCreateRequest`` / ``WatchUpdateRequest`` with kwargs that
# never matched the manager's dataclass shape. PR p13s rewrote
# ``_build_watch_create_request`` / ``_build_watch_update_request``
# to translate the create / edit form's actual posted fields
# (``event_type`` / ``repository_id`` / ``branch_pattern`` /
# ``action_type`` / ``action_spec_id`` / ``enabled``) into
# ``WatchCreateRequest(name, trigger_source, source_id,
# conditions, actions, enabled, description)``.
#
# The tests below DO NOT patch the ``_build_watch_*_request``
# seams; they exercise the real translation end-to-end against
# the stubbed :class:`_FakeWatchManager` and assert the
# constructed dataclass carries the expected enum / source_id /
# WatchCondition / WatchActionConfig values.


def test_handle_watch_create_post_translates_form_to_dataclass():
    """
    **Feature: webworks projects watches T13.19 (p13s)**
    **Property: POST /watches/create translates the template
    form fields into a :class:`WatchCreateRequest` whose
    ``trigger_source``, ``source_id``, ``conditions``, and
    ``actions`` carry the parsed values from the template's
    ``event_type`` / ``repository_id`` / ``branch_pattern`` /
    ``action_type`` / ``action_spec_id`` form fields. Catches
    any future regression of the legacy "trigger_conditions"
    bitrot.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    repo_patch = None
    wm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )
        repo_patch = _patch_repository_manager_in(
            target_module=projects_routes_watches
        )

        def _seed_wm(instance: _FakeWatchManager) -> None:
            instance.create_watch_response = _FakeWatch(
                watch_id=99, project_id=7
            )
            return

        wm_patch = _patch_watch_manager(configure=_seed_wm)

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh"
            b"&name=watch-on-main"
            b"&description=auto+build"
            b"&repository_id=11"
            b"&event_type=repository_commit"
            b"&branch_pattern=main"
            b"&action_type=trigger_build"
            b"&action_spec_id=22"
            b"&enabled=true"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
            body=body,
        )
        response = projects_routes_watches.handle_watch_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/watches/99"
        )

        wm = _FakeWatchManager.last_instance
        testbase.assert_equal(len(wm.create_watch_calls), 1)
        call = wm.create_watch_calls[0]
        testbase.assert_equal(call["project_id"], 7)
        req_obj = call["request"]
        testbase.assert_equal(req_obj.name, "watch-on-main")
        testbase.assert_equal(req_obj.description, "auto build")
        testbase.assert_equal(req_obj.source_id, 11)
        testbase.assert_equal(req_obj.enabled, True)
        # ``trigger_source`` is the WatchTriggerSource enum;
        # accept either the enum's ``.value`` shape or string
        # equality (str-Enum) by comparing strings.
        testbase.assert_equal(
            str(req_obj.trigger_source.value), "repository_commit"
        )
        testbase.assert_equal(
            req_obj.conditions.branch_pattern, "main"
        )
        testbase.assert_equal(len(req_obj.actions), 1)
        action0 = req_obj.actions[0]
        testbase.assert_equal(
            str(action0.action.value), "trigger_build"
        )
        testbase.assert_equal(action0.target_id, 22)
    finally:
        for p in (wm_patch, repo_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_create_post_invalid_event_type_yields_error():
    """
    **Feature: webworks projects watches T13.20 (p13s)**
    **Property: POST /watches/create with an unknown
    ``event_type`` value re-renders the form with status 400
    and never invokes ``WatchManager.create_watch``.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    repo_patch = None
    wm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )
        repo_patch = _patch_repository_manager_in(
            target_module=projects_routes_watches
        )
        wm_patch = _patch_watch_manager()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh"
            b"&name=watch-bad-event"
            b"&repository_id=11"
            b"&event_type=NOT_A_REAL_EVENT"
            b"&action_type=trigger_build"
            b"&action_spec_id=22"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
            body=body,
        )
        response = projects_routes_watches.handle_watch_create(request)
        testbase.assert_equal(response.status_code, 400)
        wm = _FakeWatchManager.last_instance
        testbase.assert_equal(len(wm.create_watch_calls), 0)
    finally:
        for p in (wm_patch, repo_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_create_post_missing_repository_id_yields_error():
    """
    **Feature: webworks projects watches T13.21 (p13s)**
    **Property: POST /watches/create with no ``repository_id``
    short-circuits with a 400 + flash and never calls
    ``WatchManager.create_watch`` (the manager's
    ``WatchCreateRequest.source_id`` is non-optional).**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    repo_patch = None
    wm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )
        repo_patch = _patch_repository_manager_in(
            target_module=projects_routes_watches
        )
        wm_patch = _patch_watch_manager()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh"
            b"&name=watch-missing-repo"
            b"&event_type=repository_commit"
            b"&action_type=trigger_build"
            b"&action_spec_id=22"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
            body=body,
        )
        response = projects_routes_watches.handle_watch_create(request)
        testbase.assert_equal(response.status_code, 400)
        # The handler short-circuits at the missing-repository
        # check BEFORE constructing the watch manager, so
        # ``_FakeWatchManager.last_instance`` is still None.
        testbase.assert_equal(_FakeWatchManager.last_instance, None)
    finally:
        for p in (wm_patch, repo_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_watch_edit_post_translates_form_to_update_request():
    """
    **Feature: webworks projects watches T13.22 (p13s)**
    **Property: POST /watches/{wid}/edit translates the
    template form fields into a
    :class:`WatchUpdateRequest` whose ``conditions``,
    ``actions``, and ``enabled`` carry the parsed values; this
    replaces the F5-era ``_patch_watch_update_request_builder``
    workaround.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    wm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_watches,
            configure=_seed_pm,
        )

        def _seed_wm(instance: _FakeWatchManager) -> None:
            instance.get_watch_response = _FakeWatch(
                watch_id=42, project_id=7
            )
            return

        wm_patch = _patch_watch_manager(configure=_seed_wm)

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh"
            b"&name=renamed-watch"
            b"&description=updated+desc"
            b"&branch_pattern=feature%2F%2A"
            b"&action_type=trigger_pipeline"
            b"&action_spec_id=33"
            b"&enabled=true"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "watch_id": "42"},
            body=body,
        )
        response = projects_routes_watches.handle_watch_edit(request)
        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/watches/42"
        )

        wm = _FakeWatchManager.last_instance
        testbase.assert_equal(len(wm.update_watch_calls), 1)
        call = wm.update_watch_calls[0]
        testbase.assert_equal(call["watch_id"], 42)
        req_obj = call["request"]
        testbase.assert_equal(req_obj.name, "renamed-watch")
        testbase.assert_equal(req_obj.description, "updated desc")
        testbase.assert_equal(
            req_obj.conditions.branch_pattern, "feature/*"
        )
        testbase.assert_equal(len(req_obj.actions), 1)
        action0 = req_obj.actions[0]
        testbase.assert_equal(
            str(action0.action.value), "trigger_pipeline"
        )
        testbase.assert_equal(action0.target_id, 33)
        testbase.assert_equal(req_obj.enabled, True)
    finally:
        for p in (wm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return
