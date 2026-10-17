"""
.. module:: test_p13e_config_users_roles_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the users + roles slices of the config
               blueprint, ported to the modern identity + RBAC
               stores.

.. moduleauthor:: Code Craft AI LLC

The users / roles admin pages are backed by
:mod:`webinterface.blueprints.config.identity_admin`, which reads
and writes the modern identity store (``identity_users`` +
``auth_local_credentials``) and the modern RBAC store
(``rbac_roles`` / ``rbac_role_permissions`` /
``rbac_role_bindings``). These tests cover:

* ``register_users_routes`` / ``register_roles_routes`` --
  route attachment matrix + url_for endpoint registration.
* user list -- pagination + search.
* user create -- GET form, POST happy path, POST validation /
  duplicate paths, CSRF rejection.
* user detail -- happy + 404.
* user edit -- GET form, POST happy path, self-lockout guard,
  self-edit control preservation.
* user deactivate -- happy + 404 + self-lockout paths.
* role list / detail / create / edit / delete -- including the
  built-in-role refusal, the empty-permission-set confirmation,
  and the delete consequence flash.
* END-TO-END TRUTH: a user created through the route handler can
  authenticate through ``local_flow.verify_local_credentials``,
  and a role granted through the route handler flips
  ``rbac_evaluator.check_permission`` -- for both catalog roles
  and custom (DB-grant) roles.

The handler unit tests patch the ``_svc_*`` service seams at the
routes-module bindings so they never import the identity /
password-hashing sources. The truth tests run the real service
against an in-memory Phase-1 database.
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
        by all tests to get past the auth gate. ``check_permission``
        grants every permission except those a test lists in
        ``denied_permissions``.
    """

    last_instance: Optional["_FakeSecurityManager"] = None
    denied_permissions: List[str] = []

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.validate_token_response: Optional[_FakeSessionInfo] = None
        self.validate_token_calls: List[str] = []
        _FakeSecurityManager.last_instance = self
        return

    def validate_token(self, token: str) -> Optional[_FakeSessionInfo]:
        self.validate_token_calls.append(token)
        return self.validate_token_response

    def check_permission(self, user_id: str, permission: str) -> bool:
        rtnval = permission not in _FakeSecurityManager.denied_permissions
        return rtnval


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


class _FakeUserView:
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


class _FakeListResult:
    def __init__(self, *, users: List[Any], total: int) -> None:
        self.users: List[Any] = users
        self.total: int = total
        return


class _FakePermView:
    def __init__(
            self, *, key: str, description: str = ""
        ) -> None:
        self.id: str = key
        self.name: str = key
        self.description: str = description
        return


class _FakeRoleView:
    def __init__(
            self, *, role_id: str, name: str,
            description: str = "",
            is_system: bool = False,
            permissions: Optional[List[Any]] = None,
            binding_count: int = 0
        ) -> None:
        self.id: str = role_id
        self.name: str = name
        self.description: str = description
        self.is_system: bool = is_system
        self.permissions: List[Any] = (
            permissions if permissions is not None else []
        )
        self.binding_count: int = binding_count
        return


class _FakeAdminValidationError(Exception):
    def __init__(self, message: str) -> None:
        self.message: str = message
        super().__init__(message)
        return


class _FakeAdminDuplicateError(Exception):
    def __init__(self, message: str) -> None:
        self.message: str = message
        super().__init__(message)
        return


class _FakeAdminNotFoundError(Exception):
    def __init__(self, message: str = "User not found") -> None:
        self.message: str = message
        super().__init__(message)
        return


class _FakeSelfLockoutError(Exception):
    def __init__(self, message: str = "You cannot deactivate your own account.") -> None:
        self.message: str = message
        super().__init__(message)
        return


class _FakeBuiltinRoleProtectedError(Exception):
    def __init__(self, message: str = "Built-in role.") -> None:
        self.message: str = message
        super().__init__(message)
        return


class _FakeLastAdminRoleError(Exception):
    def __init__(self, message: str = "Last admin role.") -> None:
        self.message: str = message
        super().__init__(message)
        return


_FAKE_USER_EXCEPTION_CLASSES: Dict[str, type] = {
    "AdminValidationError": _FakeAdminValidationError,
    "AdminDuplicateError": _FakeAdminDuplicateError,
    "AdminNotFoundError": _FakeAdminNotFoundError,
    "SelfLockoutError": _FakeSelfLockoutError,
}


_FAKE_ROLE_EXCEPTION_CLASSES: Dict[str, type] = {
    "AdminValidationError": _FakeAdminValidationError,
    "AdminDuplicateError": _FakeAdminDuplicateError,
    "AdminNotFoundError": _FakeAdminNotFoundError,
    "BuiltinRoleProtectedError": _FakeBuiltinRoleProtectedError,
    "LastAdminRoleError": _FakeLastAdminRoleError,
}


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
    _FakeSecurityManager.denied_permissions = []
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


def _patch_seam(
        *, module: Any, seam_name: str, side_effect: Callable
    ) -> Any:
    """
        Patch one ``_svc_*`` seam (or exception-class provider) on a
        routes module, returning the activated patch.
    """
    patch = create_module_patch(module, seam_name)
    mock = patch.activate()
    mock.configure(side_effect=side_effect)
    return patch


def _patch_user_exception_classes() -> Any:
    def _classes() -> Dict[str, type]:
        return dict(_FAKE_USER_EXCEPTION_CLASSES)

    rtnval = _patch_seam(
        module=config_routes_users,
        seam_name="_admin_exception_classes",
        side_effect=_classes,
    )
    return rtnval


def _patch_role_exception_classes() -> Any:
    def _classes() -> Dict[str, type]:
        return dict(_FAKE_ROLE_EXCEPTION_CLASSES)

    rtnval = _patch_seam(
        module=config_routes_roles,
        seam_name="_roles_exception_classes",
        side_effect=_classes,
    )
    return rtnval


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
        url_for() calls reference.
    """
    app = _FakeApp()
    config_routes.register_config_routes(app=app)
    users_app = _FakeApp()
    config_routes_users.register_users_routes(app=users_app)
    roles_app = _FakeApp()
    config_routes_roles.register_roles_routes(app=roles_app)
    return


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_users_routes_attaches_documented_routes():
    """
    **Feature: webworks config users port T2.1 (D2)**
    **Property: register_users_routes attaches the user-
    management routes at /admin/users*, including the reset-
    password page, the reset / invite link action (ADM-04) and
    the anonymise and delete actions (ADM-41).**
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
            ("/admin/users/{user_id}/anonymise", ("POST",)),
            ("/admin/users/{user_id}/delete", ("POST",)),
            ("/admin/users/{user_id}/reactivate", ("POST",)),
            ("/admin/users/{user_id}/password", ("GET", "POST")),
            ("/admin/users/{user_id}/password-link", ("POST",)),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_roles_routes_attaches_documented_routes():
    """
    **Feature: webworks config roles port T2.2 (D2)**
    **Property: register_roles_routes attaches the five role-
    management routes at /admin/roles* including the delete
    route.**
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
            ("/admin/roles/{role_id}/delete", ("POST",)),
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
    _AuthResolution carrying a redirect to /login -- no DB
    session is opened.**
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
        _restore_ambient_pepper()
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
        _restore_ambient_pepper()
        _reset_global_state()
    return


# ===========================================================================
# _parse_form_multi + MultiFormView (routes.py)
# ===========================================================================


def test_parse_form_multi_returns_lists_per_key():
    """
    **Feature: D2 helpers T2.4 (multi-value form)**
    **Property: A body with repeated ``role_names=a&role_names=b``
    yields ``{"role_names": ["a", "b"]}`` -- preserving the
    multi-checkbox shape webworks Request.form() loses.**
    """
    request = _FakeRequest(
        method="POST",
        body=b"role_names=system-admin&role_names=auditor&name=alice",
    )
    parsed = config_routes._parse_form_multi(request=request)
    testbase.assert_equal(
        parsed["role_names"], ["system-admin", "auditor"]
    )
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
        data={"role_names": ["a", "b"], "name": ["alice"]}
    )
    testbase.assert_equal(view.getlist("role_names"), ["a", "b"])
    testbase.assert_equal(view.getlist("missing"), [])
    testbase.assert_equal(view.get("name"), "alice")
    testbase.assert_equal(view.get("missing", "default"), "default")
    testbase.assert_equal("role_names" in view, True)
    testbase.assert_equal("missing" in view, False)
    return


# ===========================================================================
# handle_user_list (GET /admin/users)
# ===========================================================================


def test_handle_user_list_renders_with_pagination_and_search():
    """
    **Feature: webworks config users port T2.5**
    **Property: GET /admin/users renders config/users/list.html
    with the paginated identity-store output, computed
    total_pages, and the search query passed through.**
    """
    _reset_global_state()
    sm_patch = None
    svc_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        _install_db_session_factory(db_session=db_session)
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        users = [_FakeUserView(user_id="u-1", username="alice")]
        list_calls: List[Dict[str, Any]] = []

        def _list(
                *, db_session: Any, offset: int, limit: int,
                search: Optional[str], include_deleted: bool = False
            ) -> _FakeListResult:
            list_calls.append(
                {"offset": offset, "limit": limit, "search": search}
            )
            return _FakeListResult(users=users, total=42)

        svc_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_list_users",
            side_effect=_list,
        )

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
        testbase.assert_equal(ctx["current_user_id"], "u-admin")
        testbase.assert_equal(db_session.close_count, 1)

        # Service called with offset=10 ((page 2 - 1) * 10),
        # limit=10, search="ali".
        testbase.assert_equal(list_calls[0]["offset"], 10)
        testbase.assert_equal(list_calls[0]["limit"], 10)
        testbase.assert_equal(list_calls[0]["search"], "ali")
    finally:
        if svc_patch is not None:
            svc_patch.deactivate()
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
        location = response.headers["Location"]
        starts_with_login = location.startswith("/login")
        testbase.assert_equal(starts_with_login, True)
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
    with the current RBAC role options.**
    """
    _reset_global_state()
    sm_patch = None
    roles_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        roles = [
            _FakeRoleView(role_id="r-1", name="system-admin", is_system=True),
            _FakeRoleView(role_id="r-2", name="viewer"),
        ]

        def _list_roles(*, db_session: Any) -> List[Any]:
            return roles

        roles_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_list_role_options",
            side_effect=_list_roles,
        )

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
        if roles_patch is not None:
            roles_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_user_create_post_happy_path_redirects_to_list():
    """
    **Feature: webworks config users port T2.6**
    **Property: A valid POST creates the user via the identity-
    admin service (role names + acting admin id included) and
    redirects to /admin/users with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    create_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_user_exception_classes()

        create_calls: List[Dict[str, Any]] = []

        def _create(**kwargs: Any) -> str:
            create_calls.append(kwargs)
            return "u-new"

        create_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_create_user",
            side_effect=_create,
        )

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&username=newbie&email=n@example.com"
            b"&password=Sup3rS3cr3t!&display_name=Newbie"
            b"&firstname=New&lastname=Bie"
            b"&role_names=system-admin&role_names=viewer"
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
        testbase.assert_equal(len(create_calls), 1)
        call = create_calls[0]
        testbase.assert_equal(call["username"], "newbie")
        testbase.assert_equal(call["email"], "n@example.com")
        testbase.assert_equal(
            call["role_names"], ["system-admin", "viewer"]
        )
        testbase.assert_equal(call["actor_user_id"], "u-admin")
    finally:
        for p in (create_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_create_post_csrf_mismatch_redirects():
    """
    **Feature: webworks config users port T2.6**
    **Property: A POST with a missing / mismatched csrf_token
    bounces back without invoking the create service.**
    """
    _reset_global_state()
    sm_patch = None
    create_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        create_calls: List[Dict[str, Any]] = []

        def _create(**kwargs: Any) -> str:
            create_calls.append(kwargs)
            return "u-new"

        create_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_create_user",
            side_effect=_create,
        )

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
        testbase.assert_equal(create_calls, [])
    finally:
        for p in (create_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_create_post_validation_error_re_renders_with_flash():
    """
    **Feature: webworks config users port T2.6**
    **Property: When the create service raises the validation
    error the form re-renders (status 400) with an error-category
    flash carrying the exception message.**
    """
    _reset_global_state()
    sm_patch = None
    create_patch = None
    exc_patch = None
    roles_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_user_exception_classes()

        def _create(**kwargs: Any) -> str:
            raise _FakeAdminValidationError("Username is too short")

        create_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_create_user",
            side_effect=_create,
        )

        def _list_roles(*, db_session: Any) -> List[Any]:
            return []

        roles_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_list_role_options",
            side_effect=_list_roles,
        )

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
        for p in (roles_patch, create_patch, exc_patch, sm_patch):
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
    get_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        user = _FakeUserView(user_id="u-42", username="alice")

        def _get(*, db_session: Any, user_id: str) -> Optional[Any]:
            return user

        get_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_get_user",
            side_effect=_get,
        )

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
        if get_patch is not None:
            get_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_user_detail_redirects_when_user_missing():
    """
    **Feature: webworks config users port T2.7**
    **Property: A user_id the service cannot resolve redirects to
    /admin/users with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    get_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _get(*, db_session: Any, user_id: str) -> Optional[Any]:
            return None

        get_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_get_user",
            side_effect=_get,
        )

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
        if get_patch is not None:
            get_patch.deactivate()
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
    **Property: A valid edit POST calls the update service with
    the submitted role names + status and redirects to
    /admin/users/{user_id} with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    update_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_user_exception_classes()

        update_calls: List[Dict[str, Any]] = []

        def _update(**kwargs: Any) -> None:
            update_calls.append(kwargs)
            return

        update_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_update_user",
            side_effect=_update,
        )

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&email=new@example.com"
            b"&display_name=Updated&firstname=New&lastname=Name"
            b"&is_active=on&role_names=viewer"
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
        testbase.assert_equal(len(update_calls), 1)
        call = update_calls[0]
        testbase.assert_equal(call["user_id"], "u-7")
        testbase.assert_equal(call["email"], "new@example.com")
        testbase.assert_equal(call["is_active"], True)
        testbase.assert_equal(call["role_names"], ["viewer"])
        testbase.assert_equal(call["actor_user_id"], "u-admin")
    finally:
        for p in (update_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_edit_get_renders_form_when_user_found():
    """
    **Feature: webworks config users port T2.8**
    **Property: GET on edit renders the edit template with the
    resolved user + role options and is_self=False for another
    user's row.**
    """
    _reset_global_state()
    sm_patch = None
    get_patch = None
    roles_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        user = _FakeUserView(user_id="u-1", username="alice")

        def _get(*, db_session: Any, user_id: str) -> Optional[Any]:
            return user

        get_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_get_user",
            side_effect=_get,
        )
        roles = [_FakeRoleView(role_id="r-1", name="system-admin")]

        def _list_roles(*, db_session: Any) -> List[Any]:
            return roles

        roles_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_list_role_options",
            side_effect=_list_roles,
        )

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
        testbase.assert_equal(ctx["is_self"], False)
    finally:
        for p in (roles_patch, get_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_edit_self_post_preserves_status_and_roles():
    """
    **Feature: self-lockout guard T2.8b**
    **Property: When an admin edits their own row the hidden
    status/role controls post nothing -- the handler preserves
    the CURRENT is_active + role set server-side instead of
    interpreting absence as "deactivate + strip roles".**
    """
    _reset_global_state()
    sm_patch = None
    get_patch = None
    update_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_user_exception_classes()

        self_user = _FakeUserView(
            user_id="u-admin", username="admin",
            is_active=True, roles=["system-admin"],
        )

        def _get(*, db_session: Any, user_id: str) -> Optional[Any]:
            return self_user

        get_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_get_user",
            side_effect=_get,
        )

        update_calls: List[Dict[str, Any]] = []

        def _update(**kwargs: Any) -> None:
            update_calls.append(kwargs)
            return

        update_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_update_user",
            side_effect=_update,
        )

        cookie_value = _build_authenticated_cookie()
        # The self form omits is_active + role_names entirely.
        body = (
            b"csrf_token=csrf-fresh&email=admin@example.com"
            b"&display_name=Admin&firstname=&lastname="
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"user_id": "u-admin"},
        )
        response = config_routes_users.handle_user_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(len(update_calls), 1)
        call = update_calls[0]
        testbase.assert_equal(call["is_active"], True)
        testbase.assert_equal(call["role_names"], ["system-admin"])
    finally:
        for p in (update_patch, get_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_edit_post_self_lockout_re_renders_with_flash():
    """
    **Feature: self-lockout guard T2.8c**
    **Property: When the update service raises SelfLockoutError
    the edit form re-renders with the guard's message as an
    error flash instead of reporting success.**
    """
    _reset_global_state()
    sm_patch = None
    get_patch = None
    update_patch = None
    exc_patch = None
    roles_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_user_exception_classes()

        user = _FakeUserView(user_id="u-7", username="bob")

        def _get(*, db_session: Any, user_id: str) -> Optional[Any]:
            return user

        get_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_get_user",
            side_effect=_get,
        )

        def _update(**kwargs: Any) -> None:
            raise _FakeSelfLockoutError(
                "You cannot remove your own 'system-admin' role."
            )

        update_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_update_user",
            side_effect=_update,
        )

        def _list_roles(*, db_session: Any) -> List[Any]:
            return []

        roles_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_list_role_options",
            side_effect=_list_roles,
        )

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&email=b@example.com"
            b"&display_name=Bob&is_active=on"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"user_id": "u-7"},
        )
        response = config_routes_users.handle_user_edit(request)

        is_html = isinstance(response, HTMLResponse)
        testbase.assert_equal(is_html, True)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        category, message = ctx["flashes"][0]
        testbase.assert_equal(category, "error")
        contains = "system-admin" in message
        testbase.assert_equal(contains, True)
    finally:
        for p in (
            roles_patch, update_patch, get_patch, exc_patch, sm_patch,
        ):
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
    **Property: A valid deactivate POST calls the deactivate
    service with the acting admin id and redirects to
    /admin/users with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    deact_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_user_exception_classes()

        deact_calls: List[Dict[str, Any]] = []

        def _deactivate(**kwargs: Any) -> None:
            deact_calls.append(kwargs)
            return

        deact_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_deactivate_user",
            side_effect=_deactivate,
        )

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
        testbase.assert_equal(len(deact_calls), 1)
        testbase.assert_equal(deact_calls[0]["user_id"], "u-7")
        testbase.assert_equal(deact_calls[0]["actor_user_id"], "u-admin")
    finally:
        for p in (deact_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_deactivate_user_not_found_flashes_error():
    """
    **Feature: webworks config users port T2.9**
    **Property: The deactivate service raising the not-found
    error yields a redirect with a "User not found" flash.**
    """
    _reset_global_state()
    sm_patch = None
    deact_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_user_exception_classes()

        def _deactivate(**kwargs: Any) -> None:
            raise _FakeAdminNotFoundError("User u-ghost not found")

        deact_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_deactivate_user",
            side_effect=_deactivate,
        )

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
        for p in (deact_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_deactivate_self_lockout_flashes_error():
    """
    **Feature: self-lockout guard T2.9b**
    **Property: The deactivate service raising SelfLockoutError
    yields a redirect carrying the guard message as an error
    flash -- no success is reported.**
    """
    _reset_global_state()
    sm_patch = None
    deact_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_user_exception_classes()

        def _deactivate(**kwargs: Any) -> None:
            raise _FakeSelfLockoutError(
                "You cannot deactivate your own account."
            )

        deact_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_deactivate_user",
            side_effect=_deactivate,
        )

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"user_id": "u-admin"},
        )
        response = config_routes_users.handle_user_deactivate(request)

        # The guard produced a redirect back to the list (error
        # flash), not an exception and not a success redirect from
        # a completed deactivation.
        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/users"
        )
    finally:
        for p in (deact_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Roles
# ===========================================================================


def test_handle_role_list_renders_with_roles():
    """
    **Feature: webworks config roles port T2.10**
    **Property: GET /admin/roles renders config/roles/list.html
    with every RBAC role view.**
    """
    _reset_global_state()
    sm_patch = None
    list_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        roles = [
            _FakeRoleView(
                role_id="r-1", name="system-admin", is_system=True,
                binding_count=2,
            ),
            _FakeRoleView(role_id="r-2", name="viewer"),
        ]

        def _list(*, db_session: Any) -> List[Any]:
            return roles

        list_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_list_roles",
            side_effect=_list,
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = config_routes_roles.handle_role_list(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["roles"], roles)
    finally:
        if list_patch is not None:
            list_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_role_create_post_happy_path_persists_and_redirects():
    """
    **Feature: webworks config roles port T2.11**
    **Property: A valid POST calls the create service with the
    submitted permission keys and redirects to /admin/roles with
    a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    create_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_role_exception_classes()

        create_calls: List[Dict[str, Any]] = []

        def _create(**kwargs: Any) -> str:
            create_calls.append(kwargs)
            return "r-new"

        create_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_create_role",
            side_effect=_create,
        )

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=editor&description=Edit+stuff"
            b"&permission_keys=system:users.read"
            b"&permission_keys=system:users.write"
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
        testbase.assert_equal(len(create_calls), 1)
        call = create_calls[0]
        testbase.assert_equal(call["name"], "editor")
        testbase.assert_equal(
            call["permission_keys"],
            ["system:users.read", "system:users.write"],
        )
    finally:
        for p in (create_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_role_create_post_duplicate_name_re_renders_with_flash():
    """
    **Feature: webworks config roles port T2.11**
    **Property: When the create service raises the duplicate
    error, the handler re-renders the create form (400) with a
    "Role already exists" flash.**
    """
    _reset_global_state()
    sm_patch = None
    create_patch = None
    perms_patch = None
    exc_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_role_exception_classes()

        def _create(**kwargs: Any) -> str:
            raise _FakeAdminDuplicateError(
                'Role "editor" already exists.'
            )

        create_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_create_role",
            side_effect=_create,
        )

        def _perms() -> List[Any]:
            return []

        perms_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_list_catalog_permissions",
            side_effect=_perms,
        )

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
        for p in (perms_patch, create_patch, exc_patch, sm_patch):
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
    get_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        role = _FakeRoleView(role_id="r-7", name="editor")

        def _get(*, db_session: Any, role_id: str) -> Optional[Any]:
            return role

        get_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_get_role",
            side_effect=_get,
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"role_id": "r-7"},
        )
        response = config_routes_roles.handle_role_detail(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["role"], role)
    finally:
        if get_patch is not None:
            get_patch.deactivate()
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
    get_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _get(*, db_session: Any, role_id: str) -> Optional[Any]:
            return None

        get_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_get_role",
            side_effect=_get,
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"role_id": "r-99"},
        )
        response = config_routes_roles.handle_role_detail(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/roles"
        )
    finally:
        if get_patch is not None:
            get_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_role_edit_post_refuses_builtin_role():
    """
    **Feature: webworks config roles port T2.13**
    **Property: An edit POST against a role with is_system=True
    redirects to /admin/roles/{role_id} with a "Built-in roles
    cannot be modified" error flash and does NOT call the update
    service.**
    """
    _reset_global_state()
    sm_patch = None
    get_patch = None
    update_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        role = _FakeRoleView(
            role_id="r-1", name="system-admin", is_system=True
        )

        def _get(*, db_session: Any, role_id: str) -> Optional[Any]:
            return role

        get_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_get_role",
            side_effect=_get,
        )

        update_calls: List[Dict[str, Any]] = []

        def _update(**kwargs: Any) -> None:
            update_calls.append(kwargs)
            return

        update_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_update_role",
            side_effect=_update,
        )

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&description=tampered"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"role_id": "r-1"},
        )
        response = config_routes_roles.handle_role_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/roles/r-1"
        )
        testbase.assert_equal(update_calls, [])
    finally:
        for p in (update_patch, get_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_role_edit_post_happy_path_commits_and_redirects():
    """
    **Feature: webworks config roles port T2.13**
    **Property: A valid edit POST calls the update service with
    the submitted permission keys, then redirects to
    /admin/roles/{role_id} with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    get_patch = None
    update_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_role_exception_classes()
        role = _FakeRoleView(
            role_id="r-2", name="editor", is_system=False
        )

        def _get(*, db_session: Any, role_id: str) -> Optional[Any]:
            return role

        get_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_get_role",
            side_effect=_get,
        )

        update_calls: List[Dict[str, Any]] = []

        def _update(**kwargs: Any) -> None:
            update_calls.append(kwargs)
            return

        update_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_update_role",
            side_effect=_update,
        )

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&description=Updated+desc"
            b"&permission_keys=system:users.read"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"role_id": "r-2"},
        )
        response = config_routes_roles.handle_role_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/roles/r-2"
        )
        testbase.assert_equal(len(update_calls), 1)
        call = update_calls[0]
        testbase.assert_equal(call["role_id"], "r-2")
        testbase.assert_equal(call["description"], "Updated desc")
        testbase.assert_equal(
            call["permission_keys"], ["system:users.read"]
        )
    finally:
        for p in (update_patch, get_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_role_edit_post_empty_permissions_requires_confirmation():
    """
    **Feature: silent-wipe guard T2.13b**
    **Property: A POST with no permission boxes ticked and no
    confirm_remove_all acknowledgement does NOT call the update
    service and re-renders (400) with an explanatory error on the
    permissions field.**
    """
    _reset_global_state()
    sm_patch = None
    get_patch = None
    update_patch = None
    perms_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        role = _FakeRoleView(
            role_id="r-2", name="editor", is_system=False,
            permissions=[_FakePermView(key="system:users.read")],
        )

        def _get(*, db_session: Any, role_id: str) -> Optional[Any]:
            return role

        get_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_get_role",
            side_effect=_get,
        )

        update_calls: List[Dict[str, Any]] = []

        def _update(**kwargs: Any) -> None:
            update_calls.append(kwargs)
            return

        update_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_update_role",
            side_effect=_update,
        )

        def _perms() -> List[Any]:
            return [_FakePermView(key="system:users.read")]

        perms_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_list_catalog_permissions",
            side_effect=_perms,
        )

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&description=still+editor"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"role_id": "r-2"},
        )
        response = config_routes_roles.handle_role_edit(request)

        is_html = isinstance(response, HTMLResponse)
        testbase.assert_equal(is_html, True)
        testbase.assert_equal(update_calls, [])
        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["flashes"], [])
        testbase.assert_equal(list(ctx["errors"].keys()), ["permission_keys"])
        contains = "remove them all" in ctx["errors"]["permission_keys"]
        testbase.assert_equal(contains, True)
    finally:
        for p in (perms_patch, update_patch, get_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_role_edit_post_empty_permissions_with_confirmation_updates():
    """
    **Feature: silent-wipe guard T2.13c**
    **Property: A POST with no permission boxes ticked but WITH
    confirm_remove_all=on calls the update service with an empty
    key list.**
    """
    _reset_global_state()
    sm_patch = None
    get_patch = None
    update_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_role_exception_classes()
        role = _FakeRoleView(
            role_id="r-2", name="editor", is_system=False
        )

        def _get(*, db_session: Any, role_id: str) -> Optional[Any]:
            return role

        get_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_get_role",
            side_effect=_get,
        )

        update_calls: List[Dict[str, Any]] = []

        def _update(**kwargs: Any) -> None:
            update_calls.append(kwargs)
            return

        update_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_update_role",
            side_effect=_update,
        )

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&description=stripped"
            b"&confirm_remove_all=on"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"role_id": "r-2"},
        )
        response = config_routes_roles.handle_role_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(len(update_calls), 1)
        testbase.assert_equal(update_calls[0]["permission_keys"], [])
    finally:
        for p in (update_patch, get_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_role_delete_happy_path_reports_consequence():
    """
    **Feature: role delete T2.14**
    **Property: A valid delete POST calls the delete service and
    redirects to /admin/roles with a flash naming the role and
    the number of users who lost it.**
    """
    _reset_global_state()
    sm_patch = None
    get_patch = None
    delete_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_role_exception_classes()
        role = _FakeRoleView(
            role_id="r-2", name="editor", is_system=False,
            binding_count=3,
        )

        def _get(*, db_session: Any, role_id: str) -> Optional[Any]:
            return role

        get_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_get_role",
            side_effect=_get,
        )

        delete_calls: List[Dict[str, Any]] = []

        def _delete(**kwargs: Any) -> int:
            delete_calls.append(kwargs)
            return 3

        delete_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_delete_role",
            side_effect=_delete,
        )

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"role_id": "r-2"},
        )
        response = config_routes_roles.handle_role_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/roles"
        )
        testbase.assert_equal(len(delete_calls), 1)
        testbase.assert_equal(delete_calls[0]["role_id"], "r-2")
    finally:
        for p in (delete_patch, get_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_role_delete_builtin_refused():
    """
    **Feature: role delete T2.14b**
    **Property: The delete service raising
    BuiltinRoleProtectedError yields a redirect to the role
    detail page with the protection message -- no success.**
    """
    _reset_global_state()
    sm_patch = None
    get_patch = None
    delete_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_role_exception_classes()
        role = _FakeRoleView(
            role_id="r-1", name="system-admin", is_system=True
        )

        def _get(*, db_session: Any, role_id: str) -> Optional[Any]:
            return role

        get_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_get_role",
            side_effect=_get,
        )

        def _delete(**kwargs: Any) -> int:
            raise _FakeBuiltinRoleProtectedError(
                'Role "system-admin" is a built-in role and cannot '
                "be deleted."
            )

        delete_patch = _patch_seam(
            module=config_routes_roles,
            seam_name="_svc_delete_role",
            side_effect=_delete,
        )

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"role_id": "r-1"},
        )
        response = config_routes_roles.handle_role_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/roles/r-1"
        )
    finally:
        for p in (delete_patch, get_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# END-TO-END TRUTH TESTS -- the success messages must be true.
#
# These run the REAL identity_admin service against an in-memory
# Phase-1 database (only the auth gate + templates are stubbed):
#
# 1. A user created through handle_user_create can authenticate
#    through local_flow.verify_local_credentials.
# 2. A catalog role granted through handle_user_edit flips
#    rbac_evaluator.check_permission to allowed.
# 3. A CUSTOM role created through handle_role_create (grants
#    stored as rbac_role_permissions rows) also flips
#    rbac_evaluator.check_permission once bound.
# ===========================================================================


#: Ambient pepper captured by :func:`_setup_real_stack` so the
#: truth tests can restore it on the way out. ``False`` means "no
#: truth test has run"; ``None`` means "no pepper was active".
_AMBIENT_PEPPER_STASH: Any = False


def _restore_ambient_pepper() -> None:
    """
        Restore the pepper that was active before
        :func:`_setup_real_stack` replaced it. A no-op when no
        truth test has run in this process.
    """
    global _AMBIENT_PEPPER_STASH
    if _AMBIENT_PEPPER_STASH is False:
        return

    from ccai.pychestrate.webservice.security.auth.pepper_loader import (
        reset_active_pepper_for_testing,
        set_active_pepper,
    )

    reset_active_pepper_for_testing()
    if _AMBIENT_PEPPER_STASH is not None:
        set_active_pepper(pepper=_AMBIENT_PEPPER_STASH)
    _AMBIENT_PEPPER_STASH = False
    return


def _setup_real_stack() -> Any:
    """
        Bootstrap the Phase-1 runtime for a truth test: extension
        registry (hashers, catalog packs), pepper, backoff reset,
        and an in-memory database. Returns the engine.
    """
    from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
    from ccai.pychestrate.webservice.security.auth import local_flow
    from ccai.errors.exceptions import ConfigurationError
    from ccai.pychestrate.webservice.security.auth.pepper_loader import (
        get_active_pepper,
        reset_active_pepper_for_testing,
        set_active_pepper,
    )
    from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
        build_in_memory_session,
        reset_phase1_runtime,
    )

    # Stash whatever pepper is active so the truth test can put
    # it back afterwards. Clearing the pepper permanently would
    # poison later modules in a shared-process suite run: the
    # e2e harness seeds its users under the ambient pepper and
    # only installs its own constant when none is active, so a
    # clear here makes every later e2e login verify against the
    # wrong pepper (8 e2e failures in the full phase10 run).
    # ``get_active_pepper`` raises ConfigurationError when nothing
    # is loaded, which is the ordinary case for a standalone module
    # run. Catch that type by name rather than ``Exception``:
    # ConfigurationError derives from BaseException, so an
    # ``except Exception`` here silently fails to catch it and the
    # probe takes the whole test down.
    global _AMBIENT_PEPPER_STASH
    try:
        _AMBIENT_PEPPER_STASH = get_active_pepper()
    except ConfigurationError:
        _AMBIENT_PEPPER_STASH = None

    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p13e-truth-test-pepper"))
    local_flow.reset_backoff_for_testing()

    engine, session = build_in_memory_session()
    session.close()
    rtnval = engine
    return rtnval


def _install_engine_session_factory(*, engine: Any) -> None:
    """
        Point SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY at the
        in-memory engine so the handlers open real sessions.
    """
    from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
        session_for,
    )

    def factory() -> Any:
        return session_for(engine=engine)

    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = factory
    return


def test_truth_user_created_via_route_can_log_in():
    """
    **Feature: END-TO-END TRUTH (users)**
    **Property: POST /admin/users/create writes the modern
    identity store -- the created user authenticates through
    local_flow.verify_local_credentials with the submitted
    password. The success message is TRUE.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        engine = _setup_real_stack()
        _install_engine_session_factory(engine=engine)
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&username=worker&email=worker@example.com"
            b"&password=CorrectHorse9!Battery&display_name=Worker"
            b"&firstname=Wor&lastname=Ker"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_users.handle_user_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/users"
        )

        # THE TRUTH CHECK: the freshly created user can log in
        # through the real local credential flow.
        from ccai.pychestrate.webservice.security.auth import local_flow
        from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
            session_for,
        )

        verify_session = session_for(engine=engine)
        try:
            result = local_flow.verify_local_credentials(
                login_name="worker",
                password="CorrectHorse9!Battery",
                mfa_code=None,
                source_ip="127.0.0.1",
                db_session=verify_session,
            )
            has_user_id = len(result.user_id) > 0
            testbase.assert_equal(has_user_id, True)

            # The identity row is the one the route created.
            from ccai.pychestrate.webservice.identity.users.models import (
                IdentityUser,
            )
            row = (
                verify_session.query(IdentityUser)
                .filter(IdentityUser.login_name == "worker")
                .first()
            )
            testbase.assert_equal(str(row.user_id), result.user_id)

            # The user also appears on the real list + detail reads
            # (the legacy-name join tolerates the absent legacy
            # table in this schema).
            from ccai.pychestrate.webservice.webinterface.blueprints.config import (
                identity_admin,
            )
            listing = identity_admin.list_identity_users(
                db_session=verify_session,
                offset=0,
                limit=20,
                search=None,
            )
            listed_logins = [entry.username for entry in listing.users]
            testbase.assert_equal("worker" in listed_logins, True)

            detail = identity_admin.get_identity_user(
                db_session=verify_session,
                user_id=result.user_id,
            )
            testbase.assert_equal(detail.username, "worker")
            testbase.assert_equal(detail.is_active, True)
        finally:
            verify_session.close()
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _restore_ambient_pepper()
        _reset_global_state()
    return


def test_truth_role_granted_via_route_changes_rbac_decision():
    """
    **Feature: END-TO-END TRUTH (roles)**
    **Property: Granting system-admin through POST
    /admin/users/{id}/edit creates a real SYSTEM-scope
    RbacRoleBinding -- rbac_evaluator.check_permission flips from
    denied to allowed for the target user.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        engine = _setup_real_stack()
        _install_engine_session_factory(engine=engine)
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        from datetime import datetime, timezone

        from ccai.pychestrate.webservice.security.auth.models import (
            AuthProviderKind,
        )
        from ccai.pychestrate.webservice.security.auth.session_service import (
            AuthPrincipal,
        )
        from ccai.pychestrate.webservice.security.rbac import rbac_evaluator
        from ccai.pychestrate.webservice.webinterface.blueprints.config import (
            identity_admin,
        )
        from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
            session_for,
        )

        # Seed the target user through the real service.
        create_session = session_for(engine=engine)
        try:
            user_id = identity_admin.create_identity_user(
                db_session=create_session,
                username="grantee",
                email="grantee@example.com",
                password="CorrectHorse9!Battery",
                display_name="Grantee",
                firstname="",
                lastname="",
                role_names=[],
                actor_user_id=None,
            )
        finally:
            create_session.close()

        principal = AuthPrincipal(
            user_id=user_id,
            session_id="truth-session",
            provider_kind=AuthProviderKind.LOCAL,
            provider_name="local",
        )

        # BEFORE: no binding, permission denied.
        before_session = session_for(engine=engine)
        try:
            before = rbac_evaluator.check_permission(
                db_session=before_session,
                principal=principal,
                permission_key="system:users.write",
                now=datetime.now(timezone.utc),
            )
            testbase.assert_equal(before.allowed, False)
        finally:
            before_session.close()

        # Grant system-admin through the route handler.
        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&email=grantee@example.com"
            b"&display_name=Grantee&firstname=&lastname="
            b"&is_active=on&role_names=system-admin"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"user_id": user_id},
        )
        response = config_routes_users.handle_user_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)

        # AFTER: the evaluator answers True. The success message
        # is TRUE.
        after_session = session_for(engine=engine)
        try:
            after = rbac_evaluator.check_permission(
                db_session=after_session,
                principal=principal,
                permission_key="system:users.write",
                now=datetime.now(timezone.utc),
            )
            testbase.assert_equal(after.allowed, True)
            testbase.assert_equal(after.reason, "binding_allow")
        finally:
            after_session.close()
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _restore_ambient_pepper()
        _reset_global_state()
    return


def test_truth_custom_role_created_via_route_grants_access():
    """
    **Feature: END-TO-END TRUTH (custom roles)**
    **Property: A custom role created through POST
    /admin/roles/create stores its grants as
    rbac_role_permissions rows, and once bound to a user the
    evaluator honours those DB grants -- check_permission flips
    to allowed for exactly the granted key.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        engine = _setup_real_stack()
        _install_engine_session_factory(engine=engine)
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        from datetime import datetime, timezone

        from ccai.pychestrate.webservice.security.auth.models import (
            AuthProviderKind,
        )
        from ccai.pychestrate.webservice.security.auth.session_service import (
            AuthPrincipal,
        )
        from ccai.pychestrate.webservice.security.rbac import rbac_evaluator
        from ccai.pychestrate.webservice.webinterface.blueprints.config import (
            identity_admin,
        )
        from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
            session_for,
        )

        # Create the custom role through the route handler.
        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=support-auditor"
            b"&description=Read+audit+records"
            b"&permission_keys=system:audit.read"
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

        # Seed a user and bind the custom role via the service.
        work_session = session_for(engine=engine)
        try:
            user_id = identity_admin.create_identity_user(
                db_session=work_session,
                username="auditee",
                email="auditee@example.com",
                password="CorrectHorse9!Battery",
                display_name="Auditee",
                firstname="",
                lastname="",
                role_names=["support-auditor"],
                actor_user_id=None,
            )
        finally:
            work_session.close()

        principal = AuthPrincipal(
            user_id=user_id,
            session_id="truth-session",
            provider_kind=AuthProviderKind.LOCAL,
            provider_name="local",
        )

        check_session = session_for(engine=engine)
        try:
            granted = rbac_evaluator.check_permission(
                db_session=check_session,
                principal=principal,
                permission_key="system:audit.read",
                now=datetime.now(timezone.utc),
            )
            testbase.assert_equal(granted.allowed, True)

            # A key the custom role does NOT grant stays denied.
            not_granted = rbac_evaluator.check_permission(
                db_session=check_session,
                principal=principal,
                permission_key="system:users.write",
                now=datetime.now(timezone.utc),
            )
            testbase.assert_equal(not_granted.allowed, False)
        finally:
            check_session.close()
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _restore_ambient_pepper()
        _reset_global_state()
    return


# ===========================================================================
# Role assignment needs system:rbac.admin (XC-01)
# ===========================================================================


def test_handle_user_create_without_rbac_admin_creates_the_user_without_roles():
    """
    **Feature: admin page permission gate (XC-01)**
    **Property: when the acting user lacks system:rbac.admin, a
    create POST that names roles still creates the account but with
    no roles -- a user manager cannot hand out system-admin.**
    """
    _reset_global_state()
    sm_patch = None
    create_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_user_exception_classes()
        _FakeSecurityManager.denied_permissions = ["system:rbac.admin"]

        create_calls: List[Dict[str, Any]] = []

        def _create(**kwargs: Any) -> str:
            create_calls.append(kwargs)
            return "u-new"

        create_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_create_user",
            side_effect=_create,
        )

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&username=newbie&email=n@example.com"
            b"&password=Sup3rS3cr3t!&display_name=Newbie"
            b"&firstname=New&lastname=Bie"
            b"&role_names=system-admin"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        config_routes_users.handle_user_create(request)

        testbase.assert_equal(
            [call["role_names"] for call in create_calls], [[]]
        )
    finally:
        for p in (create_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_user_edit_without_rbac_admin_keeps_the_current_roles():
    """
    **Feature: admin page permission gate (XC-01)**
    **Property: when the acting user lacks system:rbac.admin, an edit
    POST that changes the target's roles saves the target's current
    roles instead of the submitted ones.**
    """
    _reset_global_state()
    sm_patch = None
    get_patch = None
    update_patch = None
    exc_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        exc_patch = _patch_user_exception_classes()
        _FakeSecurityManager.denied_permissions = ["system:rbac.admin"]

        get_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_get_user",
            side_effect=lambda **kwargs: _FakeUserView(
                user_id="u-7", roles=["viewer"]
            ),
        )
        update_calls: List[Dict[str, Any]] = []

        def _update(**kwargs: Any) -> None:
            update_calls.append(kwargs)
            return

        update_patch = _patch_seam(
            module=config_routes_users,
            seam_name="_svc_update_user",
            side_effect=_update,
        )

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&email=new@example.com"
            b"&display_name=Updated&firstname=New&lastname=Name"
            b"&is_active=on&role_names=system-admin"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"user_id": "u-7"},
        )
        config_routes_users.handle_user_edit(request)

        testbase.assert_equal(
            [call["role_names"] for call in update_calls], [["viewer"]]
        )
    finally:
        for p in (update_patch, get_patch, exc_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# END-TO-END TRUTH: deactivation ends the user's sessions (ADM-03)
# ===========================================================================


def _seed_user_with_open_session(*, engine: Any, username: str) -> str:
    """
        Create an identity user through the real service and open
        one sign-in session for them. Returns the user id.
    """
    from ccai.pychestrate.webservice.security.auth import session_service
    from ccai.pychestrate.webservice.security.auth.models import (
        AuthProviderKind,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (
        identity_admin,
    )
    from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
        session_for,
    )

    create_session = session_for(engine=engine)
    try:
        user_id = identity_admin.create_identity_user(
            db_session=create_session,
            username=username,
            email="{}@example.com".format(username),
            password="CorrectHorse9!Battery",
            display_name=username.title(),
            firstname="",
            lastname="",
            role_names=[],
            actor_user_id=None,
        )
    finally:
        create_session.close()

    open_db = session_for(engine=engine)
    try:
        session_service.open_session(
            db_session=open_db,
            user_id=user_id,
            provider_kind=AuthProviderKind.LOCAL,
            provider_name="local",
            mfa_method_name=None,
            access_token_payload=None,
            refresh_token_payload=None,
            request_fingerprint=session_service.RequestFingerprint(
                ip_fingerprint="ip", user_agent_fingerprint="ua",
            ),
            idle_timeout_seconds=1800,
            max_lifetime_seconds=3600,
        )
        open_db.commit()
    finally:
        open_db.close()
    return user_id


def _count_sessions_for(*, engine: Any, user_id: str) -> int:
    import uuid

    from ccai.pychestrate.webservice.security.auth.models import AuthSession
    from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
        session_for,
    )

    count_db = session_for(engine=engine)
    try:
        rtnval = (
            count_db.query(AuthSession)
            .filter(AuthSession.user_id == uuid.UUID(str(user_id)))
            .count()
        )
    finally:
        count_db.close()
    return rtnval


def test_truth_deactivate_route_closes_the_users_sessions():
    """
    **Feature: END-TO-END TRUTH (ADM-03)**
    **Property: POST /admin/users/{id}/deactivate closes every open
    sign-in session of that user, so their access ends immediately
    instead of when the session would have expired.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        engine = _setup_real_stack()
        _install_engine_session_factory(engine=engine)
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        user_id = _seed_user_with_open_session(engine=engine, username="leaver")

        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: _build_authenticated_cookie()},
            body=b"csrf_token=csrf-fresh",
            path_params={"user_id": user_id},
        )
        config_routes_users.handle_user_deactivate(request)

        testbase.assert_equal(
            _count_sessions_for(engine=engine, user_id=user_id), 0
        )
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _restore_ambient_pepper()
        _reset_global_state()
    return


def test_truth_edit_route_deactivation_closes_the_users_sessions():
    """
    **Feature: END-TO-END TRUTH (ADM-03)**
    **Property: saving the edit form with "active" unchecked also
    closes every open sign-in session of that user.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        engine = _setup_real_stack()
        _install_engine_session_factory(engine=engine)
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        user_id = _seed_user_with_open_session(engine=engine, username="mover")

        body = (
            b"csrf_token=csrf-fresh&email=mover@example.com"
            b"&display_name=Mover&firstname=&lastname="
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: _build_authenticated_cookie()},
            body=body,
            path_params={"user_id": user_id},
        )
        config_routes_users.handle_user_edit(request)

        testbase.assert_equal(
            _count_sessions_for(engine=engine, user_id=user_id), 0
        )
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _restore_ambient_pepper()
        _reset_global_state()
    return
