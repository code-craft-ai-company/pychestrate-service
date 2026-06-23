"""
.. module:: test_p13g_config_secrets_sessions_audit_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the D4 (final) slice of the config
               blueprint port -- secrets + sessions + audit logs.

.. moduleauthor:: Code Craft AI LLC

PR D4 ports the remaining seven flask config routes (secret
management 4 + session admin 2 + audit log viewer 1) to
webworks AND deletes the legacy ``endpoints.py`` flask
scaffolding. With this PR the ``/config`` surface is fully
webworks-native.

Tests cover:

* ``register_secrets_routes`` / ``register_sessions_routes`` /
  ``register_audit_routes`` -- route attachment matrices.
* secret list / create (GET + POST happy + manager-error +
  CSRF) / edit (GET + POST happy + 404) / delete (happy +
  manager-error + unparsable id).
* session list (happy + filter passthrough), session terminate
  (happy + 404 + manager-error).
* audit_log_list (happy with filters + pagination, ISO date
  parse, _resolve_audit_event_type_or_none, default empty
  AuditLogListResponse handling).
* Legacy flask scaffold gone:
  ``webinterface.blueprints.config`` no longer exposes
  ``config_blueprint`` / does not import ``endpoints``.
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
    routes_audit as config_routes_audit,
    routes_secrets as config_routes_secrets,
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


class _FakeSecretMetadata:
    def __init__(
            self, *, secret_id: int, name: str, scope_id: int,
            scope_name: str = "default", description: str = "",
            version: int = 1
        ) -> None:
        self.id: int = secret_id
        self.name: str = name
        self.scope_id: int = scope_id
        self.scope_name: str = scope_name
        self.description: str = description
        self.version: int = version
        self.secret_type = type("ST", (), {"value": "generic"})()
        self.updated_at = datetime(2026, 1, 1, 12, 0)
        return


class _FakeSecretManager:
    last_instance: Optional["_FakeSecretManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_secrets_response: List[_FakeSecretMetadata] = []
        self.list_scopes_response: List[Any] = []
        self.get_metadata_response: Optional[_FakeSecretMetadata] = None
        self.list_secrets_calls: List[Dict[str, Any]] = []
        self.create_secret_calls: List[Any] = []
        self.update_secret_calls: List[Any] = []
        self.delete_secret_calls: List[Any] = []
        self.create_secret_raises: Optional[Exception] = None
        self.update_secret_raises: Optional[Exception] = None
        self.delete_secret_raises: Optional[Exception] = None
        _FakeSecretManager.last_instance = self
        return

    def list_secrets(
            self, *, scope_id: Optional[int], user_id: str,
            offset: int, limit: int
        ) -> Any:
        from types import SimpleNamespace
        self.list_secrets_calls.append({
            "scope_id": scope_id, "user_id": user_id,
            "offset": offset, "limit": limit,
        })
        return SimpleNamespace(
            secrets=self.list_secrets_response,
            total=len(self.list_secrets_response),
            offset=offset,
            limit=limit,
        )

    def list_scopes(self, user_id: str) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            scopes=self.list_scopes_response,
            total=len(self.list_scopes_response),
            offset=0,
            limit=len(self.list_scopes_response),
        )

    def get_secret_metadata(
            self, name: str, scope_id: int
        ) -> Optional[_FakeSecretMetadata]:
        return self.get_metadata_response

    def create_secret(self, request: Any, user_id: str) -> None:
        self.create_secret_calls.append((request, user_id))
        if self.create_secret_raises is not None:
            raise self.create_secret_raises
        return

    def update_secret(
            self, name: str, scope_id: int,
            request: Any, user_id: str
        ) -> None:
        self.update_secret_calls.append(
            (name, scope_id, request, user_id)
        )
        if self.update_secret_raises is not None:
            raise self.update_secret_raises
        return

    def delete_secret(
            self, name: str, scope_id: int, user_id: str
        ) -> None:
        self.delete_secret_calls.append((name, scope_id, user_id))
        if self.delete_secret_raises is not None:
            raise self.delete_secret_raises
        return


class _SessionSeamRecorder:
    """
        Records calls to the patched ``routes_sessions`` data-access
        seams (``_list_active_sessions`` / ``_terminate_session``) and
        supplies their canned responses.
    """

    def __init__(self) -> None:
        self.list_calls: List[Optional[str]] = []
        self.list_response: List[Any] = []
        self.terminate_calls: List[str] = []
        self.terminate_raises: Optional[Exception] = None
        return


class _FakeAuditLogEntry:
    def __init__(self, *, entry_id: int, event_type_value: str) -> None:
        self.id: int = entry_id
        self.event_type = type("ET", (), {"value": event_type_value})()
        self.timestamp = datetime(2026, 1, 1, 12, 0)
        self.username: Optional[str] = "admin"
        self.user_id: Optional[str] = "u-admin"
        self.target_username: Optional[str] = None
        self.target_user_id: Optional[str] = None
        self.client_ip: Optional[str] = None
        self.details: Optional[Dict[str, Any]] = None
        return


class _FakeAuditLogResponse:
    def __init__(
            self, *, entries: List[_FakeAuditLogEntry], total: int = 0
        ) -> None:
        self.entries: List[_FakeAuditLogEntry] = entries
        self.total: int = total
        self.offset: int = 0
        self.limit: int = 50
        return


class _FakeAuditLogger:
    last_instance: Optional["_FakeAuditLogger"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.query_logs_response: Optional[_FakeAuditLogResponse] = None
        self.query_logs_calls: List[Any] = []
        _FakeAuditLogger.last_instance = self
        return

    def query_logs(self, query: Any) -> _FakeAuditLogResponse:
        self.query_logs_calls.append(query)
        if self.query_logs_response is None:
            return _FakeAuditLogResponse(entries=[])
        return self.query_logs_response


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
    _FakeSecretManager.last_instance = None
    _FakeAuditLogger.last_instance = None
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


def _patch_secret_manager(
        *, configure: Optional[Callable[[_FakeSecretManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeSecretManager:
        instance = _FakeSecretManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        config_routes_secrets, "_build_secret_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_secret_create_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        config_routes_secrets, "_build_secret_create_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_secret_update_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        config_routes_secrets, "_build_secret_update_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_resolve_secret_type() -> Any:
    def _resolve(*, secret_type_str: str) -> Any:
        return type("ST", (), {"value": secret_type_str})()

    patch = create_module_patch(
        config_routes_secrets, "_resolve_secret_type"
    )
    mock = patch.activate()
    mock.configure(side_effect=_resolve)
    return patch


def _patch_session_seams(*, recorder: _SessionSeamRecorder) -> List[Any]:
    """
        Patch the modern ``_list_active_sessions`` / ``_terminate_session``
        seams in ``routes_sessions`` so the handler tests stay
        DB-independent. Returns the patches for the caller to deactivate.
    """
    def _fake_list(
            *, db_session: Any, filter_user_id: Optional[str]
        ) -> List[Any]:
        recorder.list_calls.append(filter_user_id)
        return recorder.list_response

    def _fake_terminate(*, db_session: Any, session_id: str) -> None:
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


def _patch_audit_logger(
        *, configure: Optional[Callable[[_FakeAuditLogger], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeAuditLogger:
        instance = _FakeAuditLogger(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        config_routes_audit, "_build_audit_logger"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_audit_log_query_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        config_routes_audit, "_build_audit_log_query"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_resolve_audit_event_type_or_none(
        *, returns: Optional[List[Any]] = None
    ) -> Any:
    def _resolve(*, event_type_str: Optional[str]) -> Optional[List[Any]]:
        return returns

    patch = create_module_patch(
        config_routes_audit, "_resolve_audit_event_type_or_none"
    )
    mock = patch.activate()
    mock.configure(side_effect=_resolve)
    return patch


def _patch_resolve_all_audit_event_types(
        *, returns: List[str]
    ) -> Any:
    def _resolve() -> List[str]:
        return returns

    patch = create_module_patch(
        config_routes_audit, "_resolve_all_audit_event_types"
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
    app = _FakeApp()
    config_routes.register_config_routes(app=app)
    return


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_secrets_routes_attaches_documented_routes():
    """
    **Feature: webworks config secrets port T4.1 (D4)**
    **Property: register_secrets_routes attaches the four
    secret-management routes at /admin/secrets*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        config_routes_secrets.register_secrets_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/admin/secrets", ("GET",)),
            ("/admin/secrets/create", ("GET", "POST")),
            (
                "/admin/secrets/{scope_id}/{name}/edit",
                ("GET", "POST"),
            ),
            (
                "/admin/secrets/{scope_id}/{name}/delete",
                ("POST",),
            ),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_sessions_routes_attaches_documented_routes():
    """
    **Feature: webworks config sessions port T4.2 (D4)**
    **Property: register_sessions_routes attaches the two
    session-admin routes at /admin/sessions*.**
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
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_audit_routes_attaches_documented_routes():
    """
    **Feature: webworks config audit port T4.3 (D4)**
    **Property: register_audit_routes attaches the single
    audit-log viewer route at /admin/audit-logs.**
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
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Secrets -- list / create / edit / delete
# ===========================================================================


def test_handle_secret_list_renders_with_filters():
    """
    **Feature: webworks config secrets port T4.4**
    **Property: GET /admin/secrets renders config/secrets/
    list.html with the secret_manager outputs and the
    selected_scope_id filter passed through.**
    """
    _reset_global_state()
    sm_patch = None
    secret_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        secrets = [
            _FakeSecretMetadata(
                secret_id=1, name="db_pw", scope_id=2,
                scope_name="prod"
            )
        ]

        def _seed(instance: _FakeSecretManager) -> None:
            instance.list_secrets_response = secrets
            instance.list_scopes_response = []
            return

        secret_patch = _patch_secret_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            query_mapping={"page": "2", "per_page": "10", "scope_id": "5"},
        )
        response = config_routes_secrets.handle_secret_list(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/secrets/list.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["secrets"], secrets)
        testbase.assert_equal(ctx["selected_scope_id"], 5)
        sm = _FakeSecretManager.last_instance
        testbase.assert_equal(sm.list_secrets_calls[0]["scope_id"], 5)
        testbase.assert_equal(sm.list_secrets_calls[0]["offset"], 10)
        testbase.assert_equal(sm.list_secrets_calls[0]["limit"], 10)
    finally:
        for p in (secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_secret_create_post_happy_path_redirects_to_list():
    """
    **Feature: webworks config secrets port T4.5**
    **Property: A valid POST creates the secret via SecretManager
    and redirects to /admin/secrets with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    secret_patch = None
    cr_patch = None
    rt_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        secret_patch = _patch_secret_manager()
        cr_patch = _patch_secret_create_request_factory()
        rt_patch = _patch_resolve_secret_type()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=db_pw&value=hunter2"
            b"&secret_type=password&scope_id=2&description=DB+admin"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_secrets.handle_secret_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/secrets"
        )
        sm = _FakeSecretManager.last_instance
        testbase.assert_equal(len(sm.create_secret_calls), 1)
        ar, user_id = sm.create_secret_calls[0]
        testbase.assert_equal(ar.name, "db_pw")
        testbase.assert_equal(ar.scope_id, 2)
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (rt_patch, cr_patch, secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_secret_create_post_manager_error_re_renders_with_flash():
    """
    **Feature: webworks config secrets port T4.5**
    **Property: A SecretManager exception on create yields a
    400 re-render with an error-category flash.**
    """
    _reset_global_state()
    sm_patch = None
    secret_patch = None
    cr_patch = None
    rt_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeSecretManager) -> None:
            instance.create_secret_raises = RuntimeError(
                "duplicate secret name"
            )
            return

        secret_patch = _patch_secret_manager(configure=_seed)
        cr_patch = _patch_secret_create_request_factory()
        rt_patch = _patch_resolve_secret_type()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=db_pw&value=x"
            b"&secret_type=password&scope_id=2"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_secrets.handle_secret_create(request)

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        category, message = ctx["flashes"][0]
        testbase.assert_equal(category, "error")
        contains = "duplicate" in message
        testbase.assert_equal(contains, True)
    finally:
        for p in (rt_patch, cr_patch, secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_secret_edit_post_happy_path_redirects_to_list():
    """
    **Feature: webworks config secrets port T4.6**
    **Property: A valid edit POST calls update_secret with
    name/scope_id/UpdateRequest/user_id and redirects.**
    """
    _reset_global_state()
    sm_patch = None
    secret_patch = None
    upd_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        secret_patch = _patch_secret_manager()
        upd_patch = _patch_secret_update_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&value=newpw&description=Updated"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"scope_id": "3", "name": "db_pw"},
        )
        response = config_routes_secrets.handle_secret_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/secrets"
        )
        sm = _FakeSecretManager.last_instance
        testbase.assert_equal(len(sm.update_secret_calls), 1)
        name, scope_id, ar, user_id = sm.update_secret_calls[0]
        testbase.assert_equal(name, "db_pw")
        testbase.assert_equal(scope_id, 3)
        testbase.assert_equal(ar.value, "newpw")
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (upd_patch, secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_secret_edit_get_redirects_when_metadata_missing():
    """
    **Feature: webworks config secrets port T4.6**
    **Property: get_secret_metadata returning None yields a
    redirect to /admin/secrets with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    secret_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        secret_patch = _patch_secret_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"scope_id": "3", "name": "ghost"},
        )
        response = config_routes_secrets.handle_secret_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/secrets"
        )
    finally:
        for p in (secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_secret_delete_happy_path_redirects_to_list():
    """
    **Feature: webworks config secrets port T4.7**
    **Property: A valid POST calls SecretManager.delete_secret
    and redirects with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    secret_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        secret_patch = _patch_secret_manager()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"scope_id": "3", "name": "db_pw"},
        )
        response = config_routes_secrets.handle_secret_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/secrets"
        )
        sm = _FakeSecretManager.last_instance
        testbase.assert_equal(
            sm.delete_secret_calls, [("db_pw", 3, "u-admin")]
        )
    finally:
        for p in (secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_secret_delete_unparsable_scope_id_short_circuits():
    """
    **Feature: webworks config secrets port T4.7**
    **Property: A non-int scope_id path param yields a
    redirect to the list with an error flash WITHOUT building
    the SecretManager / calling delete_secret.**
    """
    _reset_global_state()
    sm_patch = None
    secret_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        secret_patch = _patch_secret_manager()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"scope_id": "not-an-int", "name": "db_pw"},
        )
        response = config_routes_secrets.handle_secret_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(_FakeSecretManager.last_instance, None)
    finally:
        for p in (secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Sessions -- list / terminate
# ===========================================================================


def test_handle_session_list_renders_with_active_sessions():
    """
    **Feature: webworks config sessions port T4.8**
    **Property: GET /admin/sessions renders the sessions list
    template with the _list_active_sessions output and passes
    filter_user_id through.**
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
            query_mapping={"user_id": "u-7"},
        )
        response = config_routes_sessions.handle_session_list(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/sessions/list.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["sessions"], active)
        testbase.assert_equal(ctx["filter_user_id"], "u-7")
        testbase.assert_equal(recorder.list_calls, ["u-7"])
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


def test_handle_audit_log_list_renders_with_filters():
    """
    **Feature: webworks config audit port T4.10**
    **Property: GET /admin/audit-logs renders config/audit/
    list.html with logs (entries), all_event_types,
    filter_user_id, selected_event_type, and the original ISO
    date strings passed back through.**
    """
    _reset_global_state()
    sm_patch = None
    al_patch = None
    q_patch = None
    et_patch = None
    aet_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        entries = [
            _FakeAuditLogEntry(entry_id=1, event_type_value="LOGIN_SUCCESS"),
            _FakeAuditLogEntry(entry_id=2, event_type_value="LOGOUT"),
        ]

        def _seed(instance: _FakeAuditLogger) -> None:
            instance.query_logs_response = _FakeAuditLogResponse(
                entries=entries, total=2
            )
            return

        al_patch = _patch_audit_logger(configure=_seed)
        q_patch = _patch_audit_log_query_factory()
        # Stub the type resolver so the route doesn't try to import
        # the real AuditEventType.
        et_patch = _patch_resolve_audit_event_type_or_none(
            returns=["LOGIN_SUCCESS"]
        )
        aet_patch = _patch_resolve_all_audit_event_types(
            returns=["LOGIN_SUCCESS", "LOGOUT"]
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            query_mapping={
                "page": "1", "per_page": "50",
                "event_type": "LOGIN_SUCCESS", "user_id": "u-7",
                "start_date": "2026-01-01T00:00",
                "end_date": "2026-12-31T23:59",
            },
        )
        response = config_routes_audit.handle_audit_log_list(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/audit/list.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["logs"], entries)
        testbase.assert_equal(
            ctx["all_event_types"], ["LOGIN_SUCCESS", "LOGOUT"]
        )
        testbase.assert_equal(ctx["selected_event_type"], "LOGIN_SUCCESS")
        testbase.assert_equal(ctx["filter_user_id"], "u-7")
        testbase.assert_equal(ctx["start_date"], "2026-01-01T00:00")
        testbase.assert_equal(ctx["end_date"], "2026-12-31T23:59")
        # The query was built with the parsed datetimes + filters.
        al = _FakeAuditLogger.last_instance
        testbase.assert_equal(len(al.query_logs_calls), 1)
        q = al.query_logs_calls[0]
        testbase.assert_equal(q.user_id, "u-7")
        testbase.assert_equal(q.event_types, ["LOGIN_SUCCESS"])
        testbase.assert_equal(q.offset, 0)
        testbase.assert_equal(q.limit, 50)
    finally:
        for p in (aet_patch, et_patch, q_patch, al_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_audit_log_list_handles_empty_response():
    """
    **Feature: webworks config audit port T4.10**
    **Property: A query with no matching entries yields
    logs=[].**
    """
    _reset_global_state()
    sm_patch = None
    al_patch = None
    q_patch = None
    et_patch = None
    aet_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        al_patch = _patch_audit_logger()
        q_patch = _patch_audit_log_query_factory()
        et_patch = _patch_resolve_audit_event_type_or_none(returns=None)
        aet_patch = _patch_resolve_all_audit_event_types(returns=[])

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
        )
        response = config_routes_audit.handle_audit_log_list(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["logs"], [])
        testbase.assert_equal(ctx["all_event_types"], [])
    finally:
        for p in (aet_patch, et_patch, q_patch, al_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_parse_iso_datetime_or_none_handles_valid_and_invalid():
    """
    **Feature: webworks config audit port T4.11 (parser)**
    **Property: Valid ISO strings parse into datetimes; bad
    inputs return None rather than raising.**
    """
    parsed = config_routes_audit._parse_iso_datetime_or_none(
        raw="2026-01-15T10:30"
    )
    testbase.assert_equal(parsed, datetime(2026, 1, 15, 10, 30))

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


def test_audit_log_response_to_entries_handles_dataclass_and_list():
    """
    **Feature: webworks config audit port T4.11 (response shape)**
    **Property: The helper handles both the documented
    AuditLogListResponse (with .entries) and a bare list (the
    test fakes may return either shape).**
    """
    entries = [_FakeAuditLogEntry(entry_id=1, event_type_value="X")]

    response = _FakeAuditLogResponse(entries=entries, total=1)
    rtnval = config_routes_audit._audit_log_response_to_entries(
        response=response
    )
    testbase.assert_equal(rtnval, entries)

    rtnval = config_routes_audit._audit_log_response_to_entries(
        response=entries
    )
    testbase.assert_equal(rtnval, entries)

    rtnval = config_routes_audit._audit_log_response_to_entries(
        response=None
    )
    testbase.assert_equal(rtnval, [])
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
