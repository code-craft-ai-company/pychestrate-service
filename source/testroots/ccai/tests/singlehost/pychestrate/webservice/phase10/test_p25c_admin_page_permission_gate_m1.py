"""
.. module:: test_p25c_admin_page_permission_gate_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the server-side permission gate on the
               ``/admin/*`` pages.

.. moduleauthor:: Code Craft AI LLC

Audit finding XC-01: the site shell hid admin navigation from users
without ``system:ui.admin.view``, but most ``/admin/*`` handlers only
checked that a session existed -- any signed-in user could load the
pages and POST to them, including creating a ``system-admin``
account. Each admin route table now declares the permission its
routes need, and :func:`config.routes._require_admin_permission_for`
checks it before the handler runs.

Coverage:

* Every ``/admin/*`` route registered by ``register_config_routes``
  answers 403 to a signed-in user who holds no permission -- including
  the UI profile, RPA job type and enrollment token pages, which used
  to gate inside their handlers and redirect to the dashboard (audit
  ADM-21).
* The gate itself -- runs the handler for a holder of the declared
  permission, refuses a user holding only other permissions, sends
  anonymous requests to sign in, and treats a failing permission
  check as a denial.
* Every declared key exists in the RBAC catalog.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_module_patch
from ccai.webworks.routing.response import HTMLResponse

from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from ccai.pychestrate.webservice.security.rbac import catalog
from ccai.pychestrate.webservice.webinterface.blueprints.config import (
    routes as config_routes,
    routes_audit,
    routes_enrollment,
    routes_roles,
    routes_rpa_types,
    routes_scopes,
    routes_secrets,
    routes_sessions,
    routes_ui_profile,
    routes_users,
    routes_variables,
)
from ccai.pychestrate.webservice.webinterface.foundation import (
    cookie_session,
    templating,
    url_for as url_for_module,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)
from ccai.tests.singlehost.pychestrate.webservice.shared.webworks_test_harness import (
    make_fake_app,
    make_fake_request,
    make_fake_security_manager,
)


_TEST_UI_COOKIE_SECRET: bytes = b"\x00" * 32

_SAMPLE_PATH_PARAMS: Dict[str, str] = {
    "user_id": "u-7",
    "role_id": "r-1",
    "name": "var-a",
    "scope_id": "1",
    "session_id": "s-1",
    "type_id": "job-type",
    "version": "1.0.0",
    "token_id": "t-1",
}


# ---------------------------------------------------------------------------
# Stubs + setup
# ---------------------------------------------------------------------------


class _StubTemplate:
    def __init__(self, *, name: str) -> None:
        self.name: str = name
        return

    def render(self, ctx: Dict[str, Any]) -> str:
        return "RENDERED:{}".format(self.name)


class _StubJinjaEnvironment:
    def __init__(self) -> None:
        self.globals: Dict[str, Any] = {}
        return

    def get_template(self, name: str) -> _StubTemplate:
        return _StubTemplate(name=name)


class _FakeDbSession:
    def close(self) -> None:
        return


class _RecordingHandler:
    def __init__(self) -> None:
        self.calls: List[Any] = []
        return

    def __call__(self, request: Any) -> HTMLResponse:
        self.calls.append(request)
        return HTMLResponse(content="handler-ran", status_code=200)


def _install_environment() -> None:
    url_for_module.reset_registry_for_testing()
    templating.reset_default_environment_for_testing()
    templating.set_default_environment(environment=_StubJinjaEnvironment())
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = _TEST_UI_COOKIE_SECRET
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = lambda: _FakeDbSession()
    return


def _reset_environment() -> None:
    url_for_module.reset_registry_for_testing()
    templating.reset_default_environment_for_testing()
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = None
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = None
    return


def _patch_security_manager(
        *, permission_predicate: Callable[[str, str], bool]
    ) -> Any:
    """
        Make every security manager the config routes build accept
        the test session and answer permission checks with
        ``permission_predicate``.
    """

    def _builder(*, db_session: Any) -> Any:
        rtnval = make_fake_security_manager(
            db_session=db_session,
            user_id="u-member",
            csrf_token="csrf-fresh",
            permission_predicate=permission_predicate,
        )
        return rtnval

    patch = create_module_patch(config_routes, "_build_security_manager")
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _signed_in_cookies() -> Dict[str, str]:
    cookie_value = cookie_session.sign_session_payload(
        payload={
            "user_id": "u-member",
            "username": "member",
            "session_token": "tok-member",
        },
        secret=_TEST_UI_COOKIE_SECRET,
    )
    rtnval = {cookie_session.COOKIE_NAME: cookie_value}
    return rtnval


def _admin_route_responses(
        *, permission_predicate: Callable[[str, str], bool]
    ) -> List[Tuple[str, str, Any]]:
    """
        Register every config route, then call each ``/admin/*``
        route once per method as a signed-in user whose permissions
        ``permission_predicate`` decides. Returns
        ``(method, path, status)`` triples; a handler that raises
        (it ran against the stub database) reports
        ``"raised <ExceptionType>"`` as its status.
    """
    rtnval: List[Tuple[str, str, Any]] = []
    _install_environment()
    patch = _patch_security_manager(permission_predicate=permission_predicate)
    try:
        app = make_fake_app()
        config_routes.register_config_routes(app=app)
        for path, methods, handler in app.calls:
            if path.startswith("/admin") is False:
                continue
            for method in methods:
                request = make_fake_request(
                    method=method,
                    path=path,
                    cookies=_signed_in_cookies(),
                    path_params=_SAMPLE_PATH_PARAMS,
                )
                try:
                    status: Any = handler(request).status_code
                except Exception as error:
                    status = "raised {}".format(type(error).__name__)
                rtnval.append((method, path, status))
    finally:
        patch.deactivate()
        _reset_environment()
    return rtnval


def _deny_everything(user_id: str, permission: str) -> bool:
    return False


# ===========================================================================
# Every admin route
# ===========================================================================


def test_every_gated_admin_route_answers_403_to_a_user_without_permissions():
    """
    **Feature: admin page permission gate (XC-01)**
    **Property: every /admin/* route (GET and POST) answers 403 to a
    signed-in user who holds no permission, so no admin page renders
    and no admin form is processed for them.**
    """
    served: List[Tuple[str, str, Any]] = []
    for method, path, status in _admin_route_responses(
        permission_predicate=_deny_everything
    ):
        if status != 403:
            served.append((method, path, status))
    testbase.assert_equal(served, [])
    return


def test_formerly_redirecting_admin_pages_answer_403():
    """
    **Feature: admin page permission gate (ADM-21)**
    **Property: the UI profile, RPA job type and enrollment token pages
    answer a refused user with the 403 page instead of redirecting to
    the dashboard.**
    """
    prefixes = ("/admin/ui-profile", "/admin/rpa-job-types", "/admin/enrollment-tokens")
    statuses = sorted({
        status
        for _method, path, status in _admin_route_responses(permission_predicate=_deny_everything)
        if path.startswith(prefixes)
    }, key=str)
    testbase.assert_equal(statuses, [403])
    return


# ===========================================================================
# The gate
# ===========================================================================


def _call_gated(
        *,
        permission_predicate: Callable[[str, str], bool],
        cookies: Optional[Dict[str, str]],
        permission: str = "system:audit.read"
    ) -> Tuple[Any, _RecordingHandler]:
    """
        Wrap a recording handler with the admin gate and call it once
        with ``GET /admin/audit-logs``.
    """
    _install_environment()
    patch = _patch_security_manager(permission_predicate=permission_predicate)
    handler = _RecordingHandler()
    try:
        config_routes.register_config_routes(app=make_fake_app())
        gated = config_routes._require_admin_permission_for(
            handler, permission=permission
        )
        request = make_fake_request(
            method="GET", path="/admin/audit-logs", cookies=cookies,
        )
        response = gated(request)
    finally:
        patch.deactivate()
        _reset_environment()
    rtnval = (response, handler)
    return rtnval


def test_admin_gate_runs_the_handler_for_a_holder_of_the_permission():
    """
    **Feature: admin page permission gate (XC-01)**
    **Property: a signed-in user who holds exactly the declared
    permission gets the handler's own response.**
    """
    response, handler = _call_gated(
        permission_predicate=lambda uid, perm: perm == "system:audit.read",
        cookies=_signed_in_cookies(),
    )
    testbase.assert_equal((response.status_code, len(handler.calls)), (200, 1))
    return


def test_admin_gate_refuses_a_user_holding_only_other_permissions():
    """
    **Feature: admin page permission gate (XC-01)**
    **Property: holding other admin permissions is not enough -- a
    user with every permission except the declared one gets 403 and
    the handler never runs.**
    """
    response, handler = _call_gated(
        permission_predicate=lambda uid, perm: perm != "system:audit.read",
        cookies=_signed_in_cookies(),
    )
    testbase.assert_equal((response.status_code, len(handler.calls)), (403, 0))
    return


def test_admin_gate_sends_an_anonymous_request_to_sign_in():
    """
    **Feature: admin page permission gate (XC-01)**
    **Property: a request without a session is redirected to the
    login page (not answered 403), and the handler never runs.**
    """
    response, handler = _call_gated(
        permission_predicate=lambda uid, perm: True,
        cookies=None,
    )
    location = str(response.headers.get("Location", "")).split("?", 1)[0]
    testbase.assert_equal(
        (response.status_code in (302, 303), location, len(handler.calls)),
        (True, "/login", 0),
    )
    return


def test_admin_gate_treats_a_failing_permission_check_as_denial():
    """
    **Feature: admin page permission gate (XC-01)**
    **Property: when the permission check itself raises, the gate
    answers 403 (fail closed) and the handler never runs.**
    """

    def _raise(user_id: str, permission: str) -> bool:
        raise RuntimeError("rbac store unavailable")

    response, handler = _call_gated(
        permission_predicate=_raise,
        cookies=_signed_in_cookies(),
    )
    testbase.assert_equal((response.status_code, len(handler.calls)), (403, 0))
    return


# ===========================================================================
# Declared keys
# ===========================================================================


def test_every_admin_route_permission_exists_in_the_rbac_catalog():
    """
    **Feature: admin page permission gate (XC-01)**
    **Property: every permission an admin route table declares (and
    the role-assignment key) is registered in the RBAC catalog, so no
    page is locked behind a misspelled key that nobody can hold.**
    """
    reset_phase1_runtime()
    known = set(catalog.load_catalog_from_registry().permissions)

    declared: Dict[str, str] = {}
    declared.update(config_routes._ADMIN_ROUTE_PERMISSIONS)
    for module in (
        routes_users, routes_roles, routes_variables, routes_secrets,
        routes_scopes, routes_sessions, routes_audit, routes_enrollment,
        routes_ui_profile, routes_rpa_types,
    ):
        declared.update(module._ROUTE_PERMISSIONS)
    declared["users.role_assignment"] = routes_users.ROLE_ASSIGN_PERMISSION

    unknown = sorted(
        (endpoint, key) for endpoint, key in declared.items() if key not in known
    )
    testbase.assert_equal(unknown, [])
    return
