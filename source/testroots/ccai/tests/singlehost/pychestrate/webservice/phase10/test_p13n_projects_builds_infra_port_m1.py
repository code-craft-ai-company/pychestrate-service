"""
.. module:: test_p13n_projects_builds_infra_port_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the F3 slice of the projects port
               (builds + infrastructure).

.. moduleauthor:: Code Craft AI LLC

PR F3 ports the eight build routes plus the five infrastructure
routes. Tests cover registration, build_list (filter
passthrough), build_spec_create (POST happy + invalid-JSON
steps + developer-denied + missing project), build_detail
(happy + cross-project guard), build_logs (happy + step
filter), build_trigger (happy + manager-error), build_cancel
(happy + developer-denied), and the infrastructure list /
detail / logs read-only flows.
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
    routes_builds as projects_routes_builds,
    routes_infrastructure as projects_routes_infrastructure,
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


# ---- Project / build / infra fakes ----------------------------------------


class _FakeProject:
    def __init__(self, *, project_id: int, name: str = "p") -> None:
        self.id: int = project_id
        self.name: str = name
        return


class _FakeBuild:
    def __init__(self, *, build_id: int, project_id: int = 1) -> None:
        self.id: int = build_id
        self.project_id: int = project_id
        return


class _FakeBuildSpec:
    def __init__(self, *, spec_id: int, project_id: int = 1) -> None:
        self.id: int = spec_id
        self.project_id: int = project_id
        return


class _FakeInfraJob:
    def __init__(self, *, job_id: int, project_id: int = 1) -> None:
        self.id: int = job_id
        self.project_id: int = project_id
        return


class _FakeInfraSpec:
    def __init__(self, *, spec_id: int, project_id: int = 1) -> None:
        self.id: int = spec_id
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


class _FakeBuildManager:
    last_instance: Optional["_FakeBuildManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_builds_response: List[_FakeBuild] = []
        self.list_specs_response: List[_FakeBuildSpec] = []
        self.list_artifacts_response: List[Any] = []
        self.get_spec_response: Optional[_FakeBuildSpec] = None
        self.get_build_response: Optional[_FakeBuild] = None
        self.create_spec_response: Optional[_FakeBuildSpec] = None
        self.trigger_build_response: Optional[_FakeBuild] = None
        self.get_build_logs_response: Any = ""
        self.list_builds_calls: List[Dict[str, Any]] = []
        self.create_spec_calls: List[Any] = []
        self.trigger_build_calls: List[Any] = []
        self.cancel_build_calls: List[Any] = []
        self.get_build_logs_calls: List[Any] = []
        self.create_spec_raises: Optional[Exception] = None
        self.trigger_build_raises: Optional[Exception] = None
        self.cancel_build_raises: Optional[Exception] = None
        _FakeBuildManager.last_instance = self
        return

    def list_builds(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        self.list_builds_calls.append(kwargs)
        return SimpleNamespace(
            builds=self.list_builds_response,
            total=len(self.list_builds_response),
            offset=0,
            limit=len(self.list_builds_response),
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

    def get_spec(self, spec_id: int) -> Optional[_FakeBuildSpec]:
        return self.get_spec_response

    def get_build(self, build_id: int) -> Optional[_FakeBuild]:
        return self.get_build_response

    def list_artifacts(self, build_id: int) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            artifacts=self.list_artifacts_response,
            total=len(self.list_artifacts_response),
        )

    def create_spec(
            self, project_id: int, request: Any, user_id: str
        ) -> _FakeBuildSpec:
        self.create_spec_calls.append(
            (project_id, request, user_id)
        )
        if self.create_spec_raises is not None:
            raise self.create_spec_raises
        if self.create_spec_response is None:
            return _FakeBuildSpec(
                spec_id=99, project_id=project_id
            )
        return self.create_spec_response

    def trigger_build(
            self, request: Any, user_id: str
        ) -> _FakeBuild:
        self.trigger_build_calls.append((request, user_id))
        if self.trigger_build_raises is not None:
            raise self.trigger_build_raises
        if self.trigger_build_response is None:
            return _FakeBuild(build_id=42)
        return self.trigger_build_response

    def cancel_build(self, build_id: int, user_id: str) -> None:
        self.cancel_build_calls.append((build_id, user_id))
        if self.cancel_build_raises is not None:
            raise self.cancel_build_raises
        return

    def get_build_logs(
            self, build_id: int, *, step_name: Optional[str] = None
        ) -> Any:
        self.get_build_logs_calls.append(
            (build_id, step_name)
        )
        return self.get_build_logs_response


class _FakeRepositoryManager:
    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_repositories_response: List[Any] = []
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


class _FakeInfraManager:
    last_instance: Optional["_FakeInfraManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_jobs_response: List[_FakeInfraJob] = []
        self.list_specs_response: List[_FakeInfraSpec] = []
        self.get_job_response: Optional[_FakeInfraJob] = None
        self.get_spec_response: Optional[_FakeInfraSpec] = None
        self.get_job_logs_response: Any = ""
        self.list_jobs_calls: List[Dict[str, Any]] = []
        _FakeInfraManager.last_instance = self
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

    def get_job(self, job_id: int) -> Optional[_FakeInfraJob]:
        return self.get_job_response

    def get_spec(self, spec_id: int) -> Optional[_FakeInfraSpec]:
        return self.get_spec_response

    def get_job_logs(self, job_id: int) -> Any:
        return self.get_job_logs_response


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
    _FakeBuildManager.last_instance = None
    _FakeInfraManager.last_instance = None
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


def _patch_build_manager(
        *,
        configure: Optional[Callable[[_FakeBuildManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeBuildManager:
        instance = _FakeBuildManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        projects_routes_builds, "_build_build_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_repository_manager_for_builds() -> Any:
    def _builder(*, db_session: Any) -> _FakeRepositoryManager:
        return _FakeRepositoryManager(db_session)

    patch = create_module_patch(
        projects_routes_builds, "_build_repository_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_infra_manager(
        *,
        configure: Optional[Callable[[_FakeInfraManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeInfraManager:
        instance = _FakeInfraManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        projects_routes_infrastructure, "_build_infra_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_build_spec_create_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        projects_routes_builds, "_build_build_spec_create_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_build_trigger_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        projects_routes_builds, "_build_build_trigger_request"
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


def test_register_builds_routes_attaches_documented_routes():
    """
    **Feature: webworks projects builds T11.1 (F3)**
    **Property: register_builds_routes attaches the eight build
    routes at /projects/{id}/builds*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        projects_routes_builds.register_builds_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/projects/{project_id}/builds", ("GET",)),
            ("/projects/{project_id}/builds/specs", ("GET",)),
            (
                "/projects/{project_id}/builds/specs/create",
                ("GET", "POST"),
            ),
            (
                "/projects/{project_id}/builds/specs/{spec_id}",
                ("GET",),
            ),
            (
                "/projects/{project_id}/builds/{build_id}",
                ("GET",),
            ),
            (
                "/projects/{project_id}/builds/{build_id}/logs",
                ("GET",),
            ),
            (
                "/projects/{project_id}/builds/trigger",
                ("POST",),
            ),
            (
                "/projects/{project_id}/builds/{build_id}/cancel",
                ("POST",),
            ),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_infrastructure_routes_attaches_documented_routes():
    """
    **Feature: webworks projects infrastructure T11.2 (F3)**
    **Property: register_infrastructure_routes attaches the
    five infrastructure routes at /projects/{id}/infrastructure*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        projects_routes_infrastructure.register_infrastructure_routes(
            app=app
        )
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            (
                "/projects/{project_id}/infrastructure",
                ("GET",),
            ),
            (
                "/projects/{project_id}/infrastructure/specs",
                ("GET",),
            ),
            (
                "/projects/{project_id}/infrastructure/specs/{spec_id}",
                ("GET",),
            ),
            (
                "/projects/{project_id}/infrastructure/{job_id}",
                ("GET",),
            ),
            (
                "/projects/{project_id}/infrastructure/{job_id}/logs",
                ("GET",),
            ),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Builds
# ===========================================================================


def test_handle_build_list_passes_status_and_spec_filters():
    """
    **Feature: webworks projects builds T11.3 (F3)**
    **Property: GET /projects/{id}/builds passes status +
    spec_id + offset/limit through to BuildManager.list_builds.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    bm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(
                project_id=7
            )
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_builds,
            configure=_seed_pm,
        )
        bm_patch = _patch_build_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
            query_mapping={
                "status": "running", "spec_id": "3",
                "page": "2", "per_page": "10",
            },
        )
        response = projects_routes_builds.handle_build_list(request)

        testbase.assert_equal(response.status_code, 200)
        bm = _FakeBuildManager.last_instance
        kwargs = bm.list_builds_calls[0]
        testbase.assert_equal(kwargs["project_id"], 7)
        testbase.assert_equal(kwargs["spec_id"], 3)
        testbase.assert_equal(kwargs["status"], "running")
        testbase.assert_equal(kwargs["offset"], 10)
        testbase.assert_equal(kwargs["limit"], 10)
    finally:
        for p in (bm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_build_spec_create_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks projects builds T11.4 (F3)**
    **Property: A valid developer POST builds + creates the
    spec and redirects to /projects/{pid}/builds/specs/{sid}.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    bm_patch = None
    rm_patch = None
    cr_patch = None
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
            target_module=projects_routes_builds,
            configure=_seed_pm,
        )

        def _seed_bm(instance: _FakeBuildManager) -> None:
            instance.create_spec_response = _FakeBuildSpec(
                spec_id=42, project_id=7
            )
            return

        bm_patch = _patch_build_manager(configure=_seed_bm)
        rm_patch = _patch_repository_manager_for_builds()
        cr_patch = _patch_build_spec_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=ci-build"
            b"&repository_id=11&branch=main"
            b"&steps=%5B%7B%22run%22%3A+%22make%22%7D%5D"
            b"&environment=%7B%22DEBUG%22%3A+%221%22%7D"
            b"&timeout_minutes=30"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"project_id": "7"},
        )
        response = (
            projects_routes_builds.handle_build_spec_create(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/projects/7/builds/specs/42",
        )
        bm = _FakeBuildManager.last_instance
        proj_id, ar, user_id = bm.create_spec_calls[0]
        testbase.assert_equal(proj_id, 7)
        testbase.assert_equal(ar.name, "ci-build")
        testbase.assert_equal(ar.repository_id, 11)
        testbase.assert_equal(ar.branch, "main")
        testbase.assert_equal(
            ar.steps, [{"run": "make"}]
        )
        testbase.assert_equal(ar.environment, {"DEBUG": "1"})
        testbase.assert_equal(ar.timeout_minutes, 30)
    finally:
        for p in (cr_patch, rm_patch, bm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_build_spec_create_post_invalid_steps_json_re_renders():
    """
    **Feature: webworks projects builds T11.4 (F3)**
    **Property: A POST with non-JSON ``steps`` re-renders the
    form (400) with the documented error flash and does NOT
    invoke create_spec.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    bm_patch = None
    rm_patch = None
    cr_patch = None
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
            target_module=projects_routes_builds,
            configure=_seed_pm,
        )
        bm_patch = _patch_build_manager()
        rm_patch = _patch_repository_manager_for_builds()
        cr_patch = _patch_build_spec_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=ci-build&steps=not-json"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"project_id": "7"},
        )
        response = (
            projects_routes_builds.handle_build_spec_create(request)
        )

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        category, message = ctx["flashes"][0]
        testbase.assert_equal(category, "error")
        contains = "Invalid JSON" in message
        testbase.assert_equal(contains, True)
        bm = _FakeBuildManager.last_instance
        testbase.assert_equal(bm.create_spec_calls, [])
    finally:
        for p in (cr_patch, rm_patch, bm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_build_spec_create_developer_denied_redirects():
    """
    **Feature: webworks projects builds T11.4 (F3)**
    **Property: A non-developer user is redirected to
    /projects/{pid}.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            instance.default_check_permission_response = False
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_builds,
            configure=_seed,
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = (
            projects_routes_builds.handle_build_spec_create(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7"
        )
    finally:
        for p in (pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_build_detail_redirects_when_cross_project():
    """
    **Feature: webworks projects builds T11.5 (F3)**
    **Property: A build whose project_id does not match the
    URL's project_id is treated as not-found.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    bm_patch = None
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
            target_module=projects_routes_builds,
            configure=_seed_pm,
        )

        def _seed_bm(instance: _FakeBuildManager) -> None:
            instance.get_build_response = _FakeBuild(
                build_id=42, project_id=99
            )
            return

        bm_patch = _patch_build_manager(configure=_seed_bm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "build_id": "42"},
        )
        response = projects_routes_builds.handle_build_detail(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/builds"
        )
    finally:
        for p in (bm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_build_logs_passes_step_filter_through():
    """
    **Feature: webworks projects builds T11.6 (F3)**
    **Property: GET .../builds/{bid}/logs?step=test calls
    BuildManager.get_build_logs with step_name="test".**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    bm_patch = None
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
            target_module=projects_routes_builds,
            configure=_seed_pm,
        )

        def _seed_bm(instance: _FakeBuildManager) -> None:
            instance.get_build_response = _FakeBuild(
                build_id=42, project_id=7
            )
            instance.get_build_logs_response = "OK\n"
            return

        bm_patch = _patch_build_manager(configure=_seed_bm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "build_id": "42"},
            query_mapping={"step": "test"},
        )
        response = projects_routes_builds.handle_build_logs(request)

        testbase.assert_equal(response.status_code, 200)
        bm = _FakeBuildManager.last_instance
        testbase.assert_equal(
            bm.get_build_logs_calls, [(42, "test")]
        )
    finally:
        for p in (bm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_build_trigger_happy_path_redirects_to_new_build_detail():
    """
    **Feature: webworks projects builds T11.7 (F3)**
    **Property: A valid POST triggers the build and redirects
    to /projects/{pid}/builds/{new_id} naming the build id.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    bm_patch = None
    tr_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_builds,
        )

        def _seed(instance: _FakeBuildManager) -> None:
            instance.trigger_build_response = _FakeBuild(
                build_id=99, project_id=7
            )
            return

        bm_patch = _patch_build_manager(configure=_seed)
        tr_patch = _patch_build_trigger_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&spec_id=3"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"project_id": "7"},
        )
        response = projects_routes_builds.handle_build_trigger(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/builds/99"
        )
    finally:
        for p in (tr_patch, bm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_build_cancel_developer_denied_redirects():
    """
    **Feature: webworks projects builds T11.8 (F3)**
    **Property: A non-developer user cannot cancel a build --
    redirected to /projects/{pid}.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    bm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeProjectManager) -> None:
            instance.default_check_permission_response = False
            return

        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_builds,
            configure=_seed,
        )
        bm_patch = _patch_build_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"project_id": "7", "build_id": "42"},
        )
        response = projects_routes_builds.handle_build_cancel(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7"
        )
        # The deny redirect short-circuits before _build_build_manager,
        # so the manager is never constructed and last_instance stays
        # None.
        testbase.assert_equal(_FakeBuildManager.last_instance, None)
    finally:
        for p in (bm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_build_cancel_happy_path_redirects_to_build_detail():
    """
    **Feature: webworks projects builds T11.8 (F3)**
    **Property: A valid developer POST cancels the build and
    redirects to /projects/{pid}/builds/{bid}.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    bm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        pm_patch = _patch_project_manager_in(
            target_module=projects_routes_builds,
        )
        bm_patch = _patch_build_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"project_id": "7", "build_id": "42"},
        )
        response = projects_routes_builds.handle_build_cancel(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/builds/42"
        )
        bm = _FakeBuildManager.last_instance
        testbase.assert_equal(
            bm.cancel_build_calls, [(42, "u-admin")]
        )
    finally:
        for p in (bm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Infrastructure
# ===========================================================================


def test_handle_infra_job_list_passes_filters_through():
    """
    **Feature: webworks projects infrastructure T11.9 (F3)**
    **Property: GET .../infrastructure passes status + spec_id
    + offset/limit through to InfrastructureManager.list_jobs.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    im_patch = None
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
            target_module=projects_routes_infrastructure,
            configure=_seed_pm,
        )
        im_patch = _patch_infra_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
            query_mapping={
                "status": "succeeded", "spec_id": "5",
                "page": "1", "per_page": "20",
            },
        )
        response = (
            projects_routes_infrastructure.handle_infra_job_list(request)
        )

        testbase.assert_equal(response.status_code, 200)
        im = _FakeInfraManager.last_instance
        kwargs = im.list_jobs_calls[0]
        testbase.assert_equal(kwargs["project_id"], 7)
        testbase.assert_equal(kwargs["spec_id"], 5)
        testbase.assert_equal(kwargs["status"], "succeeded")
        testbase.assert_equal(kwargs["offset"], 0)
        testbase.assert_equal(kwargs["limit"], 20)
    finally:
        for p in (im_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_infra_job_detail_redirects_when_cross_project():
    """
    **Feature: webworks projects infrastructure T11.10 (F3)**
    **Property: A job whose project_id doesn't match yields a
    "not found" redirect.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    im_patch = None
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
            target_module=projects_routes_infrastructure,
            configure=_seed_pm,
        )

        def _seed_im(instance: _FakeInfraManager) -> None:
            instance.get_job_response = _FakeInfraJob(
                job_id=42, project_id=99
            )
            return

        im_patch = _patch_infra_manager(configure=_seed_im)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "job_id": "42"},
        )
        response = (
            projects_routes_infrastructure.handle_infra_job_detail(
                request
            )
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/projects/7/infrastructure",
        )
    finally:
        for p in (im_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_infra_job_logs_renders_with_logs():
    """
    **Feature: webworks projects infrastructure T11.11 (F3)**
    **Property: GET .../infrastructure/{jid}/logs renders the
    logs template with the manager output.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    im_patch = None
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
            target_module=projects_routes_infrastructure,
            configure=_seed_pm,
        )

        def _seed_im(instance: _FakeInfraManager) -> None:
            instance.get_job_response = _FakeInfraJob(
                job_id=42, project_id=7
            )
            instance.get_job_logs_response = "infra log lines"
            return

        im_patch = _patch_infra_manager(configure=_seed_im)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "job_id": "42"},
        )
        response = (
            projects_routes_infrastructure.handle_infra_job_logs(request)
        )

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["logs"], "infra log lines")
    finally:
        for p in (im_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return
