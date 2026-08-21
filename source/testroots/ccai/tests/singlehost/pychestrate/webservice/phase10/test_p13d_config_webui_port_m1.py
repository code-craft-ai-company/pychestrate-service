"""
.. module:: test_p13d_config_webui_port_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the D1 slice of the config blueprint
               port (auth + dashboard routes).

.. moduleauthor:: Code Craft AI LLC

PR D1 ports the auth + dashboard surface of the flask config
blueprint to webworks. These tests cover:

* ``register_config_routes`` registers the documented routes +
  pre-registers the future-PR endpoint patterns so url_for
  resolves at template render time.
* ``handle_login_form`` (GET) renders the login template +
  drains queued flashes.
* ``handle_login_submit`` (POST) -- happy + bad-input + auth-
  failure paths, including the ``next`` query-param redirect.
* ``handle_logout`` (POST) calls ``SecurityManager.logout`` and
  returns a 303 redirect to the login page with a fresh empty
  session.
* ``handle_dashboard`` (GET) -- anonymous, expired-token, and
  happy paths.
* ``runtime_bootstrap._load_ui_cookie_secret_or_none`` -- file +
  env + None + short-material paths.

The url_for shim and templating singleton are reset in each
test that touches them so cross-test state never bleeds.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile

from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.errors.exceptions import ConfigurationError
from ccai.testbase.mocking import create_module_patch
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice import runtime_bootstrap
from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from ccai.pychestrate.webservice.webinterface.blueprints.config import (
    routes as config_routes,
)
from ccai.pychestrate.webservice.webinterface.foundation import (
    cookie_session,
    csrf,
    flash,
    templating,
    url_for as url_for_module,
)


# ---------------------------------------------------------------------------
# Test stubs
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
        cookies: Optional[Dict[str, str]] = None,
        form: Optional[Dict[str, Any]] = None,
        form_raises: bool = False,
        query_mapping: Optional[Dict[str, str]] = None,
        header_mapping: Optional[Dict[str, str]] = None,
        method: str = "GET",
    ) -> None:
        self.cookies: Dict[str, str] = cookies if cookies is not None else {}
        self._form: Dict[str, Any] = form if form is not None else {}
        self._form_raises: bool = form_raises
        self.query_params: _FakeQueryParams = _FakeQueryParams(
            mapping=query_mapping
        )
        self.headers: _FakeHeaders = _FakeHeaders(mapping=header_mapping)
        self.method: str = method
        return

    def form(self) -> Dict[str, Any]:
        if self._form_raises is True:
            raise ValueError("body decode failed")
        return self._form


class _FakeApp:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[str, ...], Callable]] = []
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


class _FakeAuthResponse:
    def __init__(
            self, *, user_id: str, username: str, token: str,
            csrf_token: str
        ) -> None:
        self.user_id: str = user_id
        self.username: str = username
        self.token: str = token
        self.csrf_token: str = csrf_token
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
        Captures arguments passed to authenticate / logout /
        validate_token. Configurable per-test via the
        ``configure_*`` factories so each test owns the behavior.
    """

    last_instance: Optional["_FakeSecurityManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.authenticate_calls: List[Any] = []
        self.logout_calls: List[str] = []
        self.validate_token_calls: List[str] = []
        self.authenticate_response: Optional[_FakeAuthResponse] = None
        self.authenticate_raises: bool = False
        self.validate_token_response: Optional[_FakeSessionInfo] = None
        self.logout_raises: bool = False
        _FakeSecurityManager.last_instance = self
        return

    def authenticate(self, request: Any) -> _FakeAuthResponse:
        self.authenticate_calls.append(request)
        if self.authenticate_raises is True:
            raise RuntimeError("auth failure")
        return self.authenticate_response

    def logout(self, token: str) -> None:
        self.logout_calls.append(token)
        if self.logout_raises is True:
            raise RuntimeError("logout failure")
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
        rtnval = "RENDERED:{}".format(self.name)
        return rtnval


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


# ---------------------------------------------------------------------------
# Test setup helpers
# ---------------------------------------------------------------------------


def _install_stub_environment() -> _StubJinjaEnvironment:
    env = _StubJinjaEnvironment()
    templating.set_default_environment(environment=env)
    return env


def _install_ui_cookie_secret(*, secret: bytes = _TEST_UI_COOKIE_SECRET) -> None:
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = secret
    return


def _install_db_session_factory(
        *, db_session: Optional[Any]
    ) -> None:
    """
        Install a single-call factory on
        SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY that returns
        ``db_session``. Tests then verify the handler closed it.
    """
    def factory() -> Any:
        rtnval = db_session
        return rtnval

    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = factory
    return


def _reset_global_state() -> None:
    """
        Clear cross-test bleed: the url_for registry, the jinja
        default env, the SITE_SHARED_GLOBALS bootstrap fields the
        tests poke at, and the _FakeSecurityManager class-level
        ``last_instance`` recorder.
    """
    url_for_module.reset_registry_for_testing()
    templating.reset_default_environment_for_testing()
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = None
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = None
    _FakeSecurityManager.last_instance = None
    return


def _patch_security_manager(
        *, side_effect: Optional[Callable[..., Any]] = None
    ) -> Any:
    """
        Replace the routes module's ``_build_security_manager``
        helper with a stub that returns a fake. The routes module
        keeps the SecurityManager construction behind a single
        helper exactly so tests can patch it without importing
        the werkzeug-using source module.

        :param side_effect: Optional callable. Called as
                            ``builder(db_session=...)``; must
                            return the SecurityManager-like
                            object the handler will use. Defaults
                            to ``_FakeSecurityManager``.

        :returns: Patch handle. Caller must ``.deactivate()`` in
                  cleanup.
    """
    if side_effect is None:
        def _default_builder(*, db_session: Any) -> _FakeSecurityManager:
            rtnval = _FakeSecurityManager(db_session)
            return rtnval
        builder: Callable[..., Any] = _default_builder
    else:
        # Wrap the test-supplied positional builder into one that
        # accepts the kwarg shape the handler calls with.
        def _kwarg_adapter(*, db_session: Any) -> Any:
            rtnval = side_effect(db_session)
            return rtnval
        builder = _kwarg_adapter

    patch = create_module_patch(
        config_routes, "_build_security_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=builder)
    return patch


def _patch_auth_request_factory() -> Any:
    """
        Replace the routes module's ``_build_auth_request`` helper
        with one that builds a simple namespace object so tests
        can inspect the username/password/client_ip/user_agent
        passed in. Keeps the AuthRequest source class out of the
        test's import graph.
    """
    class _NamespaceAuthRequest:
        def __init__(
                self, *, username: str, password: str,
                client_ip: str, user_agent: str
            ) -> None:
            self.username: str = username
            self.password: str = password
            self.client_ip: str = client_ip
            self.user_agent: str = user_agent
            return

    def _builder(
            *, username: str, password: str,
            client_ip: str, user_agent: str
        ) -> _NamespaceAuthRequest:
        rtnval = _NamespaceAuthRequest(
            username=username,
            password=password,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        return rtnval

    patch = create_module_patch(
        config_routes, "_build_auth_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_config_routes_attaches_documented_routes():
    """
    **Feature: webworks config blueprint port T1.1 (D1)**
    **Property: register_config_routes attaches the five
    documented D1 routes (login GET/POST, logout, dashboard
    root + /dashboard) at ``/config*``. Asserted as a subset
    so the D2/D3 per-feature route attachments (which the
    same registrar dispatches to) do not break this contract.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected_subset = {
            ("/login", ("GET",)),
            ("/login", ("POST",)),
            ("/logout", ("GET", "POST")),
            ("/admin", ("GET",)),
            ("/admin/dashboard", ("GET",)),
        }
        missing = expected_subset - actual
        testbase.assert_equal(missing, set())
    finally:
        _reset_global_state()
    return


def test_register_config_routes_registers_endpoint_names_for_d1_routes():
    """
    **Feature: webworks config blueprint port T1.1 (D1)**
    **Property: register_config_routes populates the url_for
    registry so templates can resolve url_for('config.login')
    etc.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        snapshot = url_for_module.get_registry_snapshot()
        testbase.assert_equal(snapshot["config.login"], "/login")
        testbase.assert_equal(snapshot["config.logout"], "/logout")
        testbase.assert_equal(snapshot["config.dashboard"], "/admin/dashboard")
        testbase.assert_equal(snapshot["config.dashboard_root"], "/admin")
    finally:
        _reset_global_state()
    return


def test_register_config_routes_pre_registers_future_endpoint_patterns():
    """
    **Feature: webworks config blueprint port T1.1 (D1)**
    **Property: register_config_routes pre-registers the URL
    patterns for D2/D3/D4 endpoints (user_list / role_list /
    variable_list / scope_list / secret_list / session_list /
    audit_log_list) so the dashboard render does not crash at
    url_for() time before those handlers ship.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        snapshot = url_for_module.get_registry_snapshot()
        for endpoint in (
            "config.user_list",
            "config.role_list",
            "config.variable_list",
            "config.scope_list",
            "config.secret_list",
            "config.session_list",
            "config.audit_log_list",
        ):
            testbase.assert_equal(endpoint in snapshot, True)
        # And: future endpoints with path params keep their {name}
        # placeholder so url_for can substitute kwargs.
        testbase.assert_equal(
            snapshot["config.user_detail"], "/admin/users/{user_id}"
        )
    finally:
        _reset_global_state()
    return


# ===========================================================================
# handle_login_form (GET /login)
# ===========================================================================


def test_handle_login_form_renders_login_template_with_drained_flashes():
    """
    **Feature: webworks config blueprint port T1.2 (D1)**
    **Property: GET /login renders config/login.html with
    the drained flashes list and writes the (now-cleared)
    session cookie back on the response.**
    """
    _reset_global_state()
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()

        # Seed the inbound cookie with a queued flash so we can
        # observe the drain.
        cookie_value = cookie_session.sign_session_payload(
            payload={
                flash.SESSION_KEY: [["info", "first-msg"]],
            },
            secret=_TEST_UI_COOKIE_SECRET,
        )
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
        )
        response = config_routes.handle_login_form(request)

        is_html = isinstance(response, HTMLResponse)
        testbase.assert_equal(is_html, True)
        testbase.assert_equal(response.status_code, 200)

        # Template lookup + context shape
        testbase.assert_equal(env.template_lookups, ["config/login.html"])
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["request_endpoint"], "config.login")
        testbase.assert_equal(ctx["flashes"], [("info", "first-msg")])
        testbase.assert_equal(ctx["username"], "")
    finally:
        _reset_global_state()
    return


# ===========================================================================
# handle_login_submit (POST /login)
# ===========================================================================


def test_handle_login_submit_returns_400_when_username_or_password_missing():
    """
    **Feature: webworks config blueprint port T1.3 (D1)**
    **Property: An empty username or password re-renders the
    login form with a 400 status and an error-category flash.**
    """
    _reset_global_state()
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()

        request = _FakeRequest(
            form={"username": "", "password": "something"},
        )
        response = config_routes.handle_login_submit(request)

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        # The flash queued by the handler is drained into the
        # context's flashes list (one error-category entry).
        testbase.assert_equal(len(ctx["flashes"]), 1)
        testbase.assert_equal(ctx["flashes"][0][0], "error")
    finally:
        _reset_global_state()
    return


def test_handle_login_submit_happy_path_redirects_to_root():
    """
    **Feature: webworks config blueprint port T1.3 (D1, p17b)**
    **Property: A successful authenticate call yields a 303
    RedirectResponse to ``/`` (the same-origin fallback target
    when no ``next`` query parameter is present). The session
    cookie written on the redirect carries user_id, username,
    session_token, and csrf_token from the AuthResponse.**
    """
    _reset_global_state()
    sm_patch = None
    ar_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        _install_db_session_factory(db_session=db_session)
        # Pre-register endpoints so url_for("config.dashboard")
        # resolves.
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        # The handler builds SecurityManager(db_session) inline.
        # Patch SecurityManager so the fake constructor seeds an
        # AuthResponse for the upcoming authenticate() call.
        def _build_with_response(db_session_arg: Any) -> _FakeSecurityManager:
            instance = _FakeSecurityManager(db_session_arg)
            instance.authenticate_response = _FakeAuthResponse(
                user_id="u-1",
                username="admin",
                token="tok-abc",
                csrf_token="csrf-xyz",
            )
            return instance

        _FakeSecurityManager.last_instance = None
        sm_patch = _patch_security_manager(side_effect=_build_with_response)
        ar_patch = _patch_auth_request_factory()

        request = _FakeRequest(
            form={"username": "admin", "password": "pw"},
        )
        response = config_routes.handle_login_submit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(response.status_code, 303)
        testbase.assert_equal(
            response.headers["Location"], "/"
        )
        # SecurityManager was constructed with the resolved db
        # session AND received the AuthRequest.
        instance = _FakeSecurityManager.last_instance
        testbase.assert_equal(instance.db_session is db_session, True)
        testbase.assert_equal(len(instance.authenticate_calls), 1)
        ar = instance.authenticate_calls[0]
        testbase.assert_equal(ar.username, "admin")
        testbase.assert_equal(ar.password, "pw")
        # DB session closed.
        testbase.assert_equal(db_session.close_count, 1)
    finally:
        if ar_patch is not None:
            ar_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_login_submit_honors_next_query_param_on_success():
    """
    **Feature: webworks config blueprint port T1.3 (D1)**
    **Property: When the request URL carries ``?next=/admin/users``,
    the redirect lands on that path rather than the dashboard.**
    """
    _reset_global_state()
    sm_patch = None
    ar_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        def _build_with_response(db_session_arg: Any) -> _FakeSecurityManager:
            instance = _FakeSecurityManager(db_session_arg)
            instance.authenticate_response = _FakeAuthResponse(
                user_id="u-1",
                username="admin",
                token="tok",
                csrf_token="csrf",
            )
            return instance

        sm_patch = _patch_security_manager(side_effect=_build_with_response)
        ar_patch = _patch_auth_request_factory()

        request = _FakeRequest(
            form={"username": "admin", "password": "pw"},
            query_mapping={"next": "/admin/users"},
        )
        response = config_routes.handle_login_submit(request)

        testbase.assert_equal(response.status_code, 303)
        testbase.assert_equal(
            response.headers["Location"], "/admin/users"
        )
    finally:
        if ar_patch is not None:
            ar_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_login_form_threads_validated_next_into_context():
    """
    **Feature: unified login next-threading (audit fix)**
    **Property: GET /login?next=/runs passes the validated target
    into the template context as ``next_target`` so the form can
    carry it in a hidden field. An unsafe candidate (absolute
    URL) is rejected and the context carries an empty string.**
    """
    _reset_global_state()
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()

        request = _FakeRequest(query_mapping={"next": "/runs"})
        config_routes.handle_login_form(request)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["next_target"], "/runs")

        request = _FakeRequest(
            query_mapping={"next": "https://evil.example/x"}
        )
        config_routes.handle_login_form(request)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["next_target"], "")
    finally:
        _reset_global_state()
    return


def test_handle_login_submit_prefers_form_next_over_query():
    """
    **Feature: unified login next-threading (audit fix)**
    **Property: The POST handler reads ``next`` from the form
    body (the hidden field the login form carries) before falling
    back to the query string, so the target survives the form
    round-trip even when the browser drops the query string.**
    """
    _reset_global_state()
    sm_patch = None
    ar_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        def _build_with_response(db_session_arg: Any) -> _FakeSecurityManager:
            instance = _FakeSecurityManager(db_session_arg)
            instance.authenticate_response = _FakeAuthResponse(
                user_id="u-1",
                username="admin",
                token="tok",
                csrf_token="csrf",
            )
            return instance

        sm_patch = _patch_security_manager(side_effect=_build_with_response)
        ar_patch = _patch_auth_request_factory()

        request = _FakeRequest(
            form={
                "username": "admin",
                "password": "pw",
                "next": "/runs",
            },
            query_mapping={"next": "/somewhere-else"},
        )
        response = config_routes.handle_login_submit(request)

        testbase.assert_equal(response.status_code, 303)
        testbase.assert_equal(response.headers["Location"], "/runs")
    finally:
        if ar_patch is not None:
            ar_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_login_submit_rejects_unsafe_form_next():
    """
    **Feature: unified login next-threading (audit fix)**
    **Property: An unsafe ``next`` in the form body (absolute
    URL) is rejected by the same-origin validator and the
    redirect falls back to ``/``.**
    """
    _reset_global_state()
    sm_patch = None
    ar_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        def _build_with_response(db_session_arg: Any) -> _FakeSecurityManager:
            instance = _FakeSecurityManager(db_session_arg)
            instance.authenticate_response = _FakeAuthResponse(
                user_id="u-1",
                username="admin",
                token="tok",
                csrf_token="csrf",
            )
            return instance

        sm_patch = _patch_security_manager(side_effect=_build_with_response)
        ar_patch = _patch_auth_request_factory()

        request = _FakeRequest(
            form={
                "username": "admin",
                "password": "pw",
                "next": "https://evil.example/phish",
            },
        )
        response = config_routes.handle_login_submit(request)

        testbase.assert_equal(response.status_code, 303)
        testbase.assert_equal(response.headers["Location"], "/")
    finally:
        if ar_patch is not None:
            ar_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_login_submit_queues_no_welcome_flash_on_success():
    """
    **Feature: login flash hygiene (audit fix)**
    **Property: A successful login queues NO flash on the session
    cookie written with the redirect. The shell document the
    browser lands on never drains the flash queue, so a queued
    greeting would surface minutes later on an unrelated legacy
    page instead.**
    """
    _reset_global_state()
    sm_patch = None
    ar_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        def _build_with_response(db_session_arg: Any) -> _FakeSecurityManager:
            instance = _FakeSecurityManager(db_session_arg)
            instance.authenticate_response = _FakeAuthResponse(
                user_id="u-1",
                username="admin",
                token="tok",
                csrf_token="csrf",
            )
            return instance

        sm_patch = _patch_security_manager(side_effect=_build_with_response)
        ar_patch = _patch_auth_request_factory()

        request = _FakeRequest(
            form={"username": "admin", "password": "pw"},
        )
        response = config_routes.handle_login_submit(request)

        testbase.assert_equal(response.status_code, 303)
        morsel = response._cookies[cookie_session.COOKIE_NAME]
        payload = cookie_session.verify_session_payload(
            cookie_value=morsel.value,
            secret=_TEST_UI_COOKIE_SECRET,
        )
        testbase.assert_equal(payload is not None, True)
        flash_queue = payload.get(flash.SESSION_KEY, [])
        testbase.assert_equal(flash_queue, [])
    finally:
        if ar_patch is not None:
            ar_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_login_submit_surfaces_lockout_and_flattens_inactive():
    """
    **Feature: login failure messaging (audit fix)**
    **Property: The rate-limit lockout message is surfaced
    verbatim (it is keyed by (login_name, source_ip) and fires
    for unknown usernames too, so it is not an enumeration
    oracle). The inactive-account message flattens to the
    generic "Invalid username or password." text because the
    inactive check fires before password verification and would
    otherwise confirm account existence to anyone submitting any
    password for that username.**
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (
        auth_adapter,
    )

    message_expectations = (
        (
            "Too many recent failures; try again later",
            "Too many recent failures; try again later",
        ),
        (
            "Account is not active",
            "Invalid username or password.",
        ),
    )

    for raised_message, expected_message in message_expectations:
        _reset_global_state()
        sm_patch = None
        ar_patch = None
        try:
            env = _install_stub_environment()
            _install_ui_cookie_secret()
            db_session = _FakeDbSession()
            _install_db_session_factory(db_session=db_session)

            def _build_with_adapter_error(
                    db_session_arg: Any
                ) -> _FakeSecurityManager:
                instance = _FakeSecurityManager(db_session_arg)

                def _raise_adapter_error(request: Any) -> Any:
                    raise auth_adapter.AuthenticationError(
                        raised_message
                    )

                instance.authenticate = _raise_adapter_error
                return instance

            sm_patch = _patch_security_manager(
                side_effect=_build_with_adapter_error
            )
            ar_patch = _patch_auth_request_factory()

            request = _FakeRequest(
                form={"username": "admin", "password": "pw"},
            )
            response = config_routes.handle_login_submit(request)

            testbase.assert_equal(response.status_code, 401)
            ctx = env.last_template.render_calls[0]
            testbase.assert_equal(len(ctx["flashes"]), 1)
            testbase.assert_equal(ctx["flashes"][0][0], "error")
            testbase.assert_equal(
                ctx["flashes"][0][1], expected_message
            )
        finally:
            if ar_patch is not None:
                ar_patch.deactivate()
            if sm_patch is not None:
                sm_patch.deactivate()
            _reset_global_state()
    return


def test_handle_login_submit_keeps_generic_message_for_bad_credentials():
    """
    **Feature: login failure messaging (audit fix)**
    **Property: An adapter AuthenticationError carrying the
    bad-credentials message still flattens to the generic
    "Invalid username or password." flash so unknown usernames
    stay indistinguishable from wrong passwords.**
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (
        auth_adapter,
    )

    _reset_global_state()
    sm_patch = None
    ar_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        _install_db_session_factory(db_session=db_session)

        def _build_with_adapter_error(
                db_session_arg: Any
            ) -> _FakeSecurityManager:
            instance = _FakeSecurityManager(db_session_arg)

            def _raise_adapter_error(request: Any) -> Any:
                raise auth_adapter.AuthenticationError(
                    "Invalid credentials"
                )

            instance.authenticate = _raise_adapter_error
            return instance

        sm_patch = _patch_security_manager(
            side_effect=_build_with_adapter_error
        )
        ar_patch = _patch_auth_request_factory()

        request = _FakeRequest(
            form={"username": "admin", "password": "wrong"},
        )
        response = config_routes.handle_login_submit(request)

        testbase.assert_equal(response.status_code, 401)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        testbase.assert_equal(
            ctx["flashes"][0][1], "Invalid username or password."
        )
    finally:
        if ar_patch is not None:
            ar_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_login_submit_returns_401_when_authenticate_raises():
    """
    **Feature: webworks config blueprint port T1.3 (D1)**
    **Property: When SecurityManager.authenticate raises (bad
    credentials), the handler re-renders the login form with a
    401 status and an error-category flash. The DB session is
    still closed.**
    """
    _reset_global_state()
    sm_patch = None
    ar_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        _install_db_session_factory(db_session=db_session)

        def _build_with_failure(db_session_arg: Any) -> _FakeSecurityManager:
            instance = _FakeSecurityManager(db_session_arg)
            instance.authenticate_raises = True
            return instance

        sm_patch = _patch_security_manager(side_effect=_build_with_failure)
        ar_patch = _patch_auth_request_factory()

        request = _FakeRequest(
            form={"username": "admin", "password": "wrong-pw"},
        )
        response = config_routes.handle_login_submit(request)

        testbase.assert_equal(response.status_code, 401)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        testbase.assert_equal(ctx["flashes"][0][0], "error")
        # DB session closed via the finally block.
        testbase.assert_equal(db_session.close_count, 1)
    finally:
        if ar_patch is not None:
            ar_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# handle_logout (POST /logout)
# ===========================================================================


def test_handle_logout_calls_security_manager_logout_and_redirects_to_login():
    """
    **Feature: webworks config blueprint port T1.4 (D1)**
    **Property: A POST with a session token in the cookie and a
    matching CSRF token in the form calls
    SecurityManager.logout(token) and returns a 303 redirect to
    /login. A "logged out" flash rides on the redirect.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        _install_db_session_factory(db_session=db_session)
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        sm_patch = _patch_security_manager()

        cookie_value = cookie_session.sign_session_payload(
            payload={
                "user_id": "u-1",
                "username": "admin",
                "session_token": "tok-abc",
                csrf.SESSION_KEY: "csrf-tok-1",
            },
            secret=_TEST_UI_COOKIE_SECRET,
        )
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            form={"csrf_token": "csrf-tok-1"},
            method="POST",
        )
        response = config_routes.handle_logout(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(response.status_code, 303)
        testbase.assert_equal(
            response.headers["Location"], "/login"
        )

        instance = _FakeSecurityManager.last_instance
        testbase.assert_equal(instance.logout_calls, ["tok-abc"])
        testbase.assert_equal(db_session.close_count, 1)
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_logout_redirects_without_security_manager_call_when_no_token():
    """
    **Feature: webworks config blueprint port T1.4 (D1)**
    **Property: When the cookie carries no session_token, logout
    does NOT touch the database and just returns the redirect.
    Defensive against double-logout.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        # Note: no DATABASE_SESSION_FACTORY configured. If the
        # handler tried to open a DB session it would raise
        # RuntimeError -- the fact that this test passes proves
        # it short-circuited.
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        sm_patch = _patch_security_manager()

        request = _FakeRequest(cookies={})
        response = config_routes.handle_logout(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(response.status_code, 303)
        # No SecurityManager was constructed.
        testbase.assert_equal(_FakeSecurityManager.last_instance, None)
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_logout_post_without_csrf_token_is_rejected():
    """
    **Feature: logout CSRF protection (audit fix)**
    **Property: A POST /logout without a valid CSRF token does
    NOT log the session out -- SecurityManager.logout is never
    called and the handler redirects away (302) with the session
    cookie's auth keys intact.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        _install_db_session_factory(db_session=db_session)
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        sm_patch = _patch_security_manager()

        cookie_value = cookie_session.sign_session_payload(
            payload={
                "user_id": "u-1",
                "username": "admin",
                "session_token": "tok-abc",
                csrf.SESSION_KEY: "csrf-tok-1",
            },
            secret=_TEST_UI_COOKIE_SECRET,
        )
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            form={},
            method="POST",
        )
        response = config_routes.handle_logout(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(response.status_code, 302)
        # No logout happened.
        testbase.assert_equal(_FakeSecurityManager.last_instance, None)
        # The re-written cookie still carries the auth keys.
        morsel = response._cookies[cookie_session.COOKIE_NAME]
        payload = cookie_session.verify_session_payload(
            cookie_value=morsel.value,
            secret=_TEST_UI_COOKIE_SECRET,
        )
        testbase.assert_equal(payload is not None, True)
        testbase.assert_equal(payload.get("user_id", ""), "u-1")
        testbase.assert_equal(
            payload.get("session_token", ""), "tok-abc"
        )
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_logout_get_stays_available_without_csrf():
    """
    **Feature: logout CSRF protection (audit fix)**
    **Property: GET /logout -- the convenience entrypoint sidebar
    links bind to -- still logs out without a CSRF token. Only
    the POST path is CSRF-gated.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        _install_db_session_factory(db_session=db_session)
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        sm_patch = _patch_security_manager()

        cookie_value = cookie_session.sign_session_payload(
            payload={
                "user_id": "u-1",
                "username": "admin",
                "session_token": "tok-abc",
                csrf.SESSION_KEY: "csrf-tok-1",
            },
            secret=_TEST_UI_COOKIE_SECRET,
        )
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            method="GET",
        )
        response = config_routes.handle_logout(request)

        testbase.assert_equal(response.status_code, 303)
        testbase.assert_equal(
            response.headers["Location"], "/login"
        )
        instance = _FakeSecurityManager.last_instance
        testbase.assert_equal(instance.logout_calls, ["tok-abc"])
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# handle_dashboard (GET /config and /admin/dashboard)
# ===========================================================================


def test_handle_dashboard_redirects_anonymous_to_login_with_flash():
    """
    **Feature: webworks config blueprint port T1.5 (D1)**
    **Property: An anonymous request to the dashboard returns a
    302 redirect to /login, with a warning-category flash
    queued on the session cookie.**
    """
    _reset_global_state()
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        request = _FakeRequest(cookies={})
        response = config_routes.handle_dashboard(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(response.status_code, 302)
        testbase.assert_equal(
            response.headers["Location"], "/login"
        )
    finally:
        _reset_global_state()
    return


def test_handle_dashboard_redirects_when_token_no_longer_valid():
    """
    **Feature: webworks config blueprint port T1.5 (D1)**
    **Property: A cookie with a session_token whose
    SecurityManager.validate_token returns None (expired /
    revoked) is treated as expired -- the cookie is reset and
    the user is redirected to /login.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        _install_db_session_factory(db_session=db_session)
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        def _build_returning_none(db_session_arg: Any) -> _FakeSecurityManager:
            instance = _FakeSecurityManager(db_session_arg)
            instance.validate_token_response = None
            return instance

        sm_patch = _patch_security_manager(side_effect=_build_returning_none)

        cookie_value = cookie_session.sign_session_payload(
            payload={
                "user_id": "u-1",
                "username": "admin",
                "session_token": "tok-abc",
            },
            secret=_TEST_UI_COOKIE_SECRET,
        )
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
        )
        response = config_routes.handle_dashboard(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(response.status_code, 303)
        testbase.assert_equal(
            response.headers["Location"], "/login"
        )
        instance = _FakeSecurityManager.last_instance
        testbase.assert_equal(instance.validate_token_calls, ["tok-abc"])
        testbase.assert_equal(db_session.close_count, 1)
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_dashboard_renders_dashboard_template_when_token_valid():
    """
    **Feature: webworks config blueprint port T1.5 (D1)**
    **Property: A cookie with a still-valid session_token yields
    a 200 HTMLResponse from config/dashboard.html. The render
    context carries username + user_id + csrf_token + flashes.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        app = _FakeApp()
        config_routes.register_config_routes(app=app)

        def _build_with_valid_token(db_session_arg: Any) -> _FakeSecurityManager:
            instance = _FakeSecurityManager(db_session_arg)
            instance.validate_token_response = _FakeSessionInfo(
                user_id="u-1",
                username="admin",
                csrf_token="csrf-fresh",
            )
            return instance

        sm_patch = _patch_security_manager(side_effect=_build_with_valid_token)

        cookie_value = cookie_session.sign_session_payload(
            payload={
                "user_id": "u-1",
                "username": "admin",
                "session_token": "tok-abc",
            },
            secret=_TEST_UI_COOKIE_SECRET,
        )
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
        )
        response = config_routes.handle_dashboard(request)

        is_html = isinstance(response, HTMLResponse)
        testbase.assert_equal(is_html, True)
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/dashboard.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["username"], "admin")
        testbase.assert_equal(ctx["user_id"], "u-1")
        testbase.assert_equal(ctx["csrf_token"], "csrf-fresh")
        testbase.assert_equal(ctx["request_endpoint"], "config.dashboard")
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Misconfig: no UI cookie secret / no DB factory
# ===========================================================================


def test_handle_login_form_raises_runtime_error_when_ui_cookie_secret_missing():
    """
    **Feature: webworks config blueprint port T1.6 (D1)**
    **Property: With no UI cookie secret published on
    SITE_SHARED_GLOBALS, the handler raises RuntimeError to
    surface the misconfig at first request rather than silently
    serving an unsigned cookie.**
    """
    _reset_global_state()
    raised = False
    try:
        _install_stub_environment()
        request = _FakeRequest(cookies={})
        try:
            config_routes.handle_login_form(request)
        except RuntimeError:
            raised = True
    finally:
        _reset_global_state()
    testbase.assert_equal(raised, True)
    return


# ===========================================================================
# runtime_bootstrap: _load_ui_cookie_secret_or_none
# ===========================================================================


def _make_bootstrap_config(
        *,
        ui_cookie_secret_source: Optional[str] = None,
        ui_cookie_secret_file_path: Optional[str] = None,
        ui_cookie_secret_env_var: Optional[str] = None,
    ) -> runtime_bootstrap.RuntimeBootstrapConfig:
    rtnval = runtime_bootstrap.RuntimeBootstrapConfig(
        database_url="sqlite:///:memory:",
        runtime_environment="testing",
        kek_source="env",
        kek_id="test-kek",
        kek_file_path=None,
        kek_env_var=None,
        password_pepper_source=None,
        password_pepper_file_path=None,
        password_pepper_env_var=None,
        ui_cookie_secret_source=ui_cookie_secret_source,
        ui_cookie_secret_file_path=ui_cookie_secret_file_path,
        ui_cookie_secret_env_var=ui_cookie_secret_env_var,
        auto_create_schema=False,
        sql_echo=False,
    )
    return rtnval


def test_load_ui_cookie_secret_returns_none_when_source_unset():
    """
    **Feature: D1 runtime bootstrap T1.7**
    **Property: When the UI cookie secret source is unset (the
    REST-only deployment shape), the loader returns None and the
    bootstrap continues. The web UI handlers will refuse to serve
    until the secret is configured.**
    """
    config = _make_bootstrap_config(ui_cookie_secret_source=None)
    result = runtime_bootstrap._load_ui_cookie_secret_or_none(
        config=config
    )
    testbase.assert_equal(result, None)
    return


def test_load_ui_cookie_secret_reads_from_file_when_source_is_file():
    """
    **Feature: D1 runtime bootstrap T1.7**
    **Property: With source=file, the loader reads the file
    contents (>= 32 bytes) and returns them as bytes.**
    """
    handle, path = tempfile.mkstemp(prefix="ui-cookie-secret-")
    try:
        material = b"\x42" * 48
        with os.fdopen(handle, "wb") as fh:
            fh.write(material)
        config = _make_bootstrap_config(
            ui_cookie_secret_source="file",
            ui_cookie_secret_file_path=path,
        )
        result = runtime_bootstrap._load_ui_cookie_secret_or_none(
            config=config
        )
        testbase.assert_equal(result, material)
    finally:
        if os.path.exists(path) is True:
            os.unlink(path)
    return


def test_load_ui_cookie_secret_refuses_short_file_material():
    """
    **Feature: D1 runtime bootstrap T1.7**
    **Property: A file < 32 bytes raises ConfigurationError --
    the cookie signing minimum is enforced at boot rather than
    at first request.**
    """
    handle, path = tempfile.mkstemp(prefix="ui-cookie-secret-short-")
    raised = False
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(b"short")
        config = _make_bootstrap_config(
            ui_cookie_secret_source="file",
            ui_cookie_secret_file_path=path,
        )
        try:
            runtime_bootstrap._load_ui_cookie_secret_or_none(config=config)
        except ConfigurationError:
            raised = True
    finally:
        if os.path.exists(path) is True:
            os.unlink(path)
    testbase.assert_equal(raised, True)
    return


def test_load_ui_cookie_secret_reads_from_env_when_source_is_env():
    """
    **Feature: D1 runtime bootstrap T1.7**
    **Property: With source=env, the loader reads the named env
    var, encodes utf-8 to bytes, and returns the result. The env
    var name itself is taken from the config -- the material is
    the value of the named env var.**
    """
    env_var_name = "PYCHESTRATE_TEST_UI_COOKIE_SECRET_MATERIAL_M1"
    material_str = "x" * 48
    os.environ[env_var_name] = material_str
    try:
        config = _make_bootstrap_config(
            ui_cookie_secret_source="env",
            ui_cookie_secret_env_var=env_var_name,
        )
        result = runtime_bootstrap._load_ui_cookie_secret_or_none(
            config=config
        )
        testbase.assert_equal(result, material_str.encode("utf-8"))
    finally:
        del os.environ[env_var_name]
    return


def test_load_ui_cookie_secret_unsupported_source_raises():
    """
    **Feature: D1 runtime bootstrap T1.7**
    **Property: An unrecognized source value raises
    ConfigurationError with the supported-list mentioned --
    operators get a clear "fix this" message.**
    """
    config = _make_bootstrap_config(ui_cookie_secret_source="azure-kv")
    raised = False
    try:
        runtime_bootstrap._load_ui_cookie_secret_or_none(config=config)
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ===========================================================================
# url_for shim
# ===========================================================================


def test_url_for_substitutes_path_parameters_on_registered_endpoint():
    """
    **Feature: D1 url_for shim T1.8**
    **Property: A registered ``{user_id}``-bearing pattern is
    substituted with the kwarg value, returning the final URL.**
    """
    _reset_global_state()
    try:
        url_for_module.register_endpoint(
            endpoint="config.user_detail",
            pattern="/admin/users/{user_id}",
        )
        rtnval = url_for_module.url_for(
            "config.user_detail", user_id="u-42"
        )
        testbase.assert_equal(rtnval, "/admin/users/u-42")
    finally:
        _reset_global_state()
    return


def test_url_for_raises_keyerror_when_endpoint_unknown():
    """
    **Feature: D1 url_for shim T1.8**
    **Property: A typo in a template's url_for endpoint name
    surfaces as KeyError -- loud-fail rather than a half-built
    URL.**
    """
    _reset_global_state()
    raised = False
    try:
        try:
            url_for_module.url_for("config.no_such")
        except KeyError:
            raised = True
    finally:
        _reset_global_state()
    testbase.assert_equal(raised, True)
    return


def test_url_for_raises_keyerror_when_path_param_kwarg_missing():
    """
    **Feature: D1 url_for shim T1.8**
    **Property: When the registered pattern requires a path
    parameter that the caller didn't pass, the url_for shim
    raises KeyError. Loud-fail prevents a half-substituted URL
    sneaking into a template.**
    """
    _reset_global_state()
    raised = False
    try:
        url_for_module.register_endpoint(
            endpoint="config.user_detail",
            pattern="/admin/users/{user_id}",
        )
        try:
            url_for_module.url_for("config.user_detail")
        except KeyError:
            raised = True
    finally:
        _reset_global_state()
    testbase.assert_equal(raised, True)
    return


def test_url_for_drops_converter_qualifier_in_placeholder():
    """
    **Feature: D1 url_for shim T1.8**
    **Property: A pattern with ``{name:converter}`` substitutes
    using just the name -- the converter qualifier is dropped
    on render.**
    """
    _reset_global_state()
    try:
        url_for_module.register_endpoint(
            endpoint="config.role_detail",
            pattern="/admin/roles/{role_id:int}",
        )
        rtnval = url_for_module.url_for(
            "config.role_detail", role_id=99
        )
        testbase.assert_equal(rtnval, "/admin/roles/99")
    finally:
        _reset_global_state()
    return


def test_url_for_pure_path_substitution_has_no_query_string():
    """
    **Feature: D1 url_for shim T1.8**
    **Property: When every kwarg matches a path placeholder, the
    returned URL is the substituted path only -- no stray ``?``
    is appended.**
    """
    _reset_global_state()
    try:
        url_for_module.register_endpoint(
            endpoint="config.user_detail",
            pattern="/admin/users/{user_id}",
        )
        rtnval = url_for_module.url_for(
            "config.user_detail", user_id="u-42"
        )
        testbase.assert_equal(rtnval, "/admin/users/u-42")
    finally:
        _reset_global_state()
    return


def test_url_for_appends_extra_kwargs_as_query_string():
    """
    **Feature: D1 url_for shim T1.8**
    **Property: Kwargs that match no path placeholder are
    appended as a query string in insertion order -- pagination
    and filter links keep their parameters instead of collapsing
    to the bare URL.**
    """
    _reset_global_state()
    try:
        url_for_module.register_endpoint(
            endpoint="config.users_list",
            pattern="/admin/users",
        )
        rtnval = url_for_module.url_for(
            "config.users_list", page=2, search="alice"
        )
        testbase.assert_equal(rtnval, "/admin/users?page=2&search=alice")
    finally:
        _reset_global_state()
    return


def test_url_for_skips_none_valued_kwargs_in_query_string():
    """
    **Feature: D1 url_for shim T1.8**
    **Property: A kwarg whose value is ``None`` is omitted from
    the query string entirely -- optional filters a template
    passes unconditionally never render as ``param=None``.**
    """
    _reset_global_state()
    try:
        url_for_module.register_endpoint(
            endpoint="config.audit_list",
            pattern="/admin/audit",
        )
        rtnval = url_for_module.url_for(
            "config.audit_list", page=3, event_type=None, user_id=None
        )
        testbase.assert_equal(rtnval, "/admin/audit?page=3")
    finally:
        _reset_global_state()
    return


def test_url_for_returns_bare_url_when_all_extra_kwargs_are_none():
    """
    **Feature: D1 url_for shim T1.8**
    **Property: When every non-placeholder kwarg is ``None``,
    no ``?`` is appended -- the bare URL comes back exactly as
    registered.**
    """
    _reset_global_state()
    try:
        url_for_module.register_endpoint(
            endpoint="config.audit_list",
            pattern="/admin/audit",
        )
        rtnval = url_for_module.url_for(
            "config.audit_list", event_type=None, user_id=None
        )
        testbase.assert_equal(rtnval, "/admin/audit")
    finally:
        _reset_global_state()
    return


def test_url_for_url_encodes_query_string_values():
    """
    **Feature: D1 url_for shim T1.8**
    **Property: Query-string values with spaces and reserved
    characters are URL-encoded -- a search term like
    ``a b&c=d`` round-trips as a single parameter value.**
    """
    _reset_global_state()
    try:
        url_for_module.register_endpoint(
            endpoint="config.users_list",
            pattern="/admin/users",
        )
        rtnval = url_for_module.url_for(
            "config.users_list", search="a b&c=d"
        )
        testbase.assert_equal(
            rtnval, "/admin/users?search=a+b%26c%3Dd"
        )
    finally:
        _reset_global_state()
    return


def test_url_for_mixes_path_placeholders_and_query_string_kwargs():
    """
    **Feature: D1 url_for shim T1.8**
    **Property: A call mixing placeholder kwargs and extra
    kwargs substitutes the path params and appends only the
    extras as the query string.**
    """
    _reset_global_state()
    try:
        url_for_module.register_endpoint(
            endpoint="projects.tests_list",
            pattern="/projects/{project_id}/tests",
        )
        rtnval = url_for_module.url_for(
            "projects.tests_list",
            project_id="p-7",
            status="failed",
            page=4,
        )
        testbase.assert_equal(
            rtnval, "/projects/p-7/tests?status=failed&page=4"
        )
    finally:
        _reset_global_state()
    return
