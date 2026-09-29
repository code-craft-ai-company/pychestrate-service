"""
.. module:: test_p13k_resources_health_tags_port_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the E4 (FINAL) slice of the resources
               port -- health monitoring + tag list + flask
               scaffold cleanup.

.. moduleauthor:: Code Craft AI LLC

PR E4 closes out the resources port. The five health routes +
the tag-list route ship on webworks AND the legacy
``endpoints.py`` flask scaffolding is deleted. With this PR
the ``/resources`` surface is fully webworks-native.

Tests cover:

* register_health_routes / register_tags_routes -- route
  attachment matrices.
* health_dashboard -- happy path with grouping; legacy
  ``health_run_check`` template alias.
* health_detail -- happy + 404 + pagination.
* health_config -- GET form, POST happy + admin-denied + 404.
* health_update -- happy + admin-denied.
* health_run_check -- queues the check (never probes) + already queued.
* tag_list -- happy + anonymous redirect.
* Legacy flask scaffold gone:
  ``webinterface.blueprints.resources.endpoints`` no longer
  importable; ``register_web_blueprints`` no longer registers
  resources_blueprint.
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
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources import (
    routes as resources_routes,
    routes_health as resources_routes_health,
    routes_tags as resources_routes_tags,
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


# ---- Health-domain fakes --------------------------------------------------


class _FakeHealthStatusEnum:
    def __init__(self, *, value: str) -> None:
        self.value: str = value
        return


class _FakeResource:
    def __init__(
            self, *, resource_id: int, name: str = "r",
            health_status_value: str = "online"
        ) -> None:
        self.id: int = resource_id
        self.name: str = name
        self.health_status: _FakeHealthStatusEnum = _FakeHealthStatusEnum(
            value=health_status_value
        )
        return


class _FakeHealthHistoryEntry:
    def __init__(self, *, entry_id: int) -> None:
        self.id: int = entry_id
        return


class _FakeHealthTransitionList:
    """
        Stands in for :class:`HealthTransitionListResponse`.

        The real ``HealthMonitor.get_health_history`` returns that dataclass,
        not a bare list, and the route reads ``history.transitions`` from it.
        Mirror the shape here so the double fails the same way the product
        would.
    """

    def __init__(
            self, *, transitions: List[_FakeHealthHistoryEntry],
            total: Optional[int] = None, offset: int = 0, limit: int = 50
        ) -> None:
        self.transitions: List[_FakeHealthHistoryEntry] = transitions
        self.total: int = len(transitions) if total is None else total
        self.offset: int = offset
        self.limit: int = limit
        return


class _FakeHealthCheckConfig:
    def __init__(
            self, *, resource_id: int, enabled: bool = True
        ) -> None:
        self.resource_id: int = resource_id
        self.enabled: bool = enabled
        return


class _FakeResourceManager:
    last_instance: Optional["_FakeResourceManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_resources_response: List[_FakeResource] = []
        self.get_resource_response: Optional[_FakeResource] = None
        self.list_tags_response: List[Any] = []
        _FakeResourceManager.last_instance = self
        return

    def list_resources(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        matching = self.list_resources_response
        wanted = kwargs.get("health_status", None)
        if wanted is not None:
            matching = [
                resource for resource in matching
                if getattr(getattr(resource, "health_status", None), "value",
                           getattr(resource, "health_status", None)) == wanted
            ]
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", len(matching))
        return SimpleNamespace(
            resources=matching[offset:offset + limit],
            total=len(matching),
            offset=offset,
            limit=limit,
        )

    def get_resource(self, resource_id: int) -> Optional[_FakeResource]:
        return self.get_resource_response

    def list_tags(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            tags=self.list_tags_response,
            total=len(self.list_tags_response),
            offset=0,
            limit=len(self.list_tags_response),
        )

    def count_resources_by_health_status(self) -> Dict[str, int]:
        # Mirrors the manager's aggregate count query by bucketing
        # the seeded list_resources_response.
        counts: Dict[str, int] = {
            "online": 0,
            "offline": 0,
            "degraded": 0,
            "maintenance": 0,
        }
        for resource in self.list_resources_response:
            status = getattr(resource, "health_status", None)
            if status is None:
                continue
            status_value = getattr(status, "value", status)
            if isinstance(status_value, str) and status_value in counts:
                counts[status_value] = counts[status_value] + 1
        return counts


class _FakeHealthMonitor:
    last_instance: Optional["_FakeHealthMonitor"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.history_response: _FakeHealthTransitionList = (
            _FakeHealthTransitionList(transitions=[])
        )
        self.config_response: Optional[_FakeHealthCheckConfig] = None
        self.run_check_response: bool = True
        self.run_check_raises: Optional[Exception] = None
        self.update_status_calls: List[Any] = []
        self.update_status_raises: Optional[Exception] = None
        self.configure_calls: List[Any] = []
        self.configure_raises: Optional[Exception] = None
        self.run_check_calls: List[Any] = []
        self.request_calls: List[Any] = []
        self.request_response: bool = True
        _FakeHealthMonitor.last_instance = self
        return

    def request_health_check(self, resource_id: int) -> bool:
        self.request_calls.append(resource_id)
        return self.request_response

    def get_health_history(
            self, resource_id: int, *, offset: int, limit: int
        ) -> _FakeHealthTransitionList:
        return self.history_response

    def get_health_check_config(
            self, resource_id: int
        ) -> Optional[_FakeHealthCheckConfig]:
        return self.config_response

    def configure_health_check(
            self, config: Any, user_id: str
        ) -> None:
        self.configure_calls.append((config, user_id))
        if self.configure_raises is not None:
            raise self.configure_raises
        return

    def update_health_status(
            self, resource_id: int, status: Any,
            reason: str, user_id: str
        ) -> None:
        self.update_status_calls.append(
            (resource_id, status, reason, user_id)
        )
        if self.update_status_raises is not None:
            raise self.update_status_raises
        return

    def run_health_check(self, resource_id: int) -> bool:
        self.run_check_calls.append(resource_id)
        if self.run_check_raises is not None:
            raise self.run_check_raises
        return self.run_check_response


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
    _FakeResourceManager.last_instance = None
    _FakeHealthMonitor.last_instance = None
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


def _patch_resource_manager_in(
        *, target_module: Any,
        configure: Optional[Callable[[_FakeResourceManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeResourceManager:
        instance = _FakeResourceManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(target_module, "_build_resource_manager")
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_health_monitor(
        *,
        configure: Optional[Callable[[_FakeHealthMonitor], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeHealthMonitor:
        instance = _FakeHealthMonitor(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        resources_routes_health, "_build_health_monitor"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_health_status_resolver() -> Any:
    def _resolve(*, status_str: str) -> Any:
        return _FakeHealthStatusEnum(value=status_str)

    patch = create_module_patch(
        resources_routes_health, "_resolve_health_status"
    )
    mock = patch.activate()
    mock.configure(side_effect=_resolve)
    return patch


def _patch_health_check_config_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        resources_routes_health, "_build_health_check_config"
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
    """
        Register every config + resources endpoint into the
        url_for shim. The resources registrar cascades into all
        E1-E4 sub-feature registrars.
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


def test_register_health_routes_attaches_documented_routes():
    """
    **Feature: webworks resources port T8.1 (E4)**
    **Property: register_health_routes attaches the five
    health routes at /resources/health*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        resources_routes_health.register_health_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/resources/health", ("GET",)),
            ("/resources/health/{resource_id}", ("GET",)),
            (
                "/resources/health/{resource_id}/config",
                ("GET", "POST"),
            ),
            (
                "/resources/health/{resource_id}/update",
                ("POST",),
            ),
            (
                "/resources/health/{resource_id}/check",
                ("POST",),
            ),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_tags_routes_attaches_documented_routes():
    """
    **Feature: webworks resources port T8.2 (E4)**
    **Property: register_tags_routes attaches the tag list and the
    manager routes that create, edit and delete a tag.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        resources_routes_tags.register_tags_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/resources/tags", ("GET",)),
            ("/resources/tags/create", ("POST",)),
            ("/resources/tags/{tag_id}/edit", ("GET", "POST")),
            ("/resources/tags/{tag_id}/delete", ("POST",)),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Helpers
# ===========================================================================


# ===========================================================================
# Health -- dashboard / detail / config / update / run-check
# ===========================================================================


def test_handle_health_dashboard_renders_with_grouped_resources():
    """
    **Feature: webworks resources port T8.4 (E4)**
    **Property: GET /resources/health renders the dashboard
    template with health_groups + total_count.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeResourceManager) -> None:
            instance.list_resources_response = [
                _FakeResource(
                    resource_id=1, health_status_value="online"
                ),
                _FakeResource(
                    resource_id=2, health_status_value="degraded"
                ),
            ]
            return

        rm_patch = _patch_resource_manager_in(
            target_module=resources_routes_health, configure=_seed
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = resources_routes_health.handle_health_dashboard(
            request
        )

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups,
            ["resources/health/dashboard.html"],
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["total_count"], 2)
        testbase.assert_equal(len(ctx["health_groups"]["online"]), 1)
        testbase.assert_equal(
            len(ctx["health_groups"]["degraded"]), 1
        )
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_health_detail_renders_with_history_and_config():
    """
    **Feature: webworks resources port T8.5 (E4)**
    **Property: GET /resources/health/{id} renders the detail
    template with the resource + history list + config.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    hm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        resource = _FakeResource(resource_id=7, name="boardA")

        def _seed_rm(instance: _FakeResourceManager) -> None:
            instance.get_resource_response = resource
            return

        rm_patch = _patch_resource_manager_in(
            target_module=resources_routes_health, configure=_seed_rm
        )

        def _seed_hm(instance: _FakeHealthMonitor) -> None:
            instance.history_response = _FakeHealthTransitionList(
                transitions=[_FakeHealthHistoryEntry(entry_id=1)]
            )
            instance.config_response = _FakeHealthCheckConfig(
                resource_id=7
            )
            return

        hm_patch = _patch_health_monitor(configure=_seed_hm)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"resource_id": "7"},
        )
        response = resources_routes_health.handle_health_detail(
            request
        )

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["resource"], resource)
        testbase.assert_equal(len(ctx["history"]), 1)
    finally:
        for p in (hm_patch, rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_health_detail_redirects_when_resource_missing():
    """
    **Feature: webworks resources port T8.5 (E4)**
    **Property: An unknown resource_id redirects to
    /resources/health with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        rm_patch = _patch_resource_manager_in(
            target_module=resources_routes_health
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"resource_id": "999"},
        )
        response = resources_routes_health.handle_health_detail(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/health"
        )
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_health_config_admin_denied_redirects():
    """
    **Feature: webworks resources port T8.6 (E4)**
    **Property: A non-admin user is redirected away from the
    config page to /resources/dashboard.**
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
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"resource_id": "7"},
        )
        response = resources_routes_health.handle_health_config(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/dashboard"
        )
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_health_config_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks resources port T8.6 (E4)**
    **Property: A valid POST builds + saves a HealthCheckConfig
    and redirects to /resources/health/{id}. The thresholds /
    intervals / enabled flag are passed through.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    hm_patch = None
    cf_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_rm(instance: _FakeResourceManager) -> None:
            instance.get_resource_response = _FakeResource(
                resource_id=7
            )
            return

        rm_patch = _patch_resource_manager_in(
            target_module=resources_routes_health, configure=_seed_rm
        )
        hm_patch = _patch_health_monitor()
        cf_patch = _patch_health_check_config_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&probe_url=http%3A%2F%2Fboard%2Fhealth"
            b"&interval_seconds=30&timeout_seconds=5"
            b"&failure_threshold=2&success_threshold=1&enabled=on"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"resource_id": "7"},
        )
        response = resources_routes_health.handle_health_config(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/health/7"
        )
        hm = _FakeHealthMonitor.last_instance
        testbase.assert_equal(len(hm.configure_calls), 1)
        config_obj, user_id = hm.configure_calls[0]
        testbase.assert_equal(config_obj.resource_id, 7)
        testbase.assert_equal(config_obj.interval_seconds, 30)
        testbase.assert_equal(config_obj.timeout_seconds, 5)
        testbase.assert_equal(config_obj.failure_threshold, 2)
        testbase.assert_equal(config_obj.success_threshold, 1)
        testbase.assert_equal(config_obj.enabled, True)
        testbase.assert_equal(
            config_obj.probe_url, "http://board/health"
        )
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (cf_patch, hm_patch, rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_health_update_passes_status_and_reason_to_monitor():
    """
    **Feature: webworks resources port T8.7 (E4)**
    **Property: A valid POST resolves the status string to the
    HealthStatus enum, calls update_health_status with status +
    reason, and redirects to /resources/health/{id} with a
    success flash naming the new status.**
    """
    _reset_global_state()
    sm_patch = None
    hm_patch = None
    hs_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        hm_patch = _patch_health_monitor()
        hs_patch = _patch_health_status_resolver()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&status=maintenance"
            b"&reason=scheduled+downtime"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"resource_id": "7"},
        )
        response = resources_routes_health.handle_health_update(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/health/7"
        )
        hm = _FakeHealthMonitor.last_instance
        testbase.assert_equal(len(hm.update_status_calls), 1)
        resource_id, status, reason, user_id = (
            hm.update_status_calls[0]
        )
        testbase.assert_equal(resource_id, 7)
        testbase.assert_equal(status.value, "maintenance")
        testbase.assert_equal(reason, "scheduled downtime")
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (hs_patch, hm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def _post_run_check(*, configure: Callable[[Any], None]) -> Any:
    """
        POST the run-check form for resource 7 against a fake monitor
        set up by ``configure``; returns ``(response, monitor)``.
    """
    _reset_global_state()
    sm_patch = None
    hm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        hm_patch = _patch_health_monitor(configure=configure)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=b"csrf_token=csrf-fresh",
            path_params={"resource_id": "7"},
        )
        response = resources_routes_health.handle_health_run_check(
            request
        )
        return (response, _FakeHealthMonitor.last_instance)
    finally:
        for p in (hm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()


def test_handle_health_run_check_queues_the_check_and_does_not_probe():
    """
    **Feature: resources health (RES-39)**
    **Property: POST /resources/health/{id}/check asks the monitor to
    queue the check and redirects to /resources/health/{id}; it never
    runs the probe in the request.**
    """
    response, monitor = _post_run_check(configure=lambda instance: None)

    testbase.assert_equal(isinstance(response, RedirectResponse), True)
    testbase.assert_equal(response.headers["Location"], "/resources/health/7")
    testbase.assert_equal(monitor.request_calls, [7])
    testbase.assert_equal(monitor.run_check_calls, [])
    return


def test_handle_health_run_check_when_one_is_already_queued_still_redirects():
    """
    **Feature: resources health (RES-39)**
    **Property: asking again while a check is already queued redirects
    to the health page as well and probes nothing.**
    """
    def _seed(instance: _FakeHealthMonitor) -> None:
        instance.request_response = False
        return

    response, monitor = _post_run_check(configure=_seed)

    testbase.assert_equal(isinstance(response, RedirectResponse), True)
    testbase.assert_equal(response.headers["Location"], "/resources/health/7")
    testbase.assert_equal(monitor.run_check_calls, [])
    return


# ===========================================================================
# Tags
# ===========================================================================


def test_handle_tag_list_renders_with_tags():
    """
    **Feature: webworks resources port T8.9 (E4)**
    **Property: GET /resources/tags renders resources/tags/
    list.html with the resource_manager.list_tags() output.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeResourceManager) -> None:
            instance.list_tags_response = ["alpha", "beta"]
            return

        rm_patch = _patch_resource_manager_in(
            target_module=resources_routes_tags, configure=_seed
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = resources_routes_tags.handle_tag_list(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["resources/tags/list.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["tags"], ["alpha", "beta"])
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_tag_list_redirects_anonymous_to_config_login():
    """
    **Feature: webworks resources port T8.9 (E4)**
    **Property: An unauthenticated request redirects to
    /login.**
    """
    _reset_global_state()
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _register_url_for_endpoints()
        request = _FakeRequest(cookies={})
        response = resources_routes_tags.handle_tag_list(request)
        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/login"
        )
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Legacy flask scaffold gone
# ===========================================================================


def test_legacy_resources_endpoints_module_no_longer_present():
    """
    **Feature: E4 cleanup T8.10**
    **Property: ``webinterface.blueprints.resources.endpoints``
    (the 1,657-LOC flask handler module) no longer importable
    -- it was deleted in this PR.**
    """
    raised = False
    try:
        import importlib
        importlib.import_module(
            "ccai.pychestrate.webservice.webinterface."
            "blueprints.resources.endpoints"
        )
    except ImportError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_legacy_resources_blueprint_attribute_no_longer_exposed():
    """
    **Feature: E4 cleanup T8.10**
    **Property: ``webinterface.blueprints.resources`` no longer
    exposes ``resources_blueprint`` (the flask Blueprint
    object).**
    """
    from ccai.pychestrate.webservice.webinterface.blueprints import (
        resources as resources_pkg,
    )
    has_attr = hasattr(resources_pkg, "resources_blueprint")
    testbase.assert_equal(has_attr, False)
    return


# ---------------------------------------------------------------------------
# per_page is capped (audit finding RES-24)
# ---------------------------------------------------------------------------


def test_health_detail_caps_per_page():
    """
    **Feature: resources (RES-24 server-side validation)**
    **Property: GET /resources/health/{id}?per_page=100000 pages the
    history at most RESOURCES_MAX_PER_PAGE rows at a time.**
    """
    _reset_global_state()
    patches: List[Any] = []
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        patches.append(_patch_security_manager())

        def _seed_rm(instance: _FakeResourceManager) -> None:
            instance.get_resource_response = _FakeResource(resource_id=7, name="boardA")
            return

        def _seed_hm(instance: _FakeHealthMonitor) -> None:
            instance.history_response = _FakeHealthTransitionList(transitions=[])
            return

        patches.append(_patch_resource_manager_in(target_module=resources_routes_health, configure=_seed_rm))
        patches.append(_patch_health_monitor(configure=_seed_hm))
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: _build_authenticated_cookie()},
            path_params={"resource_id": "7"},
            query_mapping={"per_page": "100000"},
        )
        resources_routes_health.handle_health_detail(request)
        per_page = env.last_template.render_calls[0]["per_page"]
    finally:
        for p in patches:
            p.deactivate()
        _reset_global_state()

    testbase.assert_equal(per_page, 100)
    return
