"""
.. module:: test_p19o_enrollment_admin_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the p19o enrollment-token admin page
               (list / mint / revoke under /admin).

.. moduleauthor:: Automation Mojo LLC

PR p19o adds an operator-facing admin page so a logged-in admin
can mint / list / revoke client enrollment tokens from the UI
instead of only via the REST surface.

Tests cover:

* ``register_enrollment_admin_routes`` -- the three documented
  routes are attached under ``/admin``.
* ``handle_enrollment_token_list`` -- happy path renders the
  list template with the token rows; permission-denied path
  redirects to the dashboard.
* ``handle_enrollment_token_mint`` -- happy path mints a token
  and redirects to the list with the secret surfaced in a flash;
  missing-field path flashes an error.
* ``handle_enrollment_token_revoke`` -- happy path revokes and
  redirects to the list.
* ``_coerce_ttl_seconds`` -- blank / non-numeric / non-positive
  inputs fall back to the default TTL.

All enrollment-service + SecurityManager interactions are patched
at the routes-module bindings so the suite never imports the
source service module.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from automojo import testbase
from automojo.testbase.mocking import create_module_patch
from automojo.webworks.routing.response import RedirectResponse

from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from automojo.pychestrate.webservice.webinterface.blueprints.config import (
    routes as config_routes,
)
from automojo.pychestrate.webservice.webinterface.blueprints.config import (
    routes_enrollment,
)
from automojo.pychestrate.webservice.webinterface.foundation import (
    cookie_session,
    csrf,
    templating,
    url_for as url_for_module,
)


_TEST_UI_COOKIE_SECRET: bytes = b"\x00" * 32


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeQueryParams:
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
            path_params: Optional[Dict[str, Any]] = None
        ) -> None:
        self.method: str = method
        self.cookies: Dict[str, str] = cookies if cookies is not None else {}
        self.body: bytes = body
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams()
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
        resolved_methods = tuple(
            methods if methods is not None else ["GET"]
        )

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
    last_instance: Optional["_FakeSecurityManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.validate_token_response: Optional[_FakeSessionInfo] = None
        self.check_permission_response: bool = True
        _FakeSecurityManager.last_instance = self
        return

    def validate_token(self, token: str) -> Optional[_FakeSessionInfo]:
        return self.validate_token_response

    def check_permission(self, user_id: str, permission: str) -> bool:
        return self.check_permission_response


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


class _FakeTokenStatus:
    def __init__(self, *, value: str) -> None:
        self.value: str = value
        return


class _FakeTokenView:
    def __init__(
            self, *, token_id: str, project_id: str, pod_name: str,
            status_value: str
        ) -> None:
        self.token_id: str = token_id
        self.project_id: str = project_id
        self.pod_name: str = pod_name
        self.status: _FakeTokenStatus = _FakeTokenStatus(
            value=status_value
        )
        self.issued_at_iso: str = "2026-05-20T00:00:00+00:00"
        self.expires_at_iso: str = "2026-05-21T00:00:00+00:00"
        self.one_shot: bool = True
        self.algorithm_name: str = "sha256"
        self.redeemed_at_iso: Optional[str] = None
        self.redeemed_by_client_id: Optional[str] = None
        return


class _FakeIssuedToken:
    def __init__(self, *, token_id: str, secret: str) -> None:
        self.token_id: str = token_id
        self.secret: str = secret
        self.project_id: str = "proj-1"
        self.pod_name: str = "pod-1"
        self.expires_at_iso: str = "2026-05-21T00:00:00+00:00"
        self.algorithm_name: str = "sha256"
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
    return


def _patch_security_manager(
        *, check_permission_response: bool = True
    ) -> Any:
    info = _FakeSessionInfo(
        user_id="u-admin", username="admin", csrf_token="csrf-fresh"
    )

    def _builder(*, db_session: Any) -> _FakeSecurityManager:
        instance = _FakeSecurityManager(db_session)
        instance.validate_token_response = info
        instance.check_permission_response = check_permission_response
        return instance

    patch = create_module_patch(config_routes, "_build_security_manager")
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_service_list(*, tokens: List[Any]) -> Any:
    def _list(*, db_session: Any) -> List[Any]:
        return tokens

    patch = create_module_patch(routes_enrollment, "_service_list_tokens")
    mock = patch.activate()
    mock.configure(side_effect=_list)
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
    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (  # noqa: E402
        register_config_routes,
    )
    app = _FakeApp()
    register_config_routes(app=app)
    return


def _csrf_body(*, fields: Dict[str, str]) -> bytes:
    from urllib.parse import urlencode
    payload = dict(fields)
    payload[csrf.FORM_FIELD_NAME] = "csrf-fresh"
    rtnval = urlencode(payload).encode("utf-8")
    return rtnval


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_enrollment_admin_routes_attaches_routes():
    """
    **Feature: enrollment-admin (p19o)**
    **Property: register_enrollment_admin_routes attaches the
    three documented routes -- list / mint / revoke -- under the
    /admin prefix.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        routes_enrollment.register_enrollment_admin_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/admin/enrollment-tokens", ("GET",)),
            ("/admin/enrollment-tokens/mint", ("POST",)),
            (
                "/admin/enrollment-tokens/{token_id}/revoke",
                ("POST",),
            ),
        }
        missing = expected - actual
        testbase.assert_equal(missing, set())
    finally:
        _reset_global_state()
    return


# ===========================================================================
# _coerce_ttl_seconds
# ===========================================================================


def test_coerce_ttl_seconds_falls_back_on_bad_input():
    """
    **Feature: enrollment-admin (p19o)**
    **Property: _coerce_ttl_seconds returns the default TTL for
    blank / non-numeric / non-positive inputs and the parsed
    value for a positive integer.**
    """
    default = routes_enrollment._DEFAULT_TTL_SECONDS
    testbase.assert_equal(
        routes_enrollment._coerce_ttl_seconds(raw=None), default
    )
    testbase.assert_equal(
        routes_enrollment._coerce_ttl_seconds(raw=""), default
    )
    testbase.assert_equal(
        routes_enrollment._coerce_ttl_seconds(raw="abc"), default
    )
    testbase.assert_equal(
        routes_enrollment._coerce_ttl_seconds(raw="0"), default
    )
    testbase.assert_equal(
        routes_enrollment._coerce_ttl_seconds(raw="-5"), default
    )
    testbase.assert_equal(
        routes_enrollment._coerce_ttl_seconds(raw="3600"), 3600
    )
    return


# ===========================================================================
# handle_enrollment_token_list
# ===========================================================================


def test_handle_enrollment_token_list_renders_token_rows():
    """
    **Feature: enrollment-admin (p19o)**
    **Property: GET /admin/enrollment-tokens renders the
    enrollment list template with the token rows from the
    enrollment service.**
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
        tokens = [
            _FakeTokenView(
                token_id="tok-1", project_id="p1", pod_name="pod-a",
                status_value="PENDING",
            ),
            _FakeTokenView(
                token_id="tok-2", project_id="p1", pod_name="pod-b",
                status_value="REVOKED",
            ),
        ]
        list_patch = _patch_service_list(tokens=tokens)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = routes_enrollment.handle_enrollment_token_list(
            request
        )

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/enrollment/list.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["tokens"]), 2)
    finally:
        for p in (list_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_enrollment_token_list_redirects_when_lacks_permission():
    """
    **Feature: enrollment-admin (p19o)**
    **Property: A user without system:resources.manage is
    redirected to the admin dashboard rather than seeing the
    token list -- the route is the security boundary.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager(
            check_permission_response=False
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = routes_enrollment.handle_enrollment_token_list(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_enrollment_token_list_redirects_anonymous():
    """
    **Feature: enrollment-admin (p19o)**
    **Property: An anonymous GET (no session cookie) to the
    enrollment admin page redirects to the login page.**
    """
    _reset_global_state()
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()

        request = _FakeRequest()
        response = routes_enrollment.handle_enrollment_token_list(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        location = response.headers.get("Location", "")
        testbase.assert_true(location.startswith("/login"))
    finally:
        _reset_global_state()
    return


# ===========================================================================
# handle_enrollment_token_mint
# ===========================================================================


def test_handle_enrollment_token_mint_happy_path_redirects():
    """
    **Feature: enrollment-admin (p19o)**
    **Property: POST /admin/enrollment-tokens/mint with valid
    project_id + pod_name mints a token via the service and
    redirects to the list; the secret rides on a flash.**
    """
    _reset_global_state()
    sm_patch = None
    issue_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        issued_calls: List[Dict[str, Any]] = []

        def _issue(**kwargs: Any) -> _FakeIssuedToken:
            issued_calls.append(kwargs)
            return _FakeIssuedToken(
                token_id="tok-new", secret="s3cr3t-value"
            )

        issue_patch = create_module_patch(
            routes_enrollment, "_service_issue_token"
        )
        issue_mock = issue_patch.activate()
        issue_mock.configure(side_effect=_issue)

        cookie_value = _build_authenticated_cookie()
        body = _csrf_body(fields={
            "project_id": "proj-1",
            "pod_name": "pod-1",
            "ttl_seconds": "7200",
        })
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = routes_enrollment.handle_enrollment_token_mint(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(len(issued_calls), 1)
        testbase.assert_equal(issued_calls[0]["project_id"], "proj-1")
        testbase.assert_equal(issued_calls[0]["pod_name"], "pod-1")
        testbase.assert_equal(issued_calls[0]["ttl_seconds"], 7200)
    finally:
        for p in (issue_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_enrollment_token_mint_missing_fields_flashes_error():
    """
    **Feature: enrollment-admin (p19o)**
    **Property: A mint POST missing project_id / pod_name does
    not call the service and redirects back to the list with an
    error flash.**
    """
    _reset_global_state()
    sm_patch = None
    issue_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        issued_calls: List[Dict[str, Any]] = []

        def _issue(**kwargs: Any) -> _FakeIssuedToken:
            issued_calls.append(kwargs)
            return _FakeIssuedToken(token_id="x", secret="x")

        issue_patch = create_module_patch(
            routes_enrollment, "_service_issue_token"
        )
        issue_mock = issue_patch.activate()
        issue_mock.configure(side_effect=_issue)

        cookie_value = _build_authenticated_cookie()
        body = _csrf_body(fields={"project_id": "", "pod_name": ""})
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = routes_enrollment.handle_enrollment_token_mint(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(len(issued_calls), 0)
    finally:
        for p in (issue_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# handle_enrollment_token_revoke
# ===========================================================================


def test_handle_enrollment_token_revoke_happy_path_redirects():
    """
    **Feature: enrollment-admin (p19o)**
    **Property: POST /admin/enrollment-tokens/{token_id}/revoke
    revokes the token via the service and redirects to the
    list.**
    """
    _reset_global_state()
    sm_patch = None
    revoke_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        revoke_calls: List[Dict[str, Any]] = []

        def _revoke(**kwargs: Any) -> None:
            revoke_calls.append(kwargs)
            return

        revoke_patch = create_module_patch(
            routes_enrollment, "_service_revoke_token"
        )
        revoke_mock = revoke_patch.activate()
        revoke_mock.configure(side_effect=_revoke)

        cookie_value = _build_authenticated_cookie()
        body = _csrf_body(fields={})
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"token_id": "tok-99"},
        )
        response = routes_enrollment.handle_enrollment_token_revoke(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(len(revoke_calls), 1)
        testbase.assert_equal(revoke_calls[0]["token_id"], "tok-99")
    finally:
        for p in (revoke_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return
