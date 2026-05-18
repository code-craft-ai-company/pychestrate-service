"""
.. module:: test_p13l_projects_core_members_port_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the F1 slice of the projects port
               (dashboard + project core + members).

.. moduleauthor:: Automation Mojo LLC

PR F1 begins the /projects blueprint port. Lands the dashboard
+ the project-core CRUD (list / create / detail / edit /
delete) + the four member-management handlers.

Tests cover:

* register_projects_routes -- documented route attachment +
  F2/F3/F4/F5 future-endpoint pre-registration.
* dashboard -- happy + anonymous redirect.
* project_list -- pagination + search filter passthrough.
* project_create -- GET form, POST happy + invalid-JSON +
  CSRF.
* project_detail -- happy + 404 + view-permission denied.
* project_edit -- POST happy + admin-permission denied.
* project_delete -- happy + owner-permission denied.
* member_list -- happy + can_manage flag toggling.
* member_add -- POST happy + admin-permission denied + missing
  user_id error.
* member_edit -- POST happy + member-not-found.
* member_remove -- happy + admin-permission denied.
* _require_project_permission_or_redirect helper -- allowed,
  denied, exception-as-denial.
* _parse_metadata_json_or_default helper.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from automojo import testbase
from automojo.testbase.mocking import create_module_patch
from automojo.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from automojo.pychestrate.webservice.webinterface.blueprints.config import (
    routes as config_routes,
)
from automojo.pychestrate.webservice.webinterface.blueprints.projects import (
    routes as projects_routes,
)
from automojo.pychestrate.webservice.webinterface.foundation import (
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
    """
        Auth-side SecurityManager stand-in. The projects
        handlers use ProjectManager.check_permission for project-
        scoped writes, so this fake's check_permission isn't
        consulted.
    """

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


# ---- Project-domain fakes -------------------------------------------------


class _FakeProject:
    def __init__(self, *, project_id: int, name: str = "p") -> None:
        self.id: int = project_id
        self.name: str = name
        self.description: str = ""
        return


class _FakeMember:
    def __init__(self, *, user_id: int, role: str = "viewer") -> None:
        self.user_id: int = user_id
        self.role: str = role
        return


class _FakeUser:
    def __init__(self, *, user_id: int, username: str = "u") -> None:
        self.id: int = user_id
        self.username: str = username
        return


class _FakeUserListResponse:
    def __init__(self, *, users: List[_FakeUser]) -> None:
        self.users: List[_FakeUser] = users
        return


class _FakeProjectManager:
    last_instance: Optional["_FakeProjectManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_projects_response: List[_FakeProject] = []
        self.get_project_response: Optional[_FakeProject] = None
        self.create_project_response: Optional[_FakeProject] = None
        self.list_members_response: List[_FakeMember] = []
        self.check_permission_responses: Dict[str, bool] = {}
        # Default: all permissions allowed.
        self.default_check_permission_response: bool = True
        self.check_permission_raises: Optional[Exception] = None
        self.list_projects_calls: List[Dict[str, Any]] = []
        self.create_project_calls: List[Any] = []
        self.update_project_calls: List[Any] = []
        self.delete_project_calls: List[Any] = []
        self.add_member_calls: List[Any] = []
        self.update_member_role_calls: List[Any] = []
        self.remove_member_calls: List[Any] = []
        self.create_project_raises: Optional[Exception] = None
        self.update_project_raises: Optional[Exception] = None
        self.delete_project_raises: Optional[Exception] = None
        self.add_member_raises: Optional[Exception] = None
        self.update_member_role_raises: Optional[Exception] = None
        self.remove_member_raises: Optional[Exception] = None
        _FakeProjectManager.last_instance = self
        return

    def list_projects(
            self, user_id: str, **kwargs: Any
        ) -> Any:
        from types import SimpleNamespace
        self.list_projects_calls.append(
            {"user_id": user_id, **kwargs}
        )
        return SimpleNamespace(
            projects=self.list_projects_response,
            total=len(self.list_projects_response),
            offset=0,
            limit=len(self.list_projects_response),
        )

    def get_project(self, project_id: int) -> Optional[_FakeProject]:
        return self.get_project_response

    def check_permission(
            self, project_id: int, user_id: str, permission: str
        ) -> bool:
        if self.check_permission_raises is not None:
            raise self.check_permission_raises
        return self.check_permission_responses.get(
            permission, self.default_check_permission_response
        )

    def create_project(
            self, request: Any, user_id: str
        ) -> _FakeProject:
        self.create_project_calls.append((request, user_id))
        if self.create_project_raises is not None:
            raise self.create_project_raises
        if self.create_project_response is None:
            return _FakeProject(project_id=99, name=request.name)
        return self.create_project_response

    def update_project(
            self, project_id: int, request: Any, user_id: str
        ) -> None:
        self.update_project_calls.append(
            (project_id, request, user_id)
        )
        if self.update_project_raises is not None:
            raise self.update_project_raises
        return

    def delete_project(self, project_id: int, user_id: str) -> None:
        self.delete_project_calls.append((project_id, user_id))
        if self.delete_project_raises is not None:
            raise self.delete_project_raises
        return

    def list_members(
            self, project_id: int, **kwargs: Any
        ) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            members=self.list_members_response,
            total=len(self.list_members_response),
            offset=0,
            limit=len(self.list_members_response),
        )

    def add_member(
            self, project_id: int, target_user_id: int,
            role: Any, user_id: str
        ) -> None:
        self.add_member_calls.append(
            (project_id, target_user_id, role, user_id)
        )
        if self.add_member_raises is not None:
            raise self.add_member_raises
        return

    def update_member_role(
            self, project_id: int, target_user_id: int,
            role: Any, user_id: str
        ) -> None:
        self.update_member_role_calls.append(
            (project_id, target_user_id, role, user_id)
        )
        if self.update_member_role_raises is not None:
            raise self.update_member_role_raises
        return

    def remove_member(
            self, project_id: int, target_user_id: int, user_id: str
        ) -> None:
        self.remove_member_calls.append(
            (project_id, target_user_id, user_id)
        )
        if self.remove_member_raises is not None:
            raise self.remove_member_raises
        return


class _FakeUserManager:
    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_users_response: _FakeUserListResponse = (
            _FakeUserListResponse(users=[])
        )
        return

    def list_users(self, **kwargs: Any) -> _FakeUserListResponse:
        return self.list_users_response


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


class _FakeBuildManager:
    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_builds_response: List[Any] = []
        return

    def list_builds(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            builds=self.list_builds_response,
            total=len(self.list_builds_response),
            offset=0,
            limit=len(self.list_builds_response),
        )


class _FakeTestManager:
    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_jobs_response: List[Any] = []
        return

    def list_jobs(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            jobs=self.list_jobs_response,
            total=len(self.list_jobs_response),
            offset=0,
            limit=len(self.list_jobs_response),
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


def _patch_project_manager(
        *,
        configure: Optional[Callable[[_FakeProjectManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeProjectManager:
        instance = _FakeProjectManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        projects_routes, "_build_project_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_user_manager(*, users: Optional[List[_FakeUser]] = None) -> Any:
    def _builder(*, db_session: Any) -> _FakeUserManager:
        instance = _FakeUserManager(db_session)
        instance.list_users_response = _FakeUserListResponse(
            users=users if users is not None else []
        )
        return instance

    patch = create_module_patch(
        projects_routes, "_build_user_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_repository_manager() -> Any:
    def _builder(*, db_session: Any) -> _FakeRepositoryManager:
        return _FakeRepositoryManager(db_session)

    patch = create_module_patch(
        projects_routes, "_build_repository_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_build_manager() -> Any:
    def _builder(*, db_session: Any) -> _FakeBuildManager:
        return _FakeBuildManager(db_session)

    patch = create_module_patch(
        projects_routes, "_build_build_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_test_manager() -> Any:
    def _builder(*, db_session: Any) -> _FakeTestManager:
        return _FakeTestManager(db_session)

    patch = create_module_patch(
        projects_routes, "_build_test_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_project_create_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        projects_routes, "_build_project_create_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_project_update_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        projects_routes, "_build_project_update_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_project_role_resolver() -> Any:
    def _resolve(*, role_str: str) -> Any:
        return type("PR", (), {"value": role_str})()

    patch = create_module_patch(
        projects_routes, "_resolve_project_role"
    )
    mock = patch.activate()
    mock.configure(side_effect=_resolve)
    return patch


def _patch_project_role_enumerator() -> Any:
    def _enum() -> List[str]:
        return ["viewer", "contributor", "admin", "owner"]

    patch = create_module_patch(
        projects_routes, "_enumerate_project_role_values"
    )
    mock = patch.activate()
    mock.configure(side_effect=_enum)
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
    """
        Register every config + projects endpoint into the
        url_for shim. (Resources is not registered here -- F1
        handlers don't reference resources endpoints.)
    """
    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (
        register_config_routes,
    )
    app = _FakeApp()
    register_config_routes(app=app)
    projects_routes.register_projects_routes(app=app)
    return


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_projects_routes_attaches_documented_routes():
    """
    **Feature: webworks projects port T9.1 (F1)**
    **Property: register_projects_routes attaches the eleven
    documented F1 routes (dashboard root + /dashboard, /list,
    /create GET+POST, /<id>, /<id>/edit GET+POST, /<id>/delete,
    /<id>/members, /<id>/members/add GET+POST, /<id>/members/
    <uid>/edit GET+POST, /<id>/members/<uid>/remove) at
    /projects/*. Asserted as a SUBSET so future per-feature
    PRs (F2/F3/F4/F5) that dispatch from the same registrar do
    not break this contract.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        projects_routes.register_projects_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected_subset = {
            ("/projects", ("GET",)),
            ("/projects/dashboard", ("GET",)),
            ("/projects/list", ("GET",)),
            ("/projects/create", ("GET", "POST")),
            ("/projects/{project_id}", ("GET",)),
            ("/projects/{project_id}/edit", ("GET", "POST")),
            ("/projects/{project_id}/delete", ("POST",)),
            ("/projects/{project_id}/members", ("GET",)),
            (
                "/projects/{project_id}/members/add",
                ("GET", "POST"),
            ),
            (
                "/projects/{project_id}/members/{user_id}/edit",
                ("GET", "POST"),
            ),
            (
                "/projects/{project_id}/members/{user_id}/remove",
                ("POST",),
            ),
        }
        missing = expected_subset - actual
        testbase.assert_equal(missing, set())
    finally:
        _reset_global_state()
    return


def test_register_projects_routes_pre_registers_future_endpoints():
    """
    **Feature: webworks projects port T9.1 (F1)**
    **Property: register_projects_routes pre-registers the
    F2/F3/F4/F5 endpoint patterns so the dashboard sidebar's
    url_for(...) calls resolve before those handlers ship.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        projects_routes.register_projects_routes(app=app)
        snapshot = url_for_module.get_registry_snapshot()
        for endpoint in (
            "projects.repository_list",
            "projects.build_list",
            "projects.infra_job_list",
            "projects.test_job_list",
            "projects.release_list",
            "projects.pipeline_list",
            "projects.channel_list",
            "projects.schedule_list",
            "projects.calendar_view",
            "projects.watch_list",
        ):
            testbase.assert_equal(endpoint in snapshot, True)
        testbase.assert_equal(
            snapshot["projects.build_detail"],
            "/projects/{project_id}/builds/{build_id}",
        )
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Helpers
# ===========================================================================


def test_parse_metadata_json_or_default_handles_empty_and_valid():
    """
    **Feature: F1 helpers T9.2**
    **Property: Empty input returns the default; valid JSON
    object parses; non-JSON / non-object input raises
    ValueError.**
    """
    parse = projects_routes._parse_metadata_json_or_default
    testbase.assert_equal(parse(raw="", default={}), {})
    testbase.assert_equal(parse(raw=None, default=None), None)
    testbase.assert_equal(
        parse(raw='{"k": "v"}', default={}), {"k": "v"}
    )
    raised = False
    try:
        parse(raw="not json", default={})
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_require_project_permission_or_redirect_returns_none_when_allowed():
    """
    **Feature: F1 helpers T9.3**
    **Property: When ProjectManager.check_permission returns
    True, the helper returns None and the handler proceeds.**
    """
    _reset_global_state()
    try:
        _install_ui_cookie_secret()
        pm = _FakeProjectManager(db_session=None)
        pm.default_check_permission_response = True
        auth = config_routes._AuthResolution(
            redirect_response=None,
            session={},
            db_session=None,
            user_id="u-admin",
            username="admin",
            csrf_token="csrf",
        )
        result = (
            projects_routes._require_project_permission_or_redirect(
                project_manager=pm,
                auth=auth,
                project_id=7,
                permission="admin",
                deny_redirect_url="/projects",
            )
        )
        testbase.assert_equal(result, None)
    finally:
        _reset_global_state()
    return


def test_require_project_permission_or_redirect_redirects_when_denied():
    """
    **Feature: F1 helpers T9.3**
    **Property: When check_permission returns False, the
    helper returns a 302 redirect to the deny URL with an
    error flash on the session.**
    """
    _reset_global_state()
    try:
        _install_ui_cookie_secret()
        pm = _FakeProjectManager(db_session=None)
        pm.default_check_permission_response = False
        auth = config_routes._AuthResolution(
            redirect_response=None,
            session={},
            db_session=None,
            user_id="u-viewer",
            username="viewer",
            csrf_token="csrf",
        )
        result = (
            projects_routes._require_project_permission_or_redirect(
                project_manager=pm,
                auth=auth,
                project_id=7,
                permission="admin",
                deny_redirect_url="/projects/7",
            )
        )
        is_redirect = isinstance(result, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(result.headers["Location"], "/projects/7")
        queue = auth.session[flash.SESSION_KEY]
        testbase.assert_equal(queue[0][0], "error")
    finally:
        _reset_global_state()
    return


def test_require_project_permission_or_redirect_treats_exception_as_denial():
    """
    **Feature: F1 helpers T9.3**
    **Property: An exception from check_permission is treated
    as denial -- no fail-open path.**
    """
    _reset_global_state()
    try:
        _install_ui_cookie_secret()
        pm = _FakeProjectManager(db_session=None)
        pm.check_permission_raises = RuntimeError("DB exploded")
        auth = config_routes._AuthResolution(
            redirect_response=None,
            session={},
            db_session=None,
            user_id="u-admin",
            username="admin",
            csrf_token="csrf",
        )
        result = (
            projects_routes._require_project_permission_or_redirect(
                project_manager=pm,
                auth=auth,
                project_id=7,
                permission="admin",
                deny_redirect_url="/projects/7",
            )
        )
        is_redirect = isinstance(result, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Dashboard
# ===========================================================================


def test_handle_dashboard_renders_with_user_projects():
    """
    **Feature: webworks projects port T9.4 (F1)**
    **Property: GET /projects/ renders projects/dashboard.html
    with the user's project list.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeProjectManager) -> None:
            instance.list_projects_response = [
                _FakeProject(project_id=1, name="alpha"),
                _FakeProject(project_id=2, name="beta"),
            ]
            return

        pm_patch = _patch_project_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = projects_routes.handle_dashboard(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["projects/dashboard.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["projects"]), 2)
    finally:
        for p in (pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_dashboard_redirects_anonymous_to_config_login():
    """
    **Feature: webworks projects port T9.4 (F1)**
    **Property: An unauthenticated request redirects to
    /login (the shared login URL).**
    """
    _reset_global_state()
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _register_url_for_endpoints()
        request = _FakeRequest(cookies={})
        response = projects_routes.handle_dashboard(request)
        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/login"
        )
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Project list / create
# ===========================================================================


def test_handle_project_list_passes_search_and_pagination():
    """
    **Feature: webworks projects port T9.5 (F1)**
    **Property: GET /projects/list passes search + offset/limit
    through to ProjectManager.list_projects.**
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
        pm_patch = _patch_project_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            query_mapping={
                "page": "2", "per_page": "10", "search": "alph",
            },
        )
        response = projects_routes.handle_project_list(request)

        testbase.assert_equal(response.status_code, 200)
        pm = _FakeProjectManager.last_instance
        kwargs = pm.list_projects_calls[0]
        testbase.assert_equal(kwargs["offset"], 10)
        testbase.assert_equal(kwargs["limit"], 10)
        testbase.assert_equal(kwargs["search"], "alph")
    finally:
        for p in (pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_project_create_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks projects port T9.6 (F1)**
    **Property: A valid POST creates the project and redirects
    to /projects/{new_id}.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    cr_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeProjectManager) -> None:
            instance.create_project_response = _FakeProject(
                project_id=42, name="alpha"
            )
            return

        pm_patch = _patch_project_manager(configure=_seed)
        cr_patch = _patch_project_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=alpha"
            b"&description=Alpha+project"
            b"&metadata=%7B%22team%22%3A+%22A%22%7D"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = projects_routes.handle_project_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/42"
        )
        pm = _FakeProjectManager.last_instance
        ar, user_id = pm.create_project_calls[0]
        testbase.assert_equal(ar.name, "alpha")
        testbase.assert_equal(ar.metadata, {"team": "A"})
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (cr_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_project_create_post_invalid_metadata_json_re_renders():
    """
    **Feature: webworks projects port T9.6 (F1)**
    **Property: A POST with non-JSON metadata yields a 400
    re-render with an error flash; create_project not called.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    cr_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        pm_patch = _patch_project_manager()
        cr_patch = _patch_project_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&name=alpha&metadata=not-json"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = projects_routes.handle_project_create(request)

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        category, message = ctx["flashes"][0]
        testbase.assert_equal(category, "error")
        contains = "Invalid JSON" in message
        testbase.assert_equal(contains, True)
        # ProjectManager construction is deferred until after the
        # metadata parse succeeds; on the JSON-error path the
        # handler bails out before constructing the manager.
        testbase.assert_equal(_FakeProjectManager.last_instance, None)
    finally:
        for p in (cr_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Project detail / edit / delete
# ===========================================================================


def test_handle_project_detail_renders_when_project_found_and_view_allowed():
    """
    **Feature: webworks projects port T9.7 (F1)**
    **Property: GET /projects/{id} renders the detail template
    with the resolved project + summary panels (repos / builds /
    tests / members).**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    rep_patch = None
    bm_patch = None
    tm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(
                project_id=7, name="alpha"
            )
            instance.list_members_response = [
                _FakeMember(user_id=1, role="admin")
            ]
            return

        pm_patch = _patch_project_manager(configure=_seed)
        rep_patch = _patch_repository_manager()
        bm_patch = _patch_build_manager()
        tm_patch = _patch_test_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = projects_routes.handle_project_detail(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["project"].id, 7)
        testbase.assert_equal(len(ctx["members"]), 1)
    finally:
        for p in (tm_patch, bm_patch, rep_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_project_detail_redirects_when_view_denied():
    """
    **Feature: webworks projects port T9.7 (F1)**
    **Property: A user without ``view`` permission is
    redirected to /projects/list with an error flash.**
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
            instance.get_project_response = _FakeProject(
                project_id=7, name="alpha"
            )
            instance.default_check_permission_response = False
            return

        pm_patch = _patch_project_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = projects_routes.handle_project_detail(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/list"
        )
    finally:
        for p in (pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_project_edit_post_admin_required():
    """
    **Feature: webworks projects port T9.8 (F1)**
    **Property: A user without ``admin`` permission cannot
    POST an edit -- redirects to /projects/{id}.**
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
            instance.get_project_response = _FakeProject(
                project_id=7, name="alpha"
            )
            instance.default_check_permission_response = False
            return

        pm_patch = _patch_project_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"project_id": "7"},
        )
        response = projects_routes.handle_project_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7"
        )
        pm = _FakeProjectManager.last_instance
        testbase.assert_equal(pm.update_project_calls, [])
    finally:
        for p in (pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_project_edit_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks projects port T9.8 (F1)**
    **Property: A valid admin POST calls update_project and
    redirects to /projects/{id} with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    upd_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(
                project_id=7, name="alpha"
            )
            return

        pm_patch = _patch_project_manager(configure=_seed)
        upd_patch = _patch_project_update_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=alpha-renamed"
            b"&description=Updated+description"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"project_id": "7"},
        )
        response = projects_routes.handle_project_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7"
        )
        pm = _FakeProjectManager.last_instance
        testbase.assert_equal(len(pm.update_project_calls), 1)
        target_id, ar, user_id = pm.update_project_calls[0]
        testbase.assert_equal(target_id, 7)
        testbase.assert_equal(ar.name, "alpha-renamed")
    finally:
        for p in (upd_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_project_delete_owner_required():
    """
    **Feature: webworks projects port T9.9 (F1)**
    **Property: A user without ``owner`` permission cannot
    delete -- redirects to /projects/{id}.**
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
            instance.default_check_permission_response = False
            return

        pm_patch = _patch_project_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"project_id": "7"},
        )
        response = projects_routes.handle_project_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7"
        )
        pm = _FakeProjectManager.last_instance
        testbase.assert_equal(pm.delete_project_calls, [])
    finally:
        for p in (pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_project_delete_happy_path_redirects_to_list():
    """
    **Feature: webworks projects port T9.9 (F1)**
    **Property: A valid owner POST calls delete_project and
    redirects to /projects/list.**
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
        pm_patch = _patch_project_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"project_id": "7"},
        )
        response = projects_routes.handle_project_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/list"
        )
        pm = _FakeProjectManager.last_instance
        testbase.assert_equal(
            pm.delete_project_calls, [(7, "u-admin")]
        )
    finally:
        for p in (pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Members
# ===========================================================================


def test_handle_member_list_renders_with_can_manage_flag():
    """
    **Feature: webworks projects port T9.10 (F1)**
    **Property: GET /projects/{id}/members renders members/
    list.html with project + members + can_manage from a
    second permission probe (``admin``).**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(
                project_id=7, name="alpha"
            )
            instance.list_members_response = [
                _FakeMember(user_id=1, role="admin"),
                _FakeMember(user_id=2, role="viewer"),
            ]
            instance.check_permission_responses = {
                "view": True,
                "admin": True,
            }
            return

        pm_patch = _patch_project_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = projects_routes.handle_member_list(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["members"]), 2)
        testbase.assert_equal(ctx["can_manage"], True)
    finally:
        for p in (pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_member_add_post_happy_path_redirects_to_member_list():
    """
    **Feature: webworks projects port T9.11 (F1)**
    **Property: A valid POST calls add_member and redirects to
    /projects/{id}/members with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    role_patch = None
    enum_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(
                project_id=7, name="alpha"
            )
            return

        pm_patch = _patch_project_manager(configure=_seed)
        role_patch = _patch_project_role_resolver()
        enum_patch = _patch_project_role_enumerator()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&user_id=11&role=contributor"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"project_id": "7"},
        )
        response = projects_routes.handle_member_add(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/members"
        )
        pm = _FakeProjectManager.last_instance
        testbase.assert_equal(len(pm.add_member_calls), 1)
        proj_id, target_uid, role, user_id = pm.add_member_calls[0]
        testbase.assert_equal(proj_id, 7)
        testbase.assert_equal(target_uid, 11)
        testbase.assert_equal(role.value, "contributor")
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (enum_patch, role_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_member_add_admin_denied_redirects():
    """
    **Feature: webworks projects port T9.11 (F1)**
    **Property: A user without ``admin`` permission cannot
    reach the member-add page; redirects to /projects/{id}.**
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
            instance.get_project_response = _FakeProject(
                project_id=7, name="alpha"
            )
            instance.default_check_permission_response = False
            return

        pm_patch = _patch_project_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = projects_routes.handle_member_add(request)

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


def test_handle_member_edit_post_happy_path_calls_update_member_role():
    """
    **Feature: webworks projects port T9.12 (F1)**
    **Property: A valid POST calls update_member_role with the
    resolved role + redirects to /projects/{id}/members.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    role_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(
                project_id=7, name="alpha"
            )
            instance.list_members_response = [
                _FakeMember(user_id=11, role="viewer"),
            ]
            return

        pm_patch = _patch_project_manager(configure=_seed)
        role_patch = _patch_project_role_resolver()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&role=admin"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"project_id": "7", "user_id": "11"},
        )
        response = projects_routes.handle_member_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/members"
        )
        pm = _FakeProjectManager.last_instance
        testbase.assert_equal(len(pm.update_member_role_calls), 1)
        proj_id, target_uid, role, user_id = (
            pm.update_member_role_calls[0]
        )
        testbase.assert_equal(proj_id, 7)
        testbase.assert_equal(target_uid, 11)
        testbase.assert_equal(role.value, "admin")
    finally:
        for p in (role_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_member_remove_happy_path_redirects_to_member_list():
    """
    **Feature: webworks projects port T9.13 (F1)**
    **Property: A valid POST calls remove_member and redirects
    to /projects/{id}/members with a success flash.**
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
        pm_patch = _patch_project_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"project_id": "7", "user_id": "11"},
        )
        response = projects_routes.handle_member_remove(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7/members"
        )
        pm = _FakeProjectManager.last_instance
        testbase.assert_equal(
            pm.remove_member_calls, [(7, 11, "u-admin")]
        )
    finally:
        for p in (pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return
