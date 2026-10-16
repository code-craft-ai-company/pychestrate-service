"""
.. module:: test_p13g_config_sessions_audit_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the D4 (final) slice of the config
               blueprint port -- sessions + audit logs.

.. moduleauthor:: Code Craft AI LLC

PR D4 ports the remaining flask config routes (session admin
2 + audit log viewer 1; the legacy secret pages that were part
of it are gone, see ``specs/model-convergence.md`` section 10) to
webworks AND deletes the legacy ``endpoints.py`` flask
scaffolding. With this PR the ``/config`` surface is fully
webworks-native.

Tests cover:

* ``register_sessions_routes`` / ``register_audit_routes`` --
  route attachment matrices.
* session list (happy + filter passthrough), session terminate
  (happy + 404 + manager-error).
* audit log date-filter parsing. (The audit page now reads the
  canonical audit store; its behaviour is covered end to end in
  test_p31e_adm_audit_pipeline_m1.)
* Legacy flask scaffold gone:
  ``webinterface.blueprints.config`` no longer exposes
  ``config_blueprint`` / does not import ``endpoints``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
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
    routes_audit as config_routes_audit,
    routes_sessions as config_routes_sessions,
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
# Test stubs (mirror the D2/D3 fixtures)
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
        _FakeSecurityManager.last_instance = self
        return

    def validate_token(self, token: str) -> Optional[_FakeSessionInfo]:
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


# ---- Fakes specific to D4 -------------------------------------------------


class _SessionSeamRecorder:
    """
        Records calls to the patched ``routes_sessions`` data-access
        seams (``_list_active_sessions`` / ``_terminate_session``) and
        supplies their canned responses. ``list_calls`` records the
        ``(filter_username, offset, limit)`` triples the handler
        passed.
    """

    def __init__(self) -> None:
        self.list_calls: List[Any] = []
        self.list_response: List[Any] = []
        self.terminate_calls: List[str] = []
        self.terminate_raises: Optional[Exception] = None
        return


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


def _patch_session_seams(*, recorder: _SessionSeamRecorder) -> List[Any]:
    """
        Patch the modern ``_list_active_sessions`` / ``_terminate_session``
        seams in ``routes_sessions`` so the handler tests stay
        DB-independent. Returns the patches for the caller to deactivate.
    """
    def _fake_list(
            *,
            db_session: Any,
            filter_username: Optional[str],
            offset: int = 0,
            limit: int = 20,
            current_session_id: Optional[str] = None
        ) -> Any:
        recorder.list_calls.append((filter_username, offset, limit))
        rtnval = config_routes_sessions._SessionPage(
            rows=recorder.list_response,
            total=len(recorder.list_response),
        )
        return rtnval

    def _fake_terminate(
            *,
            db_session: Any,
            session_id: str,
            actor_user_id: Optional[str] = None
        ) -> None:
        recorder.terminate_calls.append(session_id)
        if recorder.terminate_raises is not None:
            raise recorder.terminate_raises
        return

    list_patch = create_module_patch(
        config_routes_sessions, "_list_active_sessions"
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=_fake_list)

    terminate_patch = create_module_patch(
        config_routes_sessions, "_terminate_session"
    )
    terminate_mock = terminate_patch.activate()
    terminate_mock.configure(side_effect=_fake_terminate)

    rtnval = [list_patch, terminate_patch]
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
    app = _FakeApp()
    config_routes.register_config_routes(app=app)
    return


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_sessions_routes_attaches_documented_routes():
    """
    **Feature: webworks config sessions port T4.2 (D4)**
    **Property: register_sessions_routes attaches the three
    session-admin routes at /admin/sessions* (list, terminate one,
    terminate all of a user's).**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        config_routes_sessions.register_sessions_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/admin/sessions", ("GET",)),
            (
                "/admin/sessions/{session_id}/terminate",
                ("POST",),
            ),
            (
                "/admin/sessions/user/{user_id}/terminate",
                ("POST",),
            ),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_audit_routes_attaches_documented_routes():
    """
    **Feature: webworks config audit port T4.3 (D4)**
    **Property: register_audit_routes attaches the audit-log
    viewer at /admin/audit-logs and its export at
    /admin/audit-logs/export.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        config_routes_audit.register_audit_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/admin/audit-logs", ("GET",)),
            ("/admin/audit-logs/export", ("GET",)),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Sessions -- list / terminate
# ===========================================================================


def test_handle_session_list_renders_with_active_sessions():
    """
    **Feature: webworks config sessions port T4.8**
    **Property: GET /admin/sessions renders the sessions list
    template with the _list_active_sessions page, passes the
    username filter + pagination params through to the seam,
    and exposes total / total_pages / current_session_id in the
    context.**
    """
    _reset_global_state()
    sm_patch = None
    seam_patches: List[Any] = []
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        when = datetime(2026, 6, 11, 12, 0, 0)
        active = [
            config_routes_sessions._SessionRow(
                session_id="11111111-1111-1111-1111-111111111111",
                username="alice",
                created_at=when,
                last_activity=when,
                expires_at=when,
                client_ip="10.0.0.1",
                user_agent="ua-a",
            ),
            config_routes_sessions._SessionRow(
                session_id="22222222-2222-2222-2222-222222222222",
                username="bob",
                created_at=when,
                last_activity=when,
                expires_at=when,
                client_ip="10.0.0.2",
                user_agent="ua-b",
            ),
        ]
        recorder = _SessionSeamRecorder()
        recorder.list_response = active
        seam_patches = _patch_session_seams(recorder=recorder)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            query_mapping={
                "username": "alice", "page": "2", "per_page": "10",
            },
        )
        response = config_routes_sessions.handle_session_list(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/sessions/list.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["sessions"], active)
        testbase.assert_equal(ctx["filter_username"], "alice")
        testbase.assert_equal(ctx["total"], 2)
        testbase.assert_equal(ctx["total_pages"], 1)
        # The cookie's session_token surfaces as the current
        # session id so the template can badge the own row.
        testbase.assert_equal(ctx["current_session_id"], "tok-abc")
        # Page 2 of a one-page result is past the end (e.g. after its
        # last sessions were terminated): the handler asks again for
        # the last page and renders that (ADM-33).
        testbase.assert_equal(
            recorder.list_calls, [("alice", 10, 10), ("alice", 0, 10)]
        )
        testbase.assert_equal(ctx["page"], 1)
    finally:
        for patch in seam_patches:
            patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_session_terminate_happy_path_redirects():
    """
    **Feature: webworks config sessions port T4.9**
    **Property: A valid POST calls _terminate_session with the
    session_id and redirects to /admin/sessions.**
    """
    _reset_global_state()
    sm_patch = None
    seam_patches: List[Any] = []
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        recorder = _SessionSeamRecorder()
        seam_patches = _patch_session_seams(recorder=recorder)

        target_session_id = "33333333-3333-3333-3333-333333333333"
        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"session_id": target_session_id},
        )
        response = config_routes_sessions.handle_session_terminate(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/sessions"
        )
        testbase.assert_equal(
            recorder.terminate_calls, [target_session_id]
        )
    finally:
        for patch in seam_patches:
            patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_session_terminate_service_error_flashes_error():
    """
    **Feature: webworks config sessions port T4.9**
    **Property: _terminate_session raising yields a 303 redirect
    with an error-category flash; the failure is non-fatal to
    the request lifecycle.**
    """
    _reset_global_state()
    sm_patch = None
    seam_patches: List[Any] = []
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        recorder = _SessionSeamRecorder()
        recorder.terminate_raises = RuntimeError(
            "session already terminated"
        )
        seam_patches = _patch_session_seams(recorder=recorder)

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={
                "session_id": "44444444-4444-4444-4444-444444444444"
            },
        )
        response = config_routes_sessions.handle_session_terminate(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
    finally:
        for patch in seam_patches:
            patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_session_terminate_missing_id_short_circuits():
    """
    **Feature: webworks config sessions port T4.9**
    **Property: A missing session_id path param yields a redirect
    with a "Session not found" flash WITHOUT calling
    _terminate_session.**
    """
    _reset_global_state()
    sm_patch = None
    seam_patches: List[Any] = []
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        recorder = _SessionSeamRecorder()
        seam_patches = _patch_session_seams(recorder=recorder)

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={},
        )
        response = config_routes_sessions.handle_session_terminate(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(recorder.terminate_calls, [])
    finally:
        for patch in seam_patches:
            patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Audit log viewer
# ===========================================================================


def test_parse_iso_datetime_or_none_handles_valid_and_invalid():
    """
    **Feature: webworks config audit port T4.11 (parser)**
    **Property: Valid ISO strings parse into datetimes; bad
    inputs return None rather than raising.**
    """
    parsed = config_routes_audit._parse_iso_datetime_or_none(
        raw="2026-01-15T10:30"
    )
    testbase.assert_equal(
        parsed, datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)
    )

    testbase.assert_equal(
        config_routes_audit._parse_iso_datetime_or_none(raw=None), None
    )
    testbase.assert_equal(
        config_routes_audit._parse_iso_datetime_or_none(raw=""), None
    )
    testbase.assert_equal(
        config_routes_audit._parse_iso_datetime_or_none(raw="garbage"),
        None,
    )
    return


# ===========================================================================
# Admin UX fixes -- pagination totals, masked errors, username
# filters, page titles
# ===========================================================================


def test_resolve_admin_page_title_maps_known_paths_and_defaults():
    """
    **Feature: admin UX -- per-page shell titles**
    **Property: _resolve_admin_page_title maps every admin
    section prefix to "<Label> · Pychestrate" (detail pages
    inherit their section) and keeps the bare product name for
    unknown paths.**
    """
    cases = (
        ("/admin/users", "Users · Pychestrate"),
        ("/admin/users/u-1/edit", "Users · Pychestrate"),
        ("/admin/variables", "Variables · Pychestrate"),
        ("/admin/sessions", "Sessions · Pychestrate"),
        ("/admin/audit-logs", "Audit Logs · Pychestrate"),
        ("/admin/enrollment-tokens", "Enrollment Tokens · Pychestrate"),
        ("/admin/variables/x/history", "Variables · Pychestrate"),
        ("/admin/feature-flags", "Feature Flags · Pychestrate"),
        ("/admin", "Pychestrate"),
        ("/admin/unknown-surface", "Pychestrate"),
        ("", "Pychestrate"),
    )
    for path, expected in cases:
        actual = config_routes._resolve_admin_page_title(path=path)
        testbase.assert_equal(actual, expected)
    return


# ===========================================================================
# Legacy flask scaffold gone
# ===========================================================================


def test_legacy_endpoints_module_no_longer_present():
    """
    **Feature: D4 cleanup T4.12**
    **Property: ``webinterface.blueprints.config.endpoints`` (the
    1,355-LOC flask handler module) no longer importable -- it
    was deleted in this PR.**
    """
    raised = False
    try:
        import importlib
        importlib.import_module(
            "ccai.pychestrate.webservice.webinterface."
            "blueprints.config.endpoints"
        )
    except ImportError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_legacy_config_blueprint_attribute_no_longer_exposed():
    """
    **Feature: D4 cleanup T4.12**
    **Property: ``webinterface.blueprints.config`` no longer
    exposes ``config_blueprint`` (the flask Blueprint object).
    All consumers have moved to register_config_routes.**
    """
    from ccai.pychestrate.webservice.webinterface.blueprints import (
        config as config_pkg,
    )
    has_attr = hasattr(config_pkg, "config_blueprint")
    testbase.assert_equal(has_attr, False)
    return
