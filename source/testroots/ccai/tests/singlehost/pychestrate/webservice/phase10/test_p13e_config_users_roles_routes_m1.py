"""
.. module:: test_p13e_config_users_roles_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the D2 slice of the config blueprint
               port (users + roles).

.. moduleauthor:: Code Craft AI LLC

PR D2 ports the user-management (5 routes) and role-management
(4 routes) surfaces of the legacy flask config blueprint to
webworks. These tests cover:

* ``register_users_routes`` / ``register_roles_routes`` --
  route attachment matrix + url_for endpoint registration.
* user list -- pagination + search.
* user create -- GET form, POST happy path, POST validation /
  duplicate / generic error paths, CSRF rejection.
* user detail -- happy + 404.
* user edit -- GET form, POST happy path, POST validation,
  CSRF rejection.
* user deactivate -- happy + 404 + generic-error paths.
* role list / detail / edit / create -- including the
  is_system refusal path.
* MultiFormView + _parse_form_multi + _redirect_with_flash
  helpers from routes.py.
* _resolve_authenticated_request -- anonymous / expired /
  authenticated paths.

All SecurityManager / UserManager / ORM lookups are patched at
the routes-module bindings so the test suite never imports the
werkzeug-using sources.
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
    routes_roles as config_routes_roles,
    routes_users as config_routes_users,
)
from ccai.pychestrate.webservice.webinterface.foundation import (
    cookie_session,
    csrf,
    flash,
    templating,
    url_for as url_for_module,
)


# ---------------------------------------------------------------------------
# Test stubs (mirror the D1 fixtures so the helpers + tests are
# coherent across PRs)
# ---------------------------------------------------------------------------


_TEST_UI_COOKIE_SECRET: bytes = b"\x00" * 32


class _FakeQueryParams:
    def __init__(self, *, mapping: Optional[Dict[str, str]] = None) -> None:
        self._mapping: Dict[str, str] = mapping if mapping is not None else {}
        return

    def get(
            self, key: str, default: Optional[str] = None
        ) -> Optional[str]:
        rtnval = self._mapping.get(key, default)
        return rtnval


class _FakeHeaders:
    def __init__(self, *, mapping: Optional[Dict[str, str]] = None) -> None:
        self._mapping: Dict[str, str] = mapping if mapping is not None else {}
        return

    def get(
            self, key: str, default: Optional[str] = None
        ) -> Optional[str]:
        rtnval = self._mapping.get(key, default)
        return rtnval


class _FakeRequest:
    def __init__(
        self,
        *,
        method: str = "GET",
        cookies: Optional[Dict[str, str]] = None,
        body: bytes = b"",
        form_raises: bool = False,
        path_params: Optional[Dict[str, Any]] = None,
        query_mapping: Optional[Dict[str, str]] = None,
        header_mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        self.method: str = method
        self.cookies: Dict[str, str] = cookies if cookies is not None else {}
        self.body: bytes = body
        self._form_raises: bool = form_raises
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(
            mapping=query_mapping
        )
        self.headers: _FakeHeaders = _FakeHeaders(mapping=header_mapping)
        return

    def form(self) -> Dict[str, str]:
        if self._form_raises is True:
            raise ValueError("body decode failed")
        # Single-value parse to mirror webworks.Request.form().
        from urllib.parse import parse_qs
        try:
            parsed = parse_qs(self.body.decode("utf-8"), keep_blank_values=True)
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
            rtnval = func
            return rtnval

        rtnval = decorator
        return rtnval


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
        Returns a configured SessionInfo on validate_token. Used
        by all D2 tests to get past the auth gate.
    """

    last_instance: Optional["_FakeSecurityManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.validate_token_response: Optional[_FakeSessionInfo] = None
        self.validate_token_calls: List[str] = []
        _FakeSecurityManager.last_instance = self
        return

    def validate_token(self, token: str) -> Optional[_FakeSessionInfo]:
        self.validate_token_calls.append(token)
        return self.validate_token_response


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


class _FakeUserResponse:
    def __init__(
            self, *, user_id: str = "u-1", username: str = "alice",
            email: str = "alice@example.com",
            display_name: str = "Alice",
            firstname: str = "Alice", lastname: str = "Doe",
            is_active: bool = True,
            roles: Optional[List[str]] = None
        ) -> None:
        self.id: str = user_id
        self.username: str = username
        self.email: str = email
        self.display_name: str = display_name
        self.firstname: str = firstname
        self.lastname: str = lastname
        self.is_active: bool = is_active
        self.roles: List[str] = roles if roles is not None else []
        return


class _FakeListResponse:
    def __init__(self, *, users: List[Any], total: int) -> None:
        self.users: List[Any] = users
        self.total: int = total
        return


class _FakeUserManager:
    """
        Configurable fake replacing UserManager for the user
        handlers' tests. Each test seeds the responses or
        exception-instances it wants the handler to receive.
    """

    last_instance: Optional["_FakeUserManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_users_response: Optional[_FakeListResponse] = None
        self.get_user_response: Optional[_FakeUserResponse] = None
        self.list_users_calls: List[Dict[str, Any]] = []
        self.get_user_calls: List[str] = []
        self.create_user_calls: List[Any] = []
        self.update_user_calls: List[Any] = []
        self.deactivate_user_calls: List[str] = []
        self.create_user_raises: Optional[Exception] = None
        self.update_user_raises: Optional[Exception] = None
        self.deactivate_user_raises: Optional[Exception] = None
        _FakeUserManager.last_instance = self
        return

    def list_users(
            self, *, offset: int, limit: int, search: Optional[str]
        ) -> _FakeListResponse:
        self.list_users_calls.append(
            {"offset": offset, "limit": limit, "search": search}
        )
        if self.list_users_response is None:
            return _FakeListResponse(users=[], total=0)
        return self.list_users_response

    def get_user(self, user_id: str) -> Optional[_FakeUserResponse]:
        self.get_user_calls.append(user_id)
        return self.get_user_response

    def create_user(self, request: Any) -> _FakeUserResponse:
        self.create_user_calls.append(request)
        if self.create_user_raises is not None:
            raise self.create_user_raises
        return _FakeUserResponse(user_id="u-new", username=request.username)

    def update_user(self, user_id: str, request: Any) -> _FakeUserResponse:
        self.update_user_calls.append((user_id, request))
        if self.update_user_raises is not None:
            raise self.update_user_raises
        return _FakeUserResponse(user_id=user_id)

    def deactivate_user(self, user_id: str) -> None:
        self.deactivate_user_calls.append(user_id)
        if self.deactivate_user_raises is not None:
            raise self.deactivate_user_raises
        return


class _FakeValidationError(Exception):
    def __init__(self, message: str) -> None:
        self.message: str = message
        super().__init__(message)
        return


class _FakeDuplicateUserError(Exception):
    def __init__(self, message: str) -> None:
        self.message: str = message
        super().__init__(message)
        return


class _FakeUserNotFoundError(Exception):
    def __init__(self, message: str = "User not found") -> None:
        self.message: str = message
        super().__init__(message)
        return


_FAKE_USER_EXCEPTION_CLASSES: Dict[str, type] = {
    "ValidationError": _FakeValidationError,
    "DuplicateUserError": _FakeDuplicateUserError,
    "UserNotFoundError": _FakeUserNotFoundError,
}


class _FakeRole:
    def __init__(
            self, *, role_id: int, name: str,
            description: str = "",
            is_system: bool = False,
            permissions: Optional[List[Any]] = None
        ) -> None:
        self.id: int = role_id
        self.name: str = name
        self.description: str = description
        self.is_system: bool = is_system
        self.permissions: List[Any] = (
            permissions if permissions is not None else []
        )
        return


class _FakePermission:
    def __init__(
            self, *, permission_id: int, name: str,
            description: str = ""
        ) -> None:
        self.id: int = permission_id
        self.name: str = name
        self.description: str = description
        return


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
    _FakeSecurityManager.last_instance = None
    _FakeUserManager.last_instance = None
    return


_UNSET_VALIDATE_RESPONSE = object()


def _patch_security_manager(
        *, validate_token_response: Any = _UNSET_VALIDATE_RESPONSE
    ) -> Any:
    """
        Patch the SecurityManager builder on routes.py so the
        routes-side _resolve_authenticated_request helper sees a
        fake SM that returns the configured SessionInfo. Pass
        ``validate_token_response=None`` explicitly to test the
        "token expired" path (returns None from validate_token).
    """
    if validate_token_response is _UNSET_VALIDATE_RESPONSE:
        info: Optional[_FakeSessionInfo] = _FakeSessionInfo(
            user_id="u-admin",
            username="admin",
            csrf_token="csrf-fresh",
        )
    else:
        info = validate_token_response

    def _builder(*, db_session: Any) -> _FakeSecurityManager:
        instance = _FakeSecurityManager(db_session)
        instance.validate_token_response = info
        return instance

    patch = create_module_patch(
        config_routes, "_build_security_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_user_manager(
        *, configure: Optional[Callable[[_FakeUserManager], None]] = None
    ) -> Any:
    """
        Patch the UserManager builder on routes_users.
    """
    def _builder(*, db_session: Any) -> _FakeUserManager:
        instance = _FakeUserManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        config_routes_users, "_build_user_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_user_create_request_factory() -> Any:
    """
        Patch _build_user_create_request so it returns a
        SimpleNamespace-like object the FakeUserManager can
        inspect without the test importing the source dataclass.
    """
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        config_routes_users, "_build_user_create_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_user_update_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        config_routes_users, "_build_user_update_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_user_exception_classes() -> Any:
    """
        Patch _user_manager_exception_classes so the handler
        branches on our fake exception types.
    """
    def _classes() -> Dict[str, type]:
        return _FAKE_USER_EXCEPTION_CLASSES

    patch = create_module_patch(
        config_routes_users, "_user_manager_exception_classes"
    )
    mock = patch.activate()
    mock.configure(side_effect=_classes)
    return patch


def _patch_query_system_roles(
        *, roles: Optional[List[Any]] = None
    ) -> Any:
    def _query(*, db_session: Any) -> List[Any]:
        return roles if roles is not None else []

    patch = create_module_patch(
        config_routes_users, "_query_system_roles"
    )
    mock = patch.activate()
    mock.configure(side_effect=_query)
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
        Pre-register the endpoint URL patterns the handlers'
        url_for() calls reference. Tests only need this when they
        don't call register_users_routes() / register_roles_routes()
        themselves.
    """
    app = _FakeApp()
    config_routes.register_config_routes(app=app)
    return


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_users_routes_attaches_documented_routes():
    """
    **Feature: webworks config users port T2.1 (D2)**
    **Property: register_users_routes attaches the five user-
    management routes at /admin/users*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        config_routes_users.register_users_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/admin/users", ("GET",)),
            ("/admin/users/create", ("GET", "POST")),
            ("/admin/users/{user_id}", ("GET",)),
            ("/admin/users/{user_id}/edit", ("GET", "POST")),
            ("/admin/users/{user_id}/deactivate", ("POST",)),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_roles_routes_attaches_documented_routes():
    """
    **Feature: webworks config roles port T2.2 (D2)**
    **Property: register_roles_routes attaches the four role-
    management routes at /admin/roles*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        config_routes_roles.register_roles_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/admin/roles", ("GET",)),
            ("/admin/roles/create", ("GET", "POST")),
            ("/admin/roles/{role_id}", ("GET",)),
            ("/admin/roles/{role_id}/edit", ("GET", "POST")),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


# ===========================================================================
# _resolve_authenticated_request (routes.py)
# ===========================================================================


def test_resolve_authenticated_request_redirects_anonymous():
    """
    **Feature: D2 helpers T2.3**
    **Property: A request with no session cookie returns an
    _AuthResolution carrying a 302 redirect to /login --
    no DB session is opened.**
    """
    _reset_global_state()
    try:
        _install_ui_cookie_secret()
        _register_url_for_endpoints()
        request = _FakeRequest(cookies={})
        result = config_routes._resolve_authenticated_request(
            request=request
        )
        is_redirect = isinstance(
            result.redirect_response, RedirectResponse
        )
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(result.db_session, None)
    finally:
        _reset_global_state()
    return


def test_resolve_authenticated_request_redirects_when_token_invalid():
    """
    **Feature: D2 helpers T2.3**
    **Property: A cookie with an authenticated shape but a
    token whose validate_token returns None redirects to login
    AND closes the opened DB session.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        _install_db_session_factory(db_session=db_session)
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager(
            validate_token_response=None
        )
        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        result = config_routes._resolve_authenticated_request(
            request=request
        )
        is_redirect = isinstance(
            result.redirect_response, RedirectResponse
        )
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(db_session.close_count, 1)
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_resolve_authenticated_request_returns_open_session_on_happy_path():
    """
    **Feature: D2 helpers T2.3**
    **Property: A valid session yields user_id / username /
    csrf_token + an OPEN db_session the caller will close.
    The session dict is also refreshed with the SoR csrf_token.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        _install_db_session_factory(db_session=db_session)
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        try:
            result = config_routes._resolve_authenticated_request(
                request=request
            )
            testbase.assert_equal(result.redirect_response, None)
            testbase.assert_equal(result.user_id, "u-admin")
            testbase.assert_equal(result.username, "admin")
            testbase.assert_equal(result.csrf_token, "csrf-fresh")
            testbase.assert_equal(result.db_session is db_session, True)
            testbase.assert_equal(
                result.session[csrf.SESSION_KEY], "csrf-fresh"
            )
        finally:
            try:
                result.db_session.close()
            except Exception:
                pass
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# _parse_form_multi + MultiFormView (routes.py)
# ===========================================================================


def test_parse_form_multi_returns_lists_per_key():
    """
    **Feature: D2 helpers T2.4 (multi-value form)**
    **Property: A body with repeated ``role_ids=1&role_ids=2``
    yields ``{"role_ids": ["1", "2"]}`` -- preserving the
    multi-checkbox shape webworks Request.form() loses.**
    """
    request = _FakeRequest(
        method="POST",
        body=b"role_ids=1&role_ids=2&name=alice",
    )
    parsed = config_routes._parse_form_multi(request=request)
    testbase.assert_equal(parsed["role_ids"], ["1", "2"])
    testbase.assert_equal(parsed["name"], ["alice"])
    return


def test_parse_form_multi_empty_body_yields_empty_dict():
    """
    **Feature: D2 helpers T2.4 (multi-value form)**
    **Property: An empty body returns an empty dict rather than
    raising.**
    """
    request = _FakeRequest(method="POST", body=b"")
    parsed = config_routes._parse_form_multi(request=request)
    testbase.assert_equal(parsed, {})
    return


def test_multi_form_view_getlist_returns_list_or_empty():
    """
    **Feature: D2 helpers T2.4 (multi-value form)**
    **Property: MultiFormView.getlist returns the configured
    values or an empty list for absent keys -- mirrors flask
    MultiDict.getlist.**
    """
    view = config_routes.MultiFormView(
        data={"role_ids": ["1", "2"], "name": ["alice"]}
    )
    testbase.assert_equal(view.getlist("role_ids"), ["1", "2"])
    testbase.assert_equal(view.getlist("missing"), [])
    testbase.assert_equal(view.get("name"), "alice")
    testbase.assert_equal(view.get("missing", "default"), "default")
    testbase.assert_equal("role_ids" in view, True)
    testbase.assert_equal("missing" in view, False)
    return


# ===========================================================================
# handle_user_list (GET /admin/users)
# ===========================================================================


def test_handle_user_list_renders_with_pagination_and_search():
    """
    **Feature: webworks config users port T2.5**
    **Property: GET /admin/users renders config/users/list.html
    with the paginated UserManager output, computed total_pages,
    and the search query passed through.**
    """
    _reset_global_state()
    sm_patch = None
    um_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        _install_db_session_factory(db_session=db_session)
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        users = [_FakeUserResponse(user_id="u-1", username="alice")]

        def _seed(instance: _FakeUserManager) -> None:
            instance.list_users_response = _FakeListResponse(
                users=users, total=42
            )
            return

        um_patch = _patch_user_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            query_mapping={"page": "2", "per_page": "10", "search": "ali"},
        )
        response = config_routes_users.handle_user_list(request)

        is_html = isinstance(response, HTMLResponse)
        testbase.assert_equal(is_html, True)
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/users/list.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["users"], users)
        testbase.assert_equal(ctx["total"], 42)
        testbase.assert_equal(ctx["page"], 2)
        testbase.assert_equal(ctx["per_page"], 10)
        testbase.assert_equal(ctx["total_pages"], 5)  # ceil(42/10)
        testbase.assert_equal(ctx["search"], "ali")
        testbase.assert_equal(db_session.close_count, 1)

        # UserManager called with offset=10 (page 2 - 1 * 10), limit=10,
        # search="ali".
        um_call = _FakeUserManager.last_instance.list_users_calls[0]
        testbase.assert_equal(um_call["offset"], 10)
        testbase.assert_equal(um_call["limit"], 10)
        testbase.assert_equal(um_call["search"], "ali")
    finally:
        if um_patch is not None:
            um_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_user_list_redirects_anonymous():
    """
    **Feature: webworks config users port T2.5**
    **Property: An unauthenticated GET /admin/users redirects
    to /login.**
    """
    _reset_global_state()
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _register_url_for_endpoints()
        request = _FakeRequest(cookies={})
        response = config_routes_users.handle_user_list(request)
        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/login"
        )
    finally:
        _reset_global_state()
    return


# ===========================================================================
# handle_user_create
# ===========================================================================


def test_handle_user_create_get_renders_form_with_roles():
    """
    **Feature: webworks config users port T2.6**
    **Property: GET /admin/users/create renders the create form
    with the current SystemRole list.**
    """
    _reset_global_state()
    sm_patch = None
    qsr_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        roles = [
            _FakeRole(role_id=1, name="admin"),
            _FakeRole(role_id=2, name="viewer"),
        ]
        qsr_patch = _patch_query_system_roles(roles=roles)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="GET",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
        )
        response = config_routes_users.handle_user_create(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/users/create.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["roles"], roles)
        testbase.assert_equal(ctx["form_data"], None)
    finally:
        if qsr_patch is not None:
            qsr_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_user_create_post_happy_path_redirects_to_list():
    """
    **Feature: webworks config users port T2.6**
    **Property: A valid POST creates the user via UserManager
    and redirects to /admin/users with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    um_patch = None
    cr_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        um_patch = _patch_user_manager()
        cr_patch = _patch_user_create_request_factory()
        exc_patch = _patch_user_exception_classes()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&username=newbie&email=n@example.com"
            b"&password=Sup3rS3cr3t!&display_name=Newbie"
            b"&firstname=New&lastname=Bie"
            b"&role_ids=1&role_ids=2"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_users.handle_user_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(response.status_code, 303)
        testbase.assert_equal(
            response.headers["Location"], "/admin/users"
        )
        # UserManager.create_user invoked with the submitted values
        # carried on the namespace returned by the patched factory.
        um = _FakeUserManager.last_instance
        testbase.assert_equal(len(um.create_user_calls), 1)
        ar = um.create_user_calls[0]
        testbase.assert_equal(ar.username, "newbie")
        testbase.assert_equal(ar.email, "n@example.com")
        testbase.assert_equal(ar.role_ids, [1, 2])
    finally:
        for p in (exc_patch, cr_patch, um_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_create_post_csrf_mismatch_redirects():
    """
    **Feature: webworks config users port T2.6**
    **Property: A POST with a missing / mismatched csrf_token
    bounces back to the create page without invoking the
    UserManager.**
    """
    _reset_global_state()
    sm_patch = None
    um_patch = None
    qsr_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        um_patch = _patch_user_manager()
        qsr_patch = _patch_query_system_roles(roles=[])

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=wrong-token&username=newbie&email=n@example.com"
            b"&password=pw"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_users.handle_user_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        # No user was created. The handler short-circuited before
        # constructing the UserManager (so last_instance is None
        # because no manager was ever built).
        testbase.assert_equal(_FakeUserManager.last_instance, None)
    finally:
        for p in (qsr_patch, um_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_create_post_validation_error_re_renders_with_flash():
    """
    **Feature: webworks config users port T2.6**
    **Property: When create_user raises ValidationError the form
    re-renders (status 400) with an error-category flash carrying
    the exception message.**
    """
    _reset_global_state()
    sm_patch = None
    um_patch = None
    cr_patch = None
    exc_patch = None
    qsr_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeUserManager) -> None:
            instance.create_user_raises = _FakeValidationError(
                "Username is too short"
            )
            return

        um_patch = _patch_user_manager(configure=_seed)
        cr_patch = _patch_user_create_request_factory()
        exc_patch = _patch_user_exception_classes()
        qsr_patch = _patch_query_system_roles(roles=[])

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&username=ab&email=x@y.z&password=pw"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_users.handle_user_create(request)

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        category, message = ctx["flashes"][0]
        testbase.assert_equal(category, "error")
        contains = "Username is too short" in message
        testbase.assert_equal(contains, True)
    finally:
        for p in (qsr_patch, exc_patch, cr_patch, um_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# handle_user_detail
# ===========================================================================


def test_handle_user_detail_renders_when_user_found():
    """
    **Feature: webworks config users port T2.7**
    **Property: GET /admin/users/{user_id} renders the detail
    template with the resolved user.**
    """
    _reset_global_state()
    sm_patch = None
    um_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        user = _FakeUserResponse(user_id="u-42", username="alice")

        def _seed(instance: _FakeUserManager) -> None:
            instance.get_user_response = user
            return

        um_patch = _patch_user_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"user_id": "u-42"},
        )
        response = config_routes_users.handle_user_detail(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/users/detail.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["user"], user)
    finally:
        if um_patch is not None:
            um_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_user_detail_redirects_when_user_missing():
    """
    **Feature: webworks config users port T2.7**
    **Property: A user_id not found by the manager redirects to
    /admin/users with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    um_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        um_patch = _patch_user_manager()  # get_user_response stays None

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"user_id": "u-ghost"},
        )
        response = config_routes_users.handle_user_detail(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/users"
        )
    finally:
        if um_patch is not None:
            um_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# handle_user_edit
# ===========================================================================


def test_handle_user_edit_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks config users port T2.8**
    **Property: A valid edit POST calls update_user and
    redirects to /admin/users/{user_id} with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    um_patch = None
    upd_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        um_patch = _patch_user_manager()
        upd_patch = _patch_user_update_request_factory()
        exc_patch = _patch_user_exception_classes()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&email=new@example.com"
            b"&display_name=Updated&firstname=New&lastname=Name"
            b"&is_active=on&role_ids=1"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"user_id": "u-7"},
        )
        response = config_routes_users.handle_user_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(response.status_code, 303)
        testbase.assert_equal(
            response.headers["Location"], "/admin/users/u-7"
        )
        um = _FakeUserManager.last_instance
        testbase.assert_equal(len(um.update_user_calls), 1)
        target_id, ar = um.update_user_calls[0]
        testbase.assert_equal(target_id, "u-7")
        testbase.assert_equal(ar.email, "new@example.com")
        testbase.assert_equal(ar.is_active, True)
        testbase.assert_equal(ar.role_ids, [1])
    finally:
        for p in (exc_patch, upd_patch, um_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_edit_get_renders_form_when_user_found():
    """
    **Feature: webworks config users port T2.8**
    **Property: GET on edit renders the edit template with
    the resolved user + roles.**
    """
    _reset_global_state()
    sm_patch = None
    um_patch = None
    qsr_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        user = _FakeUserResponse(user_id="u-1", username="alice")

        def _seed(instance: _FakeUserManager) -> None:
            instance.get_user_response = user
            return

        um_patch = _patch_user_manager(configure=_seed)
        roles = [_FakeRole(role_id=1, name="admin")]
        qsr_patch = _patch_query_system_roles(roles=roles)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"user_id": "u-1"},
        )
        response = config_routes_users.handle_user_edit(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/users/edit.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["user"], user)
        testbase.assert_equal(ctx["roles"], roles)
    finally:
        for p in (qsr_patch, um_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# handle_user_deactivate
# ===========================================================================


def test_handle_user_deactivate_happy_path_redirects_to_list():
    """
    **Feature: webworks config users port T2.9**
    **Property: A valid deactivate POST calls deactivate_user
    and redirects to /admin/users with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    um_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        um_patch = _patch_user_manager()
        exc_patch = _patch_user_exception_classes()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"user_id": "u-7"},
        )
        response = config_routes_users.handle_user_deactivate(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/users"
        )
        um = _FakeUserManager.last_instance
        testbase.assert_equal(um.deactivate_user_calls, ["u-7"])
    finally:
        for p in (exc_patch, um_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_deactivate_user_not_found_flashes_error():
    """
    **Feature: webworks config users port T2.9**
    **Property: deactivate_user raising UserNotFoundError yields
    a 303 redirect with an error-category "User not found" flash.**
    """
    _reset_global_state()
    sm_patch = None
    um_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeUserManager) -> None:
            instance.deactivate_user_raises = _FakeUserNotFoundError(
                "User u-ghost not found"
            )
            return

        um_patch = _patch_user_manager(configure=_seed)
        exc_patch = _patch_user_exception_classes()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"user_id": "u-ghost"},
        )
        response = config_routes_users.handle_user_deactivate(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/users"
        )
    finally:
        for p in (exc_patch, um_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Roles
# ===========================================================================


def _patch_query_all_system_roles(*, roles: List[Any]) -> Any:
    def _q(*, db_session: Any) -> List[Any]:
        return roles

    patch = create_module_patch(
        config_routes_roles, "_query_all_system_roles"
    )
    mock = patch.activate()
    mock.configure(side_effect=_q)
    return patch


def _patch_query_system_role_by_id(
        *, role: Optional[_FakeRole]
    ) -> Any:
    def _q(*, db_session: Any, role_id: int) -> Optional[_FakeRole]:
        return role

    patch = create_module_patch(
        config_routes_roles, "_query_system_role_by_id"
    )
    mock = patch.activate()
    mock.configure(side_effect=_q)
    return patch


def _patch_query_system_role_by_name(
        *, role: Optional[_FakeRole]
    ) -> Any:
    def _q(*, db_session: Any, name: str) -> Optional[_FakeRole]:
        return role

    patch = create_module_patch(
        config_routes_roles, "_query_system_role_by_name"
    )
    mock = patch.activate()
    mock.configure(side_effect=_q)
    return patch


def _patch_query_all_permissions(*, permissions: List[Any]) -> Any:
    def _q(*, db_session: Any) -> List[Any]:
        return permissions

    patch = create_module_patch(
        config_routes_roles, "_query_all_permissions"
    )
    mock = patch.activate()
    mock.configure(side_effect=_q)
    return patch


def _patch_query_permissions_by_ids(
        *, permissions: List[Any]
    ) -> Any:
    def _q(
            *, db_session: Any, permission_ids: List[int]
        ) -> List[Any]:
        return permissions

    patch = create_module_patch(
        config_routes_roles, "_query_permissions_by_ids"
    )
    mock = patch.activate()
    mock.configure(side_effect=_q)
    return patch


def _patch_build_system_role(*, role_factory: Callable[..., Any]) -> Any:
    patch = create_module_patch(
        config_routes_roles, "_build_system_role"
    )
    mock = patch.activate()
    mock.configure(side_effect=role_factory)
    return patch


def _patch_add_and_commit() -> Any:
    captured: List[Any] = []

    def _ac(*, db_session: Any, instance: Any) -> None:
        captured.append(instance)
        return

    patch = create_module_patch(
        config_routes_roles, "_add_and_commit"
    )
    mock = patch.activate()
    mock.configure(side_effect=_ac)
    patch.captured = captured
    return patch


def _patch_commit() -> Any:
    captured: List[bool] = []

    def _c(*, db_session: Any) -> None:
        captured.append(True)
        return

    patch = create_module_patch(
        config_routes_roles, "_commit"
    )
    mock = patch.activate()
    mock.configure(side_effect=_c)
    patch.captured = captured
    return patch


def _patch_rollback() -> Any:
    def _r(*, db_session: Any) -> None:
        return

    patch = create_module_patch(
        config_routes_roles, "_rollback"
    )
    mock = patch.activate()
    mock.configure(side_effect=_r)
    return patch


def test_handle_role_list_renders_with_roles():
    """
    **Feature: webworks config roles port T2.10**
    **Property: GET /admin/roles renders config/roles/list.html
    with every SystemRole row.**
    """
    _reset_global_state()
    sm_patch = None
    qr_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        roles = [
            _FakeRole(role_id=1, name="admin", is_system=True),
            _FakeRole(role_id=2, name="viewer"),
        ]
        qr_patch = _patch_query_all_system_roles(roles=roles)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = config_routes_roles.handle_role_list(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["roles"], roles)
    finally:
        if qr_patch is not None:
            qr_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_role_create_post_happy_path_persists_and_redirects():
    """
    **Feature: webworks config roles port T2.11**
    **Property: A valid POST builds + commits a SystemRole and
    redirects to /admin/roles with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    by_name_patch = None
    perm_patch = None
    perm_by_ids_patch = None
    build_patch = None
    add_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        by_name_patch = _patch_query_system_role_by_name(role=None)
        perm_patch = _patch_query_all_permissions(permissions=[])
        perm_by_ids_patch = _patch_query_permissions_by_ids(
            permissions=[_FakePermission(permission_id=11, name="users.read")]
        )
        captured_roles: List[Any] = []

        def _build(*, name: str, description: str, is_system: bool = False):
            built = _FakeRole(
                role_id=99, name=name, description=description,
                is_system=is_system,
            )
            captured_roles.append(built)
            return built

        build_patch = _patch_build_system_role(role_factory=_build)
        add_patch = _patch_add_and_commit()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=editor&description=Edit+stuff"
            b"&permission_ids=11"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_roles.handle_role_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/roles"
        )
        # Built role + permissions assigned + persisted.
        testbase.assert_equal(len(captured_roles), 1)
        built = captured_roles[0]
        testbase.assert_equal(built.name, "editor")
        testbase.assert_equal(len(built.permissions), 1)
        testbase.assert_equal(len(add_patch.captured), 1)
    finally:
        for p in (
            add_patch, build_patch, perm_by_ids_patch,
            perm_patch, by_name_patch, sm_patch,
        ):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_role_create_post_duplicate_name_re_renders_with_flash():
    """
    **Feature: webworks config roles port T2.11**
    **Property: When _query_system_role_by_name returns an
    existing role, the handler re-renders the create form (400)
    with a "Role already exists" flash.**
    """
    _reset_global_state()
    sm_patch = None
    by_name_patch = None
    perm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        existing = _FakeRole(role_id=5, name="editor")
        by_name_patch = _patch_query_system_role_by_name(role=existing)
        perm_patch = _patch_query_all_permissions(permissions=[])

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&name=editor&description=dup"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_roles.handle_role_create(request)

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        category, message = ctx["flashes"][0]
        testbase.assert_equal(category, "error")
        contains = "already exists" in message
        testbase.assert_equal(contains, True)
    finally:
        for p in (perm_patch, by_name_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_role_detail_renders_when_role_found():
    """
    **Feature: webworks config roles port T2.12**
    **Property: GET /admin/roles/{role_id} renders the detail
    template with the resolved role.**
    """
    _reset_global_state()
    sm_patch = None
    role_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        role = _FakeRole(role_id=7, name="editor")
        role_patch = _patch_query_system_role_by_id(role=role)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"role_id": "7"},
        )
        response = config_routes_roles.handle_role_detail(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["role"], role)
    finally:
        if role_patch is not None:
            role_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_role_detail_redirects_when_role_missing():
    """
    **Feature: webworks config roles port T2.12**
    **Property: A role_id whose lookup returns None redirects to
    /admin/roles with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    role_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        role_patch = _patch_query_system_role_by_id(role=None)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"role_id": "99"},
        )
        response = config_routes_roles.handle_role_detail(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/roles"
        )
    finally:
        if role_patch is not None:
            role_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_role_edit_post_refuses_system_role():
    """
    **Feature: webworks config roles port T2.13**
    **Property: An edit POST against a role with is_system=True
    redirects to /admin/roles/{role_id} with a "System roles
    cannot be modified" error flash and does NOT call commit.**
    """
    _reset_global_state()
    sm_patch = None
    role_patch = None
    commit_patch = None
    perm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        role = _FakeRole(role_id=1, name="admin", is_system=True)
        role_patch = _patch_query_system_role_by_id(role=role)
        commit_patch = _patch_commit()
        perm_patch = _patch_query_all_permissions(permissions=[])

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&description=tampered"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"role_id": "1"},
        )
        response = config_routes_roles.handle_role_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/roles/1"
        )
        # No commit happened.
        testbase.assert_equal(commit_patch.captured, [])
    finally:
        for p in (perm_patch, commit_patch, role_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_role_edit_post_happy_path_commits_and_redirects():
    """
    **Feature: webworks config roles port T2.13**
    **Property: A valid edit POST mutates the role + permissions
    and commits, then redirects to /admin/roles/{role_id} with
    a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    role_patch = None
    perm_patch = None
    perm_by_ids_patch = None
    commit_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        role = _FakeRole(role_id=2, name="editor", is_system=False)
        role_patch = _patch_query_system_role_by_id(role=role)
        perm_patch = _patch_query_all_permissions(permissions=[])
        new_perms = [_FakePermission(permission_id=11, name="users.read")]
        perm_by_ids_patch = _patch_query_permissions_by_ids(
            permissions=new_perms
        )
        commit_patch = _patch_commit()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&description=Updated+desc"
            b"&permission_ids=11"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"role_id": "2"},
        )
        response = config_routes_roles.handle_role_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/roles/2"
        )
        testbase.assert_equal(role.description, "Updated desc")
        testbase.assert_equal(role.permissions, new_perms)
        testbase.assert_equal(commit_patch.captured, [True])
    finally:
        for p in (
            commit_patch, perm_by_ids_patch, perm_patch,
            role_patch, sm_patch,
        ):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return
