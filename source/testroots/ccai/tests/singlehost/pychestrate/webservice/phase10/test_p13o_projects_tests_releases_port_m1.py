"""
.. module:: test_p13o_projects_tests_releases_port_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the F4 slice of the projects port
               (tests + releases).

.. moduleauthor:: Code Craft AI LLC

PR F4 ports the five test routes plus the six release routes.
All routes are read-only -- test/release lifecycle goes through
the build pipeline + REST API, not the consumer UI.

Tests cover route registration, list+filter passthrough, detail
+ cross-project guard, results / artifacts / channels surfaces,
plus the unpaginated channel + schedule list endpoints.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


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
    routes_releases as projects_routes_releases,
    routes_tests as projects_routes_tests,
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


# ---- Project / test / release fakes ---------------------------------------


class _FakeProject:
    def __init__(self, *, project_id: int, name: str = "p") -> None:
        self.id: int = project_id
        self.name: str = name
        return


class _FakeTestJob:
    def __init__(self, *, job_id: int, project_id: int = 1) -> None:
        self.id: int = job_id
        self.project_id: int = project_id
        return


class _FakeTestSpec:
    def __init__(self, *, spec_id: int, project_id: int = 1) -> None:
        self.id: int = spec_id
        self.project_id: int = project_id
        return


class _FakeRelease:
    def __init__(
            self, *, release_id: int, project_id: int = 1
        ) -> None:
        self.id: int = release_id
        self.project_id: int = project_id
        return


class _FakePipeline:
    def __init__(
            self, *, pipeline_id: int, project_id: int = 1
        ) -> None:
        self.id: int = pipeline_id
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


class _FakeTestManager:
    last_instance: Optional["_FakeTestManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_jobs_response: List[_FakeTestJob] = []
        self.list_specs_response: List[_FakeTestSpec] = []
        self.get_spec_response: Optional[_FakeTestSpec] = None
        self.get_job_response: Optional[_FakeTestJob] = None
        self.get_test_results_response: Any = None
        self.get_job_logs_response: Any = ""
        self.list_jobs_calls: List[Dict[str, Any]] = []
        _FakeTestManager.last_instance = self
        return

    def list_jobs(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        self.list_jobs_calls.append(kwargs)
        return SimpleNamespace(
            jobs=self.list_jobs_response,
            total=len(self.list_jobs_response),
            offset=0,
            limit=len(self.list_jobs_response),
        )

    def list_specs(
            self, project_id: int, **kwargs: Any
        ) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            specs=self.list_specs_response,
            total=len(self.list_specs_response),
            offset=0,
            limit=len(self.list_specs_response),
        )

    def get_spec(self, spec_id: int) -> Optional[_FakeTestSpec]:
        return self.get_spec_response

    def get_job(self, job_id: int) -> Optional[_FakeTestJob]:
        return self.get_job_response

    def get_test_results(self, job_id: int) -> Any:
        return self.get_test_results_response

    def get_job_logs(self, job_id: int) -> Any:
        return self.get_job_logs_response


class _FakeReleaseManager:
    last_instance: Optional["_FakeReleaseManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_releases_response: List[_FakeRelease] = []
        self.get_release_response: Optional[_FakeRelease] = None
        self.list_artifacts_response: List[Any] = []
        self.list_channels_response: List[Any] = []
        self.list_pipelines_response: List[_FakePipeline] = []
        self.get_pipeline_response: Optional[_FakePipeline] = None
        self.list_pipeline_runs_response: List[Any] = []
        self.list_schedules_response: List[Any] = []
        self.list_releases_calls: List[Dict[str, Any]] = []
        _FakeReleaseManager.last_instance = self
        return

    def list_releases(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        self.list_releases_calls.append(kwargs)
        return SimpleNamespace(
            releases=self.list_releases_response,
            total=len(self.list_releases_response),
            offset=0,
            limit=len(self.list_releases_response),
        )

    def get_release(self, release_id: int) -> Optional[_FakeRelease]:
        return self.get_release_response

    def list_artifacts(self, release_id: int) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            artifacts=self.list_artifacts_response,
            total=len(self.list_artifacts_response),
        )

    def list_channels(self, project_id: int) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            channels=self.list_channels_response,
            total=len(self.list_channels_response),
        )

    def list_pipelines(
            self, project_id: int, **kwargs: Any
        ) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            pipelines=self.list_pipelines_response,
            total=len(self.list_pipelines_response),
            offset=0,
            limit=len(self.list_pipelines_response),
        )

    def get_pipeline(self, pipeline_id: int) -> Optional[_FakePipeline]:
        return self.get_pipeline_response

    def list_pipeline_runs(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            runs=self.list_pipeline_runs_response,
            total=len(self.list_pipeline_runs_response),
            offset=0,
            limit=len(self.list_pipeline_runs_response),
        )

    def list_schedules(self, project_id: int) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            schedules=self.list_schedules_response,
            total=len(self.list_schedules_response),
            offset=0,
            limit=len(self.list_schedules_response),
        )


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
    _FakeTestManager.last_instance = None
    _FakeReleaseManager.last_instance = None
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


def _patch_test_manager(
        *,
        configure: Optional[Callable[[_FakeTestManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeTestManager:
        instance = _FakeTestManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        projects_routes_tests, "_build_test_manager"
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
        projects_routes_releases, "_build_release_manager"
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


def test_register_tests_routes_attaches_documented_routes():
    """
    **Feature: webworks projects tests T12.1 (F4)**
    **Property: register_tests_routes attaches the five test
    routes at /projects/{id}/tests*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        projects_routes_tests.register_tests_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/projects/{project_id}/tests", ("GET",)),
            ("/projects/{project_id}/tests/specs", ("GET",)),
            (
                "/projects/{project_id}/tests/specs/{spec_id}",
                ("GET",),
            ),
            (
                "/projects/{project_id}/tests/{job_id}",
                ("GET",),
            ),
            (
                "/projects/{project_id}/tests/{job_id}/logs",
                ("GET",),
            ),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_releases_routes_attaches_documented_routes():
    """
    **Feature: webworks projects releases T12.2 (F4)**
    **Property: register_releases_routes attaches the six
    release routes at /projects/{id}/releases*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        projects_routes_releases.register_releases_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/projects/{project_id}/releases", ("GET",)),
            (
                "/projects/{project_id}/releases/{release_id}",
                ("GET",),
            ),
            (
                "/projects/{project_id}/releases/pipelines",
                ("GET",),
            ),
            (
                "/projects/{project_id}/releases/pipelines/{pipeline_id}",
                ("GET",),
            ),
            (
                "/projects/{project_id}/releases/channels",
                ("GET",),
            ),
            (
                "/projects/{project_id}/releases/schedules",
                ("GET",),
            ),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Tests
# ===========================================================================


def test_handle_test_job_list_passes_status_and_spec_filters():
    """
    **Feature: webworks projects tests T12.3 (F4)**
    **Property: GET .../tests passes status + spec_id +
    offset/limit through to TestManager.list_jobs.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    tm_patch = None
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
            target_module=projects_routes_tests, configure=_seed_pm
        )
        tm_patch = _patch_test_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
            query_mapping={
                "status": "succeeded", "spec_id": "5",
                "page": "2", "per_page": "10",
            },
        )
        response = projects_routes_tests.handle_test_job_list(request)

        testbase.assert_equal(response.status_code, 200)
        tm = _FakeTestManager.last_instance
        kwargs = tm.list_jobs_calls[0]
        testbase.assert_equal(kwargs["project_id"], 7)
        testbase.assert_equal(kwargs["spec_id"], 5)
        # The handler forwards the JobStatus str-enum member,
        # which compares equal to its string value.
        testbase.assert_equal(kwargs["status"], "succeeded")
        testbase.assert_equal(kwargs["offset"], 10)
        testbase.assert_equal(kwargs["limit"], 10)
    finally:
        for p in (tm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_test_job_detail_renders_with_results():
    """
    **Feature: webworks projects tests T12.4 (F4)**
    **Property: GET .../tests/{jid} renders the detail
    template with the job + results from TestManager.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    tm_patch = None
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
            target_module=projects_routes_tests, configure=_seed_pm
        )

        def _seed_tm(instance: _FakeTestManager) -> None:
            instance.get_job_response = _FakeTestJob(
                job_id=42, project_id=7
            )
            instance.get_test_results_response = {
                "passed": 5, "failed": 2,
            }
            return

        tm_patch = _patch_test_manager(configure=_seed_tm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "job_id": "42"},
        )
        response = projects_routes_tests.handle_test_job_detail(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["job"].id, 42)
        testbase.assert_equal(
            ctx["results"], {"passed": 5, "failed": 2}
        )
    finally:
        for p in (tm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_test_job_detail_redirects_when_cross_project():
    """
    **Feature: webworks projects tests T12.4 (F4)**
    **Property: A test job whose project_id doesn't match the
    URL is treated as not-found.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    tm_patch = None
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
            target_module=projects_routes_tests, configure=_seed_pm
        )

        def _seed_tm(instance: _FakeTestManager) -> None:
            instance.get_job_response = _FakeTestJob(
                job_id=42, project_id=99
            )
            return

        tm_patch = _patch_test_manager(configure=_seed_tm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "job_id": "42"},
        )
        response = projects_routes_tests.handle_test_job_detail(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/tests"
        )
    finally:
        for p in (tm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_test_job_logs_renders_with_logs():
    """
    **Feature: webworks projects tests T12.5 (F4)**
    **Property: GET .../tests/{jid}/logs renders the logs
    template with the manager output.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    tm_patch = None
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
            target_module=projects_routes_tests, configure=_seed_pm
        )

        def _seed_tm(instance: _FakeTestManager) -> None:
            instance.get_job_response = _FakeTestJob(
                job_id=42, project_id=7
            )
            instance.get_job_logs_response = "test log lines"
            return

        tm_patch = _patch_test_manager(configure=_seed_tm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "job_id": "42"},
        )
        response = projects_routes_tests.handle_test_job_logs(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["logs"], "test log lines")
    finally:
        for p in (tm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Releases
# ===========================================================================


def test_handle_release_list_passes_status_and_channel_filters():
    """
    **Feature: webworks projects releases T12.6 (F4)**
    **Property: GET .../releases passes status + channel +
    offset/limit through to ReleaseManager.list_releases.**
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
            target_module=projects_routes_releases,
            configure=_seed_pm,
        )
        rm_patch = _patch_release_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
            query_mapping={
                "status": "published", "channel_id": "3",
                "page": "1", "per_page": "20",
            },
        )
        response = (
            projects_routes_releases.handle_release_list(request)
        )

        testbase.assert_equal(response.status_code, 200)
        rm = _FakeReleaseManager.last_instance
        kwargs = rm.list_releases_calls[0]
        testbase.assert_equal(kwargs["project_id"], 7)
        # The handler forwards the ReleaseStatus str-enum member,
        # which compares equal to its string value; the channel
        # filter matches the manager's real ``channel_id`` kwarg
        # (the legacy ``channel=`` kwarg was a TypeError).
        testbase.assert_equal(kwargs["status"], "published")
        testbase.assert_equal(kwargs["channel_id"], 3)
        testbase.assert_equal(kwargs["offset"], 0)
        testbase.assert_equal(kwargs["limit"], 20)
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_release_detail_renders_with_artifacts_and_channels():
    """
    **Feature: webworks projects releases T12.7 (F4)**
    **Property: GET .../releases/{rid} renders the detail
    template with the release + artifacts + channels.**
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
            target_module=projects_routes_releases,
            configure=_seed_pm,
        )

        def _seed_rm(instance: _FakeReleaseManager) -> None:
            instance.get_release_response = _FakeRelease(
                release_id=42, project_id=7
            )
            instance.list_artifacts_response = ["binary.tar.gz"]
            instance.list_channels_response = ["stable", "beta"]
            return

        rm_patch = _patch_release_manager(configure=_seed_rm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "release_id": "42"},
        )
        response = (
            projects_routes_releases.handle_release_detail(request)
        )

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["release"].id, 42)
        testbase.assert_equal(ctx["artifacts"], ["binary.tar.gz"])
        testbase.assert_equal(ctx["channels"], ["stable", "beta"])
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_pipeline_detail_redirects_when_cross_project():
    """
    **Feature: webworks projects releases T12.8 (F4)**
    **Property: A pipeline whose project_id doesn't match is
    treated as not-found.**
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
            target_module=projects_routes_releases,
            configure=_seed_pm,
        )

        def _seed_rm(instance: _FakeReleaseManager) -> None:
            instance.get_pipeline_response = _FakePipeline(
                pipeline_id=11, project_id=99
            )
            return

        rm_patch = _patch_release_manager(configure=_seed_rm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={
                "project_id": "7", "pipeline_id": "11"
            },
        )
        response = (
            projects_routes_releases.handle_pipeline_detail(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/projects/7/releases/pipelines",
        )
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_channel_list_renders_unpaginated_channels():
    """
    **Feature: webworks projects releases T12.9 (F4)**
    **Property: GET .../releases/channels renders the
    channel_list template (unpaginated; channels are typically
    a small set).**
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
            target_module=projects_routes_releases,
            configure=_seed_pm,
        )

        def _seed_rm(instance: _FakeReleaseManager) -> None:
            instance.list_channels_response = [
                "stable", "beta", "edge"
            ]
            return

        rm_patch = _patch_release_manager(configure=_seed_rm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = (
            projects_routes_releases.handle_channel_list(request)
        )

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(
            ctx["channels"], ["stable", "beta", "edge"]
        )
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_schedule_list_renders_unpaginated_schedules():
    """
    **Feature: webworks projects releases T12.10 (F4)**
    **Property: GET .../releases/schedules renders the
    schedule_list template (unpaginated).**
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
            target_module=projects_routes_releases,
            configure=_seed_pm,
        )

        def _seed_rm(instance: _FakeReleaseManager) -> None:
            instance.list_schedules_response = [
                {"name": "nightly"}, {"name": "weekly"},
            ]
            return

        rm_patch = _patch_release_manager(configure=_seed_rm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = (
            projects_routes_releases.handle_schedule_list(request)
        )

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["schedules"]), 2)
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return
