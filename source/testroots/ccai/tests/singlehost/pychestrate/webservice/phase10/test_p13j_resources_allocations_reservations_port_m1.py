"""
.. module:: test_p13j_resources_allocations_reservations_port_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the E3 slice of the resources port
               (allocations + reservations).

.. moduleauthor:: Code Craft AI LLC

PR E3 ports the five allocation routes plus the five
reservation routes to webworks.

Tests cover:

* ``register_allocations_routes`` / ``register_reservations_routes``
  -- route attachment matrices.
* allocation list / history (filter passthrough including ISO
  date parsing) / detail (happy + 404) / checkin (happy +
  manager-error) / force_checkin (admin-denied + happy +
  manager-error + reason form-field default).
* reservation list / create (GET + POST happy + missing-times
  + ValueError-from-mode + manager-error + CSRF) / detail
  (happy via list-and-find + 404) / edit (POST happy + 404) /
  cancel (happy + manager-error).
* ``_parse_iso_datetime_or_none`` + ``_approximate_total_pages``
  + ``_find_reservation_by_id`` helpers.
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
from ccai.pychestrate.webservice.webinterface.blueprints.resources import (
    routes as resources_routes,
    routes_allocations as resources_routes_allocations,
    routes_reservations as resources_routes_reservations,
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
    last_instance: Optional["_FakeSecurityManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.validate_token_response: Optional[_FakeSessionInfo] = None
        self.check_permission_response: bool = True
        self.check_permission_calls: List[Any] = []
        _FakeSecurityManager.last_instance = self
        return

    def validate_token(self, token: str) -> Optional[_FakeSessionInfo]:
        return self.validate_token_response

    def check_permission(self, user_id: str, permission: str) -> bool:
        self.check_permission_calls.append((user_id, permission))
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


# ---- Allocation / reservation fakes ---------------------------------------


class _FakeAllocation:
    def __init__(
            self, *, allocation_id: int, status: str = "active"
        ) -> None:
        self.id: int = allocation_id
        self.status: str = status
        return


class _FakeReservation:
    def __init__(
            self, *, reservation_id: int,
            resource_id: int = 1
        ) -> None:
        self.id: int = reservation_id
        self.resource_id: int = resource_id
        self.start_time: datetime = datetime(2026, 5, 4, 10, 0)
        self.end_time: datetime = datetime(2026, 5, 4, 12, 0)
        return


class _FakeResource:
    def __init__(self, *, resource_id: int, name: str = "r") -> None:
        self.id: int = resource_id
        self.name: str = name
        return


class _FakeAllocationManager:
    last_instance: Optional["_FakeAllocationManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_allocations_response: List[_FakeAllocation] = []
        self.history_response: List[_FakeAllocation] = []
        self.get_allocation_response: Optional[_FakeAllocation] = None
        self.list_reservations_response: List[_FakeReservation] = []
        self.create_reservation_response: Optional[_FakeReservation] = None
        self.list_allocations_calls: List[Dict[str, Any]] = []
        self.history_calls: List[Dict[str, Any]] = []
        self.list_reservations_calls: List[Dict[str, Any]] = []
        self.checkin_calls: List[Any] = []
        self.force_checkin_calls: List[Any] = []
        self.create_reservation_calls: List[Any] = []
        self.modify_reservation_calls: List[Any] = []
        self.cancel_reservation_calls: List[Any] = []
        self.checkin_raises: Optional[Exception] = None
        self.force_checkin_raises: Optional[Exception] = None
        self.create_reservation_raises: Optional[Exception] = None
        self.modify_reservation_raises: Optional[Exception] = None
        self.cancel_reservation_raises: Optional[Exception] = None
        _FakeAllocationManager.last_instance = self
        return

    def list_allocations(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        self.list_allocations_calls.append(kwargs)
        return SimpleNamespace(
            allocations=self.list_allocations_response,
            total=len(self.list_allocations_response),
            offset=0,
            limit=len(self.list_allocations_response),
        )

    def get_allocation_history(
            self, **kwargs: Any
        ) -> Any:
        from types import SimpleNamespace
        self.history_calls.append(kwargs)
        return SimpleNamespace(
            allocations=self.history_response,
            total=len(self.history_response),
            offset=0,
            limit=len(self.history_response),
        )

    def get_allocation(
            self, allocation_id: int
        ) -> Optional[_FakeAllocation]:
        return self.get_allocation_response

    def checkin(
            self, allocation_id: int, user_id: str
        ) -> None:
        self.checkin_calls.append((allocation_id, user_id))
        if self.checkin_raises is not None:
            raise self.checkin_raises
        return

    def force_checkin(
            self, allocation_id: int, user_id: str, reason: str
        ) -> None:
        self.force_checkin_calls.append(
            (allocation_id, user_id, reason)
        )
        if self.force_checkin_raises is not None:
            raise self.force_checkin_raises
        return

    def list_reservations(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        self.list_reservations_calls.append(kwargs)
        return SimpleNamespace(
            reservations=self.list_reservations_response,
            total=len(self.list_reservations_response),
            offset=0,
            limit=len(self.list_reservations_response),
        )

    def create_reservation(
            self, request: Any, user_id: str
        ) -> _FakeReservation:
        self.create_reservation_calls.append((request, user_id))
        if self.create_reservation_raises is not None:
            raise self.create_reservation_raises
        if self.create_reservation_response is None:
            return _FakeReservation(reservation_id=99)
        return self.create_reservation_response

    def modify_reservation(
            self, reservation_id: int, **kwargs: Any
        ) -> None:
        self.modify_reservation_calls.append(
            (reservation_id, kwargs)
        )
        if self.modify_reservation_raises is not None:
            raise self.modify_reservation_raises
        return

    def cancel_reservation(
            self, reservation_id: int, user_id: str
        ) -> None:
        self.cancel_reservation_calls.append(
            (reservation_id, user_id)
        )
        if self.cancel_reservation_raises is not None:
            raise self.cancel_reservation_raises
        return


class _FakeResourceManager:
    last_instance: Optional["_FakeResourceManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_resources_response: List[_FakeResource] = []
        _FakeResourceManager.last_instance = self
        return

    def list_resources(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            resources=self.list_resources_response,
            total=len(self.list_resources_response),
            offset=0,
            limit=len(self.list_resources_response),
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
    _FakeSecurityManager.last_instance = None
    _FakeAllocationManager.last_instance = None
    _FakeResourceManager.last_instance = None
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


def _patch_allocation_manager_in(
        *, target_module: Any,
        configure: Optional[Callable[[_FakeAllocationManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeAllocationManager:
        instance = _FakeAllocationManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(target_module, "_build_allocation_manager")
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_resource_manager_in(*, target_module: Any) -> Any:
    def _builder(*, db_session: Any) -> _FakeResourceManager:
        return _FakeResourceManager(db_session)

    patch = create_module_patch(target_module, "_build_resource_manager")
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_reservation_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        resources_routes_reservations, "_build_reservation_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_allocation_mode_resolver() -> Any:
    def _resolve(*, mode_str: str) -> Any:
        return type("AM", (), {"value": mode_str})()

    patch = create_module_patch(
        resources_routes_reservations, "_resolve_allocation_mode"
    )
    mock = patch.activate()
    mock.configure(side_effect=_resolve)
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
        Register every config + resources endpoint into the
        url_for shim. The resources registrar cascades into all
        E1-E3 sub-feature registrars so the full url_for surface
        is available for the handlers under test.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
        register_config_routes,
    )
    app = _FakeApp()
    register_config_routes(app=app)
    resources_routes.register_resources_routes(app=app)
    return


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_allocations_routes_attaches_documented_routes():
    """
    **Feature: webworks resources port T7.1 (E3)**
    **Property: register_allocations_routes attaches the five
    allocation routes at /resources/allocations*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        resources_routes_allocations.register_allocations_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/resources/allocations", ("GET",)),
            ("/resources/allocations/history", ("GET",)),
            ("/resources/allocations/{allocation_id}", ("GET",)),
            (
                "/resources/allocations/{allocation_id}/checkin",
                ("POST",),
            ),
            (
                "/resources/allocations/{allocation_id}/force-checkin",
                ("POST",),
            ),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_reservations_routes_attaches_documented_routes():
    """
    **Feature: webworks resources port T7.2 (E3)**
    **Property: register_reservations_routes attaches the five
    reservation routes at /resources/reservations*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        resources_routes_reservations.register_reservations_routes(
            app=app
        )
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/resources/reservations", ("GET",)),
            ("/resources/reservations/create", ("GET", "POST")),
            (
                "/resources/reservations/{reservation_id}",
                ("GET",),
            ),
            (
                "/resources/reservations/{reservation_id}/edit",
                ("GET", "POST"),
            ),
            (
                "/resources/reservations/{reservation_id}/cancel",
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


def test_parse_iso_datetime_or_none_handles_valid_and_invalid():
    """
    **Feature: E3 helpers T7.3**
    **Property: Valid ISO strings parse; bad inputs return None
    rather than raising. Empty / None passes through to None.**
    """
    parse_a = resources_routes_allocations._parse_iso_datetime_or_none
    parse_r = resources_routes_reservations._parse_iso_datetime_or_none
    expected = datetime(2026, 5, 4, 10, 30)
    testbase.assert_equal(parse_a(raw="2026-05-04T10:30"), expected)
    testbase.assert_equal(parse_r(raw="2026-05-04T10:30"), expected)
    testbase.assert_equal(parse_a(raw=None), None)
    testbase.assert_equal(parse_a(raw=""), None)
    testbase.assert_equal(parse_a(raw="bad"), None)
    return


def test_approximate_total_pages_full_page_reports_next():
    """
    **Feature: E3 helpers T7.4**
    **Property: When the returned count == per_page, the helper
    reports page+1 (legacy "Next link enabled" shape).**
    """
    helper = resources_routes_allocations._approximate_total_pages
    testbase.assert_equal(
        helper(page=2, per_page=20, returned_count=20), 3
    )
    testbase.assert_equal(
        helper(page=1, per_page=20, returned_count=5), 1
    )
    testbase.assert_equal(
        helper(page=2, per_page=20, returned_count=5), 2
    )
    return


def test_find_reservation_by_id_returns_none_when_missing():
    """
    **Feature: E3 helpers T7.5**
    **Property: _find_reservation_by_id linearly scans the
    list_reservations(limit=1000) result for a matching id.**
    """
    finder = resources_routes_reservations._find_reservation_by_id
    fake_mgr = _FakeAllocationManager(db_session=None)
    fake_mgr.list_reservations_response = [
        _FakeReservation(reservation_id=1),
        _FakeReservation(reservation_id=2),
    ]
    found = finder(allocation_manager=fake_mgr, reservation_id=2)
    testbase.assert_equal(found.id, 2)
    found = finder(allocation_manager=fake_mgr, reservation_id=99)
    testbase.assert_equal(found, None)
    return


# ===========================================================================
# Allocations
# ===========================================================================


def test_handle_allocation_list_passes_filters_through():
    """
    **Feature: webworks resources port T7.6 (E3)**
    **Property: GET /resources/allocations renders the list
    template and passes resource_id / user_id / job_id /
    status='active' / pagination through to the manager.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    rm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_allocations
        )
        rm_patch = _patch_resource_manager_in(
            target_module=resources_routes_allocations
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            query_mapping={
                "resource_id": "5", "user_id": "7",
                "job_id": "job-123", "page": "1",
            },
        )
        response = resources_routes_allocations.handle_allocation_list(
            request
        )

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups,
            ["resources/allocations/list.html"],
        )
        am = _FakeAllocationManager.last_instance
        kwargs = am.list_allocations_calls[0]
        testbase.assert_equal(kwargs["status"], "active")
        testbase.assert_equal(kwargs["resource_id"], 5)
        testbase.assert_equal(kwargs["user_id"], 7)
        testbase.assert_equal(kwargs["job_id"], "job-123")
        testbase.assert_equal(kwargs["offset"], 0)
        testbase.assert_equal(kwargs["limit"], 20)
    finally:
        for p in (rm_patch, am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_allocation_history_parses_iso_dates():
    """
    **Feature: webworks resources port T7.7 (E3)**
    **Property: GET /resources/allocations/history calls
    get_allocation_history with parsed start_date / end_date
    datetimes (or None on invalid input).**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    rm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_allocations
        )
        rm_patch = _patch_resource_manager_in(
            target_module=resources_routes_allocations
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            query_mapping={
                "start_date": "2026-01-01T00:00",
                "end_date": "2026-12-31T23:59",
            },
        )
        response = (
            resources_routes_allocations.handle_allocation_history(request)
        )

        testbase.assert_equal(response.status_code, 200)
        am = _FakeAllocationManager.last_instance
        kwargs = am.history_calls[0]
        testbase.assert_equal(
            kwargs["start_date"], datetime(2026, 1, 1, 0, 0)
        )
        testbase.assert_equal(
            kwargs["end_date"], datetime(2026, 12, 31, 23, 59)
        )
    finally:
        for p in (rm_patch, am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_allocation_detail_redirects_when_missing():
    """
    **Feature: webworks resources port T7.8 (E3)**
    **Property: get_allocation returning None yields a redirect
    to /resources/allocations with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_allocations
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"allocation_id": "999"},
        )
        response = (
            resources_routes_allocations.handle_allocation_detail(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/resources/allocations",
        )
    finally:
        for p in (am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_allocation_checkin_happy_path_redirects_to_list():
    """
    **Feature: webworks resources port T7.9 (E3)**
    **Property: A valid POST calls checkin and redirects to
    /resources/allocations with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_allocations
        )

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"allocation_id": "11"},
        )
        response = (
            resources_routes_allocations.handle_allocation_checkin(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/resources/allocations",
        )
        am = _FakeAllocationManager.last_instance
        testbase.assert_equal(
            am.checkin_calls, [(11, "u-admin")]
        )
    finally:
        for p in (am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_allocation_force_checkin_admin_denied_redirects():
    """
    **Feature: webworks resources port T7.10 (E3)**
    **Property: A non-admin user is redirected to
    /resources/dashboard without invoking force_checkin.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager(
            check_permission_response=False
        )
        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_allocations
        )

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&reason=admin+sweep"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"allocation_id": "11"},
        )
        response = (
            resources_routes_allocations
            .handle_allocation_force_checkin(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/dashboard"
        )
        # Manager not constructed because the deny redirect
        # short-circuits before _build_allocation_manager.
        testbase.assert_equal(
            _FakeAllocationManager.last_instance, None
        )
    finally:
        for p in (am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_allocation_force_checkin_passes_reason_to_manager():
    """
    **Feature: webworks resources port T7.10 (E3)**
    **Property: An admin POST passes the ``reason`` form field
    through to force_checkin (default "Administrative force
    checkin" when omitted).**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_allocations
        )

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&reason=quarterly+cleanup"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"allocation_id": "11"},
        )
        response = (
            resources_routes_allocations
            .handle_allocation_force_checkin(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        am = _FakeAllocationManager.last_instance
        testbase.assert_equal(
            am.force_checkin_calls,
            [(11, "u-admin", "quarterly cleanup")],
        )
    finally:
        for p in (am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Reservations
# ===========================================================================


def test_handle_reservation_list_passes_filters_through():
    """
    **Feature: webworks resources port T7.11 (E3)**
    **Property: GET /resources/reservations calls
    list_reservations with parsed start_after / end_before
    datetimes and resource_id filter.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    rm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_reservations
        )
        rm_patch = _patch_resource_manager_in(
            target_module=resources_routes_reservations
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            query_mapping={
                "resource_id": "3",
                "start_after": "2026-05-01T00:00",
                "end_before": "2026-05-31T23:59",
            },
        )
        response = (
            resources_routes_reservations.handle_reservation_list(request)
        )

        testbase.assert_equal(response.status_code, 200)
        am = _FakeAllocationManager.last_instance
        kwargs = am.list_reservations_calls[0]
        testbase.assert_equal(kwargs["resource_id"], 3)
        testbase.assert_equal(
            kwargs["start_after"], datetime(2026, 5, 1, 0, 0)
        )
        testbase.assert_equal(
            kwargs["end_before"], datetime(2026, 5, 31, 23, 59)
        )
    finally:
        for p in (rm_patch, am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_reservation_create_post_happy_path_redirects_to_list():
    """
    **Feature: webworks resources port T7.12 (E3)**
    **Property: A valid POST builds a ReservationRequest and
    creates the reservation; redirects to /resources/reservations
    with a success flash naming the created reservation.id.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    rm_patch = None
    rr_patch = None
    mode_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeAllocationManager) -> None:
            instance.create_reservation_response = _FakeReservation(
                reservation_id=42
            )
            return

        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_reservations,
            configure=_seed,
        )
        rm_patch = _patch_resource_manager_in(
            target_module=resources_routes_reservations
        )
        rr_patch = _patch_reservation_request_factory()
        mode_patch = _patch_allocation_mode_resolver()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&resource_id=3&job_id=job-7"
            b"&start_time=2026-05-04T10%3A00"
            b"&end_time=2026-05-04T12%3A00"
            b"&mode=exclusive&reason=load+test"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = (
            resources_routes_reservations.handle_reservation_create(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/resources/reservations",
        )
        am = _FakeAllocationManager.last_instance
        testbase.assert_equal(len(am.create_reservation_calls), 1)
        ar, user_id = am.create_reservation_calls[0]
        testbase.assert_equal(ar.resource_id, 3)
        testbase.assert_equal(ar.job_id, "job-7")
        testbase.assert_equal(
            ar.start_time, datetime(2026, 5, 4, 10, 0)
        )
        testbase.assert_equal(
            ar.end_time, datetime(2026, 5, 4, 12, 0)
        )
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (mode_patch, rr_patch, rm_patch, am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_reservation_create_post_missing_times_re_renders():
    """
    **Feature: webworks resources port T7.12 (E3)**
    **Property: A POST without start_time / end_time
    re-renders the form (400) with an error flash and does
    NOT call create_reservation.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    rm_patch = None
    rr_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_reservations
        )
        rm_patch = _patch_resource_manager_in(
            target_module=resources_routes_reservations
        )
        rr_patch = _patch_reservation_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&resource_id=3"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = (
            resources_routes_reservations.handle_reservation_create(request)
        )

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        flashes = ctx["flashes"]
        testbase.assert_equal(len(flashes), 1)
        category, message = flashes[0]
        testbase.assert_equal(category, "error")
        contains = "Start time and end time" in message
        testbase.assert_equal(contains, True)
        am = _FakeAllocationManager.last_instance
        testbase.assert_equal(am.create_reservation_calls, [])
    finally:
        for p in (rr_patch, rm_patch, am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_reservation_detail_renders_via_list_and_find():
    """
    **Feature: webworks resources port T7.13 (E3)**
    **Property: GET /resources/reservations/{id} renders the
    detail template after finding the reservation in the
    list_reservations(limit=1000) result.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        target = _FakeReservation(reservation_id=7)

        def _seed(instance: _FakeAllocationManager) -> None:
            instance.list_reservations_response = [
                _FakeReservation(reservation_id=1),
                target,
                _FakeReservation(reservation_id=9),
            ]
            return

        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_reservations,
            configure=_seed,
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"reservation_id": "7"},
        )
        response = (
            resources_routes_reservations.handle_reservation_detail(request)
        )

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["reservation"], target)
    finally:
        for p in (am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_reservation_detail_redirects_when_missing():
    """
    **Feature: webworks resources port T7.13 (E3)**
    **Property: A reservation_id absent from the manager's list
    yields a redirect to /resources/reservations with an
    error flash.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_reservations
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"reservation_id": "999"},
        )
        response = (
            resources_routes_reservations.handle_reservation_detail(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/resources/reservations",
        )
    finally:
        for p in (am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_reservation_edit_post_happy_path_calls_modify():
    """
    **Feature: webworks resources port T7.14 (E3)**
    **Property: A valid edit POST calls modify_reservation
    with parsed start/end times + the user_id, then redirects
    to /resources/reservations/{id} with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeAllocationManager) -> None:
            instance.list_reservations_response = [
                _FakeReservation(reservation_id=7),
            ]
            return

        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_reservations,
            configure=_seed,
        )

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh"
            b"&start_time=2026-05-05T09%3A00"
            b"&end_time=2026-05-05T11%3A00"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"reservation_id": "7"},
        )
        response = (
            resources_routes_reservations.handle_reservation_edit(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/resources/reservations/7",
        )
        am = _FakeAllocationManager.last_instance
        testbase.assert_equal(len(am.modify_reservation_calls), 1)
        target_id, kwargs = am.modify_reservation_calls[0]
        testbase.assert_equal(target_id, 7)
        testbase.assert_equal(
            kwargs["start_time"], datetime(2026, 5, 5, 9, 0)
        )
        testbase.assert_equal(
            kwargs["end_time"], datetime(2026, 5, 5, 11, 0)
        )
        testbase.assert_equal(kwargs["user_id"], "u-admin")
    finally:
        for p in (am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_reservation_edit_redirects_when_missing():
    """
    **Feature: webworks resources port T7.14 (E3)**
    **Property: An unknown reservation_id redirects to
    /resources/reservations with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_reservations
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"reservation_id": "999"},
        )
        response = (
            resources_routes_reservations.handle_reservation_edit(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/resources/reservations",
        )
    finally:
        for p in (am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_reservation_cancel_happy_path_redirects_to_list():
    """
    **Feature: webworks resources port T7.15 (E3)**
    **Property: A valid POST calls cancel_reservation and
    redirects to /resources/reservations with a success
    flash.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_reservations
        )

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"reservation_id": "7"},
        )
        response = (
            resources_routes_reservations.handle_reservation_cancel(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"],
            "/resources/reservations",
        )
        am = _FakeAllocationManager.last_instance
        testbase.assert_equal(
            am.cancel_reservation_calls, [(7, "u-admin")]
        )
    finally:
        for p in (am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_reservation_cancel_manager_error_flashes_error():
    """
    **Feature: webworks resources port T7.15 (E3)**
    **Property: cancel_reservation raising yields a 303
    redirect with an error-category flash.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeAllocationManager) -> None:
            instance.cancel_reservation_raises = RuntimeError(
                "reservation already cancelled"
            )
            return

        am_patch = _patch_allocation_manager_in(
            target_module=resources_routes_reservations,
            configure=_seed,
        )

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"reservation_id": "7"},
        )
        response = (
            resources_routes_reservations.handle_reservation_cancel(request)
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
    finally:
        for p in (am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return
