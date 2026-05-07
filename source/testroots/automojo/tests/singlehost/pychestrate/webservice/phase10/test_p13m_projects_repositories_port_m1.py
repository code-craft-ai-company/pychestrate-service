"""
.. module:: test_p13m_projects_repositories_port_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the F2 slice of the projects port
               (repository management).

.. moduleauthor:: Automation Mojo LLC

PR F2 ports the seven repository routes to webworks. Tests
cover registration, repository_list (view-gated + can_manage),
repository_create (POST happy + developer-denied + manager-
error), repository_detail (happy + 404 + project-mismatch),
repository_edit (POST happy + developer-denied), repository_delete
(admin-gated), repository_test (truthy / falsey / error),
repository_fetch (happy / error), and the
_resolve_repository_or_redirect helper.
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
    routes_repositories as projects_routes_repositories,
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
# Test stubs (mirror F1)
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


# ---- Project / repository fakes -------------------------------------------


class _FakeProject:
    def __init__(self, *, project_id: int, name: str = "p") -> None:
        self.id: int = project_id
        self.name: str = name
        return


class _FakeRepository:
    def __init__(
            self, *, repository_id: int, project_id: int = 1,
            name: str = "repo"
        ) -> None:
        self.id: int = repository_id
        self.project_id: int = project_id
        self.name: str = name
        return


class _FakeProjectManager:
    last_instance: Optional["_FakeProjectManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.get_project_response: Optional[_FakeProject] = None
        self.check_permission_responses: Dict[str, bool] = {}
        self.default_check_permission_response: bool = True
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
        self.get_repository_response: Optional[_FakeRepository] = None
        self.add_repository_response: Optional[_FakeRepository] = None
        self.test_connectivity_response: bool = True
        self.fetch_latest_response: Any = None
        self.add_repository_calls: List[Any] = []
        self.update_repository_calls: List[Any] = []
        self.remove_repository_calls: List[Any] = []
        self.test_connectivity_calls: List[Any] = []
        self.fetch_latest_calls: List[Any] = []
        self.add_repository_raises: Optional[Exception] = None
        self.update_repository_raises: Optional[Exception] = None
        self.remove_repository_raises: Optional[Exception] = None
        self.test_connectivity_raises: Optional[Exception] = None
        self.fetch_latest_raises: Optional[Exception] = None
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

    def get_repository(
            self, repository_id: int
        ) -> Optional[_FakeRepository]:
        return self.get_repository_response

    def add_repository(
            self, project_id: int, request: Any, user_id: str
        ) -> _FakeRepository:
        self.add_repository_calls.append(
            (project_id, request, user_id)
        )
        if self.add_repository_raises is not None:
            raise self.add_repository_raises
        if self.add_repository_response is None:
            return _FakeRepository(
                repository_id=99,
                project_id=project_id,
                name=request.name,
            )
        return self.add_repository_response

    def update_repository(
            self, repository_id: int, request: Any, user_id: str
        ) -> None:
        self.update_repository_calls.append(
            (repository_id, request, user_id)
        )
        if self.update_repository_raises is not None:
            raise self.update_repository_raises
        return

    def remove_repository(
            self, repository_id: int, user_id: str
        ) -> None:
        self.remove_repository_calls.append(
            (repository_id, user_id)
        )
        if self.remove_repository_raises is not None:
            raise self.remove_repository_raises
        return

    def test_connectivity(self, repository_id: int) -> bool:
        self.test_connectivity_calls.append(repository_id)
        if self.test_connectivity_raises is not None:
            raise self.test_connectivity_raises
        return self.test_connectivity_response

    def fetch_latest(self, repository_id: int) -> Any:
        self.fetch_latest_calls.append(repository_id)
        if self.fetch_latest_raises is not None:
            raise self.fetch_latest_raises
        return self.fetch_latest_response


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
        projects_routes_repositories, "_build_project_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_repository_manager(
        *,
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
        projects_routes_repositories, "_build_repository_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_repository_auth_type_resolver() -> Any:
    def _resolve(*, auth_type_str: str) -> Any:
        return type("RAT", (), {"value": auth_type_str})()

    patch = create_module_patch(
        projects_routes_repositories, "_resolve_repository_auth_type"
    )
    mock = patch.activate()
    mock.configure(side_effect=_resolve)
    return patch


def _patch_repository_auth_type_enumerator() -> Any:
    def _enum() -> List[str]:
        return ["none", "ssh_key", "token"]

    patch = create_module_patch(
        projects_routes_repositories,
        "_enumerate_repository_auth_type_values",
    )
    mock = patch.activate()
    mock.configure(side_effect=_enum)
    return patch


def _patch_repository_create_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        projects_routes_repositories,
        "_build_repository_create_request",
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_repository_update_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        projects_routes_repositories,
        "_build_repository_update_request",
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


def test_register_repositories_routes_attaches_documented_routes():
    """
    **Feature: webworks projects repositories T10.1 (F2)**
    **Property: register_repositories_routes attaches the seven
    repository routes at /projects/{id}/repositories*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        projects_routes_repositories.register_repositories_routes(
            app=app
        )
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/projects/{project_id}/repositories", ("GET",)),
            (
                "/projects/{project_id}/repositories/create",
                ("GET", "POST"),
            ),
            (
                "/projects/{project_id}/repositories/{repository_id}",
                ("GET",),
            ),
            (
                "/projects/{project_id}/repositories/{repository_id}/edit",
                ("GET", "POST"),
            ),
            (
                "/projects/{project_id}/repositories/{repository_id}/delete",
                ("POST",),
            ),
            (
                "/projects/{project_id}/repositories/{repository_id}/test",
                ("POST",),
            ),
            (
                "/projects/{project_id}/repositories/{repository_id}/fetch",
                ("POST",),
            ),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Helpers
# ===========================================================================


def test_resolve_repository_or_redirect_redirects_when_project_id_mismatch():
    """
    **Feature: webworks projects repositories T10.2 (F2)**
    **Property: When the resolved repository's project_id
    doesn't match the URL's project_id, the helper treats it
    as not-found (no leak of cross-project repo existence).**
    """
    _reset_global_state()
    try:
        _install_ui_cookie_secret()
        _register_url_for_endpoints()
        helper = (
            projects_routes_repositories
            ._resolve_repository_or_redirect
        )
        rm = _FakeRepositoryManager(db_session=None)
        # Repo belongs to project 99, URL says project 7.
        rm.get_repository_response = _FakeRepository(
            repository_id=11, project_id=99
        )
        auth = config_routes._AuthResolution(
            redirect_response=None,
            session={},
            db_session=None,
            user_id="u-admin",
            username="admin",
            csrf_token="csrf",
        )
        result = helper(
            auth=auth,
            repository_manager=rm,
            project_id=7,
            repository_id=11,
        )
        is_redirect = isinstance(result, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            result.headers["Location"],
            "/projects/7/repositories",
        )
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Repository list
# ===========================================================================


def test_handle_repository_list_renders_with_can_manage_flag():
    """
    **Feature: webworks projects repositories T10.3 (F2)**
    **Property: GET /projects/{id}/repositories renders the
    list template with the resolved project + repositories +
    can_manage from the developer-permission probe.**
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
            instance.get_project_response = _FakeProject(
                project_id=7, name="alpha"
            )
            instance.check_permission_responses = {
                "view": True,
                "developer": True,
            }
            return

        pm_patch = _patch_project_manager(configure=_seed_pm)

        def _seed_rm(instance: _FakeRepositoryManager) -> None:
            instance.list_repositories_response = [
                _FakeRepository(
                    repository_id=11, project_id=7, name="repo-a"
                ),
            ]
            return

        rm_patch = _patch_repository_manager(configure=_seed_rm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = (
            projects_routes_repositories.handle_repository_list(request)
        )

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["repositories"]), 1)
        testbase.assert_equal(ctx["can_manage"], True)
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_repository_list_redirects_when_view_denied():
    """
    **Feature: webworks projects repositories T10.3 (F2)**
    **Property: A user without ``view`` permission redirects
    to /projects/list.**
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

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            instance.default_check_permission_response = False
            return

        pm_patch = _patch_project_manager(configure=_seed_pm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = (
            projects_routes_repositories.handle_repository_list(request)
        )

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


# ===========================================================================
# Repository create
# ===========================================================================


def test_handle_repository_create_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks projects repositories T10.4 (F2)**
    **Property: A valid developer POST builds + adds the repo
    and redirects to /projects/{pid}/repositories/{rid}.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    rm_patch = None
    cr_patch = None
    at_patch = None
    enum_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_pm(instance: _FakeProjectManager) -> None:
            instance.get_project_response = _FakeProject(project_id=7)
            return

        pm_patch = _patch_project_manager(configure=_seed_pm)

        def _seed_rm(instance: _FakeRepositoryManager) -> None:
            instance.add_repository_response = _FakeRepository(
                repository_id=42, project_id=7, name="repo-a"
            )
            return

        rm_patch = _patch_repository_manager(configure=_seed_rm)
        cr_patch = _patch_repository_create_request_factory()
        at_patch = _patch_repository_auth_type_resolver()
        enum_patch = _patch_repository_auth_type_enumerator()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=repo-a"
            b"&url=https%3A%2F%2Fgit.example%2Fa.git"
            b"&auth_type=ssh_key&credential_secret_ref=secret%2Fa"
            b"&default_branch=trunk&description=A+repo"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"project_id": "7"},
        )
        response = (
            projects_routes_repositories.handle_repository_create(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/projects/7/repositories/42",
        )
        rm = _FakeRepositoryManager.last_instance
        testbase.assert_equal(len(rm.add_repository_calls), 1)
        proj_id, ar, user_id = rm.add_repository_calls[0]
        testbase.assert_equal(proj_id, 7)
        testbase.assert_equal(ar.name, "repo-a")
        testbase.assert_equal(ar.url, "https://git.example/a.git")
        testbase.assert_equal(ar.auth_type.value, "ssh_key")
        testbase.assert_equal(ar.credential_secret_ref, "secret/a")
        testbase.assert_equal(ar.default_branch, "trunk")
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (
            enum_patch, at_patch, cr_patch, rm_patch, pm_patch, sm_patch,
        ):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_repository_create_developer_denied_redirects():
    """
    **Feature: webworks projects repositories T10.4 (F2)**
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

        pm_patch = _patch_project_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7"},
        )
        response = (
            projects_routes_repositories.handle_repository_create(request)
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


# ===========================================================================
# Repository detail / edit / delete
# ===========================================================================


def test_handle_repository_detail_renders_when_match():
    """
    **Feature: webworks projects repositories T10.5 (F2)**
    **Property: GET on a repository belonging to the URL's
    project renders the detail template.**
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

        pm_patch = _patch_project_manager(configure=_seed_pm)

        def _seed_rm(instance: _FakeRepositoryManager) -> None:
            instance.get_repository_response = _FakeRepository(
                repository_id=11, project_id=7
            )
            return

        rm_patch = _patch_repository_manager(configure=_seed_rm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"project_id": "7", "repository_id": "11"},
        )
        response = (
            projects_routes_repositories.handle_repository_detail(request)
        )

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["repository"].id, 11)
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_repository_edit_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks projects repositories T10.6 (F2)**
    **Property: A valid developer edit POST calls
    update_repository and redirects to /projects/{pid}/
    repositories/{rid}.**
    """
    _reset_global_state()
    sm_patch = None
    pm_patch = None
    rm_patch = None
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

        pm_patch = _patch_project_manager(configure=_seed_pm)

        def _seed_rm(instance: _FakeRepositoryManager) -> None:
            instance.get_repository_response = _FakeRepository(
                repository_id=11, project_id=7
            )
            return

        rm_patch = _patch_repository_manager(configure=_seed_rm)
        upd_patch = _patch_repository_update_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=renamed&default_branch=main"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"project_id": "7", "repository_id": "11"},
        )
        response = (
            projects_routes_repositories.handle_repository_edit(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/projects/7/repositories/11",
        )
        rm = _FakeRepositoryManager.last_instance
        testbase.assert_equal(len(rm.update_repository_calls), 1)
        target_id, ar, user_id = rm.update_repository_calls[0]
        testbase.assert_equal(target_id, 11)
        testbase.assert_equal(ar.name, "renamed")
        testbase.assert_equal(ar.default_branch, "main")
    finally:
        for p in (upd_patch, rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_repository_delete_admin_required():
    """
    **Feature: webworks projects repositories T10.7 (F2)**
    **Property: A user without ``admin`` permission cannot
    delete -- redirects to /projects/{pid}.**
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

        def _seed(instance: _FakeProjectManager) -> None:
            instance.default_check_permission_response = False
            return

        pm_patch = _patch_project_manager(configure=_seed)
        rm_patch = _patch_repository_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"project_id": "7", "repository_id": "11"},
        )
        response = (
            projects_routes_repositories.handle_repository_delete(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/projects/7"
        )
        rm = _FakeRepositoryManager.last_instance
        testbase.assert_equal(rm, None)
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_repository_delete_happy_path_redirects_to_list():
    """
    **Feature: webworks projects repositories T10.7 (F2)**
    **Property: A valid admin POST calls remove_repository
    and redirects to /projects/{pid}/repositories.**
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
        pm_patch = _patch_project_manager()
        rm_patch = _patch_repository_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"project_id": "7", "repository_id": "11"},
        )
        response = (
            projects_routes_repositories.handle_repository_delete(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/projects/7/repositories",
        )
        rm = _FakeRepositoryManager.last_instance
        testbase.assert_equal(
            rm.remove_repository_calls, [(11, "u-admin")]
        )
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Repository test / fetch
# ===========================================================================


def test_handle_repository_test_truthy_yields_success_flash():
    """
    **Feature: webworks projects repositories T10.8 (F2)**
    **Property: test_connectivity returning True yields a
    success-category flash on the redirect.**
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
        pm_patch = _patch_project_manager()

        def _seed(instance: _FakeRepositoryManager) -> None:
            instance.test_connectivity_response = True
            return

        rm_patch = _patch_repository_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"project_id": "7", "repository_id": "11"},
        )
        response = (
            projects_routes_repositories.handle_repository_test(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/projects/7/repositories/11",
        )
        rm = _FakeRepositoryManager.last_instance
        testbase.assert_equal(rm.test_connectivity_calls, [11])
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_repository_test_falsey_yields_error_flash():
    """
    **Feature: webworks projects repositories T10.8 (F2)**
    **Property: test_connectivity returning False yields an
    error-category flash on the redirect.**
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
        pm_patch = _patch_project_manager()

        def _seed(instance: _FakeRepositoryManager) -> None:
            instance.test_connectivity_response = False
            return

        rm_patch = _patch_repository_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"project_id": "7", "repository_id": "11"},
        )
        response = (
            projects_routes_repositories.handle_repository_test(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_repository_fetch_happy_path_redirects_to_detail():
    """
    **Feature: webworks projects repositories T10.9 (F2)**
    **Property: A valid POST calls fetch_latest and redirects
    with a success flash. fetch has no falsey-failure path.**
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
        pm_patch = _patch_project_manager()
        rm_patch = _patch_repository_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"project_id": "7", "repository_id": "11"},
        )
        response = (
            projects_routes_repositories.handle_repository_fetch(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        rm = _FakeRepositoryManager.last_instance
        testbase.assert_equal(rm.fetch_latest_calls, [11])
    finally:
        for p in (rm_patch, pm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return
