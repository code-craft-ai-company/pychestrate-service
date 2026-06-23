"""
.. module:: test_p13h_resources_core_port_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the E1 slice of the resources blueprint
               port (dashboard + 7 core /resources/* routes).

.. moduleauthor:: Code Craft AI LLC

PR E1 ports the dashboard + the seven core resources routes
(list, create, detail, edit, delete, checkout) of the legacy
flask resources blueprint to webworks.

Tests cover:

* ``register_resources_routes`` -- documented route attachment +
  E2/E3/E4 future-endpoint pre-registration.
* ``_require_permission_or_redirect`` (new helper in routes.py)
  -- allowed / denied / SecurityManager-raises paths.
* dashboard -- happy path with summary statistics.
* resource_list -- pagination + filter passthrough.
* resource_create -- GET form, POST happy + admin-denied +
  CSRF-mismatch + ValueError + manager-error paths.
* resource_detail -- happy + 404 + unparsable id.
* resource_edit -- POST happy + admin-denied + 404.
* resource_delete -- happy + admin-denied + manager-error.
* resource_checkout -- happy + manager-error.
* _parse_metadata_json_or_default + _summarize_health_counts
  helpers.

All ResourceManager / AllocationManager / IPPoolManager /
SecurityManager interactions are patched at the routes-module
bindings so the test suite never imports the source manager
modules.
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
# Fakes (shape mirrors the D2/D3/D4 fixtures)
# ---------------------------------------------------------------------------


class _FakeQueryParams:
    def __init__(
            self, *,
            mapping: Optional[Dict[str, str]] = None,
            multi_mapping: Optional[Dict[str, List[str]]] = None
        ) -> None:
        self._mapping: Dict[str, str] = mapping if mapping is not None else {}
        self._multi: Dict[str, List[str]] = (
            multi_mapping if multi_mapping is not None else {}
        )
        return

    def get(
            self, key: str, default: Optional[str] = None
        ) -> Optional[str]:
        rtnval = self._mapping.get(key, default)
        return rtnval

    def getlist(self, key: str) -> List[str]:
        rtnval = list(self._multi.get(key, []))
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
        query_multi_mapping: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self.method: str = method
        self.cookies: Dict[str, str] = cookies if cookies is not None else {}
        self.body: bytes = body
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(
            mapping=query_mapping, multi_mapping=query_multi_mapping
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
    """
        Stand-in covering both validate_token (used by
        ``_resolve_authenticated_request``) AND check_permission
        (used by ``_require_permission_or_redirect``). Each test
        seeds whichever it cares about.
    """

    last_instance: Optional["_FakeSecurityManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.validate_token_response: Optional[_FakeSessionInfo] = None
        self.check_permission_response: bool = True
        self.check_permission_raises: Optional[Exception] = None
        self.check_permission_calls: List[Any] = []
        _FakeSecurityManager.last_instance = self
        return

    def validate_token(self, token: str) -> Optional[_FakeSessionInfo]:
        return self.validate_token_response

    def check_permission(self, user_id: str, permission: str) -> bool:
        self.check_permission_calls.append((user_id, permission))
        if self.check_permission_raises is not None:
            raise self.check_permission_raises
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


# ---- Resource-domain fakes ------------------------------------------------


class _FakeHealthStatus:
    def __init__(self, *, value: str) -> None:
        self.value: str = value
        return


class _FakeResource:
    def __init__(
            self, *, resource_id: int, name: str,
            health_status_value: str = "online",
            description: str = "",
            tags: Optional[List[str]] = None
        ) -> None:
        self.id: int = resource_id
        self.name: str = name
        self.health_status: _FakeHealthStatus = _FakeHealthStatus(
            value=health_status_value
        )
        self.description: str = description
        self.tags: List[str] = tags if tags is not None else []
        return


class _FakePool:
    def __init__(self, *, pool_id: int, name: str) -> None:
        self.id: int = pool_id
        self.name: str = name
        return


class _FakeAllocation:
    def __init__(self, *, allocation_id: int) -> None:
        self.id: int = allocation_id
        return


class _FakeResourceManager:
    last_instance: Optional["_FakeResourceManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_resources_response: List[_FakeResource] = []
        self.list_pools_response: List[_FakePool] = []
        self.list_tags_response: List[Any] = []
        self.get_resource_response: Optional[_FakeResource] = None
        self.create_resource_response: Optional[_FakeResource] = None
        self.list_resources_calls: List[Dict[str, Any]] = []
        self.create_resource_calls: List[Any] = []
        self.update_resource_calls: List[Any] = []
        self.delete_resource_calls: List[Any] = []
        self.create_resource_raises: Optional[Exception] = None
        self.update_resource_raises: Optional[Exception] = None
        self.delete_resource_raises: Optional[Exception] = None
        _FakeResourceManager.last_instance = self
        return

    def list_resources(self, **kwargs: Any) -> Any:
        # Mirrors ``ResourceListResponse(resources=..., total=...)``.
        # Handlers extract the list via ``.resources``; tests can
        # still set ``list_resources_response`` to a bare list.
        from types import SimpleNamespace
        self.list_resources_calls.append(kwargs)
        return SimpleNamespace(
            resources=self.list_resources_response,
            total=len(self.list_resources_response),
            offset=0,
            limit=len(self.list_resources_response),
        )

    def list_pools(self, user_id: str) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            pools=self.list_pools_response,
            total=len(self.list_pools_response),
            offset=0,
            limit=len(self.list_pools_response),
        )

    def list_tags(self) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            tags=self.list_tags_response,
            total=len(self.list_tags_response),
            offset=0,
            limit=len(self.list_tags_response),
        )

    def get_resource(self, resource_id: int) -> Optional[_FakeResource]:
        return self.get_resource_response

    def create_resource(
            self, request: Any, user_id: str
        ) -> _FakeResource:
        self.create_resource_calls.append((request, user_id))
        if self.create_resource_raises is not None:
            raise self.create_resource_raises
        if self.create_resource_response is None:
            return _FakeResource(resource_id=99, name=request.name)
        return self.create_resource_response

    def update_resource(
            self, resource_id: int, request: Any, user_id: str
        ) -> None:
        self.update_resource_calls.append(
            (resource_id, request, user_id)
        )
        if self.update_resource_raises is not None:
            raise self.update_resource_raises
        return

    def delete_resource(
            self, resource_id: int, user_id: str
        ) -> None:
        self.delete_resource_calls.append((resource_id, user_id))
        if self.delete_resource_raises is not None:
            raise self.delete_resource_raises
        return


class _FakeAllocationManager:
    last_instance: Optional["_FakeAllocationManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_allocations_response: List[Any] = []
        self.get_active_allocations_response: List[Any] = []
        self.checkout_response: Optional[_FakeAllocation] = None
        self.checkout_calls: List[Any] = []
        self.checkout_raises: Optional[Exception] = None
        _FakeAllocationManager.last_instance = self
        return

    def list_allocations(self, *, status: str) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            allocations=self.list_allocations_response,
            total=len(self.list_allocations_response),
            offset=0,
            limit=len(self.list_allocations_response),
        )

    def get_active_allocations(self, resource_id: int) -> List[Any]:
        return self.get_active_allocations_response

    def checkout(self, request: Any, user_id: str) -> _FakeAllocation:
        self.checkout_calls.append((request, user_id))
        if self.checkout_raises is not None:
            raise self.checkout_raises
        if self.checkout_response is None:
            return _FakeAllocation(allocation_id=11)
        return self.checkout_response


class _FakeIPPoolManager:
    last_instance: Optional["_FakeIPPoolManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_pools_response: List[Any] = []
        _FakeIPPoolManager.last_instance = self
        return

    def list_pools(self, user_id: str) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            pools=self.list_pools_response,
            total=len(self.list_pools_response),
            offset=0,
            limit=len(self.list_pools_response),
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
    _FakeResourceManager.last_instance = None
    _FakeAllocationManager.last_instance = None
    _FakeIPPoolManager.last_instance = None
    return


def _patch_security_manager(
        *,
        check_permission_response: bool = True,
        check_permission_raises: Optional[Exception] = None
    ) -> Any:
    info = _FakeSessionInfo(
        user_id="u-admin", username="admin", csrf_token="csrf-fresh"
    )

    def _builder(*, db_session: Any) -> _FakeSecurityManager:
        instance = _FakeSecurityManager(db_session)
        instance.validate_token_response = info
        instance.check_permission_response = check_permission_response
        instance.check_permission_raises = check_permission_raises
        return instance

    patch = create_module_patch(config_routes, "_build_security_manager")
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_resource_manager(
        *,
        configure: Optional[Callable[[_FakeResourceManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeResourceManager:
        instance = _FakeResourceManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        resources_routes, "_build_resource_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_allocation_manager(
        *,
        configure: Optional[Callable[[_FakeAllocationManager], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeAllocationManager:
        instance = _FakeAllocationManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        resources_routes, "_build_allocation_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_ip_pool_manager() -> Any:
    def _builder(*, db_session: Any) -> _FakeIPPoolManager:
        return _FakeIPPoolManager(db_session)

    patch = create_module_patch(
        resources_routes, "_build_ip_pool_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_resource_type_resolver() -> Any:
    def _resolve(*, resource_type_str: str) -> Any:
        return type("RT", (), {"value": resource_type_str})()

    patch = create_module_patch(
        resources_routes, "_resolve_resource_type"
    )
    mock = patch.activate()
    mock.configure(side_effect=_resolve)
    return patch


def _patch_resource_create_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        resources_routes, "_build_resource_create_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_resource_update_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        resources_routes, "_build_resource_update_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_checkout_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        resources_routes, "_build_checkout_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_allocation_mode_resolver() -> Any:
    def _resolve(*, mode_str: str) -> Any:
        return type("AM", (), {"value": mode_str})()

    patch = create_module_patch(
        resources_routes, "_resolve_allocation_mode"
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
        Run register_resources_routes against a throwaway app
        so url_for can resolve resources.* endpoints + the
        E2/E3/E4 future patterns. Also registers config endpoints
        because the dashboard sidebar uses ``url_for('config.*')``
        helpers and the auth resolver redirects to /login
        on anonymous access.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
        register_config_routes,
    )
    app = _FakeApp()
    register_config_routes(app=app)
    return


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_resources_routes_attaches_documented_routes():
    """
    **Feature: webworks resources port T5.1 (E1)**
    **Property: register_resources_routes attaches the eight
    documented E1 routes (dashboard root + /dashboard, /list,
    /create GET+POST, /<id>, /<id>/edit GET+POST, /<id>/delete,
    /<id>/checkout) at /resources/*. Asserted as a subset so
    the E2/E3/E4 per-feature route attachments dispatched from
    the same registrar do not break this contract.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected_subset = {
            ("/resources", ("GET",)),
            ("/resources/dashboard", ("GET",)),
            ("/resources/list", ("GET",)),
            ("/resources/create", ("GET", "POST")),
            ("/resources/{resource_id}", ("GET",)),
            ("/resources/{resource_id}/edit", ("GET", "POST")),
            ("/resources/{resource_id}/delete", ("POST",)),
            ("/resources/{resource_id}/checkout", ("POST",)),
        }
        missing = expected_subset - actual
        testbase.assert_equal(missing, set())
    finally:
        _reset_global_state()
    return


def test_register_resources_routes_pre_registers_future_endpoints():
    """
    **Feature: webworks resources port T5.1 (E1)**
    **Property: register_resources_routes pre-registers the
    E2/E3/E4 endpoint patterns so the dashboard sidebar's
    url_for('resources.pool_list') / ip_pool_list /
    allocation_list / reservation_list / health_dashboard /
    tag_list calls resolve before those handlers ship.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        snapshot = url_for_module.get_registry_snapshot()
        for endpoint in (
            "resources.pool_list",
            "resources.ip_pool_list",
            "resources.allocation_list",
            "resources.allocation_history",
            "resources.reservation_list",
            "resources.health_dashboard",
            "resources.tag_list",
        ):
            testbase.assert_equal(endpoint in snapshot, True)
        testbase.assert_equal(
            snapshot["resources.pool_detail"],
            "/resources/pools/{pool_id}",
        )
    finally:
        _reset_global_state()
    return


# ===========================================================================
# _require_permission_or_redirect (config/routes.py helper)
# ===========================================================================


def test_require_permission_or_redirect_returns_none_when_allowed():
    """
    **Feature: D2/E1 helpers T5.2**
    **Property: When SecurityManager.check_permission returns
    True, the helper returns None and the handler proceeds.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        sm_patch = _patch_security_manager(
            check_permission_response=True
        )
        db_session = _FakeDbSession()
        auth = config_routes._AuthResolution(
            redirect_response=None,
            session={},
            db_session=db_session,
            user_id="u-admin",
            username="admin",
            csrf_token="csrf",
        )
        result = config_routes._require_permission_or_redirect(
            auth=auth,
            permission="resources.manage",
            deny_redirect_url="/resources",
        )
        testbase.assert_equal(result, None)
        sm = _FakeSecurityManager.last_instance
        testbase.assert_equal(
            sm.check_permission_calls,
            [("u-admin", "resources.manage")],
        )
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_require_permission_or_redirect_redirects_when_denied():
    """
    **Feature: D2/E1 helpers T5.2**
    **Property: When check_permission returns False, the helper
    returns a 302 redirect to the deny URL with an error flash
    queued on the session cookie.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        sm_patch = _patch_security_manager(
            check_permission_response=False
        )
        _install_ui_cookie_secret()
        db_session = _FakeDbSession()
        auth = config_routes._AuthResolution(
            redirect_response=None,
            session={},
            db_session=db_session,
            user_id="u-viewer",
            username="viewer",
            csrf_token="csrf",
        )
        result = config_routes._require_permission_or_redirect(
            auth=auth,
            permission="resources.manage",
            deny_redirect_url="/resources",
        )
        is_redirect = isinstance(result, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(result.status_code, 302)
        testbase.assert_equal(result.headers["Location"], "/resources")
        # An error flash was queued.
        queue = auth.session[flash.SESSION_KEY]
        testbase.assert_equal(len(queue), 1)
        testbase.assert_equal(queue[0][0], "error")
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_require_permission_or_redirect_treats_exception_as_denial():
    """
    **Feature: D2/E1 helpers T5.2**
    **Property: An exception from check_permission is treated as
    denial -- the helper redirects rather than letting the
    handler proceed on a fail-open path.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        sm_patch = _patch_security_manager(
            check_permission_raises=RuntimeError("DB exploded")
        )
        _install_ui_cookie_secret()
        auth = config_routes._AuthResolution(
            redirect_response=None,
            session={},
            db_session=_FakeDbSession(),
            user_id="u-admin",
            username="admin",
            csrf_token="csrf",
        )
        result = config_routes._require_permission_or_redirect(
            auth=auth,
            permission="resources.manage",
            deny_redirect_url="/resources",
        )
        is_redirect = isinstance(result, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Helpers (no-DB, no-auth)
# ===========================================================================


def test_parse_metadata_json_or_default_handles_empty_and_valid():
    """
    **Feature: E1 helpers T5.3**
    **Property: Empty input returns the default; valid JSON
    object parses; non-JSON / non-object input raises ValueError.**
    """
    testbase.assert_equal(
        resources_routes._parse_metadata_json_or_default(
            raw="", default={}
        ),
        {},
    )
    testbase.assert_equal(
        resources_routes._parse_metadata_json_or_default(
            raw='{"hostname": "fooboard"}', default={}
        ),
        {"hostname": "fooboard"},
    )
    raised = False
    try:
        resources_routes._parse_metadata_json_or_default(
            raw="not json", default={}
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)

    # JSON arrays / non-object types are also rejected -- the
    # manager expects a dict.
    raised = False
    try:
        resources_routes._parse_metadata_json_or_default(
            raw="[1, 2, 3]", default={}
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_summarize_health_counts_buckets_by_status_value():
    """
    **Feature: E1 helpers T5.4**
    **Property: Resources are bucketed into the four documented
    health-status keys; missing / unknown statuses contribute
    nothing; empty input yields all-zero buckets.**
    """
    resources = [
        _FakeResource(resource_id=1, name="r1", health_status_value="online"),
        _FakeResource(resource_id=2, name="r2", health_status_value="online"),
        _FakeResource(
            resource_id=3, name="r3", health_status_value="degraded"
        ),
        _FakeResource(
            resource_id=4, name="r4", health_status_value="maintenance"
        ),
        _FakeResource(
            resource_id=5, name="r5", health_status_value="unknown"
        ),
    ]
    counts = resources_routes._summarize_health_counts(resources=resources)
    testbase.assert_equal(counts["online"], 2)
    testbase.assert_equal(counts["degraded"], 1)
    testbase.assert_equal(counts["maintenance"], 1)
    testbase.assert_equal(counts["offline"], 0)

    counts = resources_routes._summarize_health_counts(resources=[])
    testbase.assert_equal(
        counts,
        {"online": 0, "offline": 0, "degraded": 0, "maintenance": 0},
    )
    return


# ===========================================================================
# Dashboard
# ===========================================================================


def test_handle_dashboard_renders_with_summary_statistics():
    """
    **Feature: webworks resources port T5.5 (E1)**
    **Property: GET /resources/ renders resources/dashboard.html
    with resource_count / pool_count / ip_pool_count /
    active_allocation_count / health_counts derived from the
    manager outputs.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    am_patch = None
    ipm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed_rm(instance: _FakeResourceManager) -> None:
            instance.list_resources_response = [
                _FakeResource(resource_id=1, name="r1"),
                _FakeResource(
                    resource_id=2, name="r2",
                    health_status_value="degraded",
                ),
            ]
            instance.list_pools_response = [
                _FakePool(pool_id=1, name="p1")
            ]
            return

        rm_patch = _patch_resource_manager(configure=_seed_rm)

        def _seed_am(instance: _FakeAllocationManager) -> None:
            instance.list_allocations_response = [
                _FakeAllocation(allocation_id=11),
                _FakeAllocation(allocation_id=12),
                _FakeAllocation(allocation_id=13),
            ]
            return

        am_patch = _patch_allocation_manager(configure=_seed_am)
        ipm_patch = _patch_ip_pool_manager()
        # Need to also register resources_routes so url_for works.
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = resources_routes.handle_dashboard(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["resources/dashboard.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["resource_count"], 2)
        testbase.assert_equal(ctx["pool_count"], 1)
        testbase.assert_equal(ctx["ip_pool_count"], 0)
        testbase.assert_equal(ctx["active_allocation_count"], 3)
        testbase.assert_equal(ctx["health_counts"]["online"], 1)
        testbase.assert_equal(ctx["health_counts"]["degraded"], 1)
    finally:
        for p in (ipm_patch, am_patch, rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_dashboard_redirects_anonymous_to_config_login():
    """
    **Feature: webworks resources port T5.5 (E1)**
    **Property: An unauthenticated request to /resources/
    redirects to /login (the shared login URL the auth
    resolver builds).**
    """
    _reset_global_state()
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _register_url_for_endpoints()
        request = _FakeRequest(cookies={})
        response = resources_routes.handle_dashboard(request)
        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/login"
        )
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Resource list
# ===========================================================================


def test_handle_resource_list_passes_filters_through_to_manager():
    """
    **Feature: webworks resources port T5.6 (E1)**
    **Property: GET /resources/list with ?pool_id=2 &
    ?resource_type=device & ?health_status=online & ?tags=t1 &
    ?tags=t2 calls list_resources with all those kwargs +
    offset/limit. Renders the list template with the manager's
    output + the selected_* + search context vars.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    rt_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()
        rm_patch = _patch_resource_manager()
        rt_patch = _patch_resource_type_resolver()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            query_mapping={
                "page": "1", "per_page": "20",
                "pool_id": "2", "resource_type": "device",
                "health_status": "online", "search": "boardA",
            },
            query_multi_mapping={"tags": ["t1", "t2"]},
        )
        response = resources_routes.handle_resource_list(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["resources/resources/list.html"]
        )
        rm = _FakeResourceManager.last_instance
        testbase.assert_equal(len(rm.list_resources_calls), 1)
        kwargs = rm.list_resources_calls[0]
        testbase.assert_equal(kwargs["offset"], 0)
        testbase.assert_equal(kwargs["limit"], 20)
        testbase.assert_equal(kwargs["pool_id"], 2)
        testbase.assert_equal(kwargs["tags"], ["t1", "t2"])
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["selected_pool_id"], 2)
        testbase.assert_equal(ctx["selected_resource_type"], "device")
        testbase.assert_equal(ctx["search"], "boardA")
        testbase.assert_equal(ctx["selected_tags"], ["t1", "t2"])
    finally:
        for p in (rt_patch, rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Resource create
# ===========================================================================


def test_handle_resource_create_get_renders_form_with_pools_and_tags():
    """
    **Feature: webworks resources port T5.7 (E1)**
    **Property: GET /resources/create renders the create
    template with pools + all_tags + form_data=None.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeResourceManager) -> None:
            instance.list_pools_response = [
                _FakePool(pool_id=1, name="default-pool")
            ]
            instance.list_tags_response = ["alpha", "beta"]
            return

        rm_patch = _patch_resource_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = resources_routes.handle_resource_create(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups,
            ["resources/resources/create.html"],
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["pools"]), 1)
        testbase.assert_equal(ctx["all_tags"], ["alpha", "beta"])
        testbase.assert_equal(ctx["form_data"], None)
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_resource_create_redirects_when_user_lacks_admin():
    """
    **Feature: webworks resources port T5.7 (E1)**
    **Property: A user without ``resources.manage`` permission
    is redirected to /resources/dashboard with an error flash
    rather than seeing the create form.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager(
            check_permission_response=False
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = resources_routes.handle_resource_create(request)

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


def test_handle_resource_create_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks resources port T5.7 (E1)**
    **Property: A valid POST creates the resource and redirects
    to /resources/{new_id} with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    rt_patch = None
    cr_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeResourceManager) -> None:
            instance.create_resource_response = _FakeResource(
                resource_id=42, name="newbox"
            )
            return

        rm_patch = _patch_resource_manager(configure=_seed)
        rt_patch = _patch_resource_type_resolver()
        cr_patch = _patch_resource_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=newbox&resource_type=device"
            b"&pool_id=2&description=A+new+device&capacity=1"
            b"&metadata=%7B%22ip%22%3A%20%22127.0.0.1%22%7D"
            b"&tags=alpha&tags=beta"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = resources_routes.handle_resource_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/42"
        )
        rm = _FakeResourceManager.last_instance
        testbase.assert_equal(len(rm.create_resource_calls), 1)
        ar, user_id = rm.create_resource_calls[0]
        testbase.assert_equal(ar.name, "newbox")
        testbase.assert_equal(ar.pool_id, 2)
        testbase.assert_equal(ar.tags, ["alpha", "beta"])
        testbase.assert_equal(ar.metadata, {"ip": "127.0.0.1"})
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (cr_patch, rt_patch, rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_resource_create_post_invalid_metadata_json_re_renders():
    """
    **Feature: webworks resources port T5.7 (E1)**
    **Property: A POST with a non-JSON metadata field
    re-renders the form (400) with an error flash and does NOT
    invoke create_resource.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    rt_patch = None
    cr_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()
        rm_patch = _patch_resource_manager()
        rt_patch = _patch_resource_type_resolver()
        cr_patch = _patch_resource_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=x&resource_type=device"
            b"&metadata=not-valid-json"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = resources_routes.handle_resource_create(request)

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        category, message = ctx["flashes"][0]
        testbase.assert_equal(category, "error")
        contains = "Invalid JSON" in message
        testbase.assert_equal(contains, True)
        rm = _FakeResourceManager.last_instance
        testbase.assert_equal(rm.create_resource_calls, [])
    finally:
        for p in (cr_patch, rt_patch, rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_resource_create_post_csrf_mismatch_redirects():
    """
    **Feature: webworks resources port T5.7 (E1)**
    **Property: A POST with a missing / mismatched csrf_token
    bounces back to /resources/create without invoking the
    ResourceManager.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()
        rm_patch = _patch_resource_manager()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=wrong-token&name=x&resource_type=device"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = resources_routes.handle_resource_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        rm = _FakeResourceManager.last_instance
        testbase.assert_equal(rm.create_resource_calls, [])
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Resource detail
# ===========================================================================


def test_handle_resource_detail_renders_when_resource_found():
    """
    **Feature: webworks resources port T5.8 (E1)**
    **Property: GET /resources/{id} renders the detail template
    with the resource + active_allocations from the
    AllocationManager.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    am_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()
        resource = _FakeResource(resource_id=42, name="boardA")

        def _seed_rm(instance: _FakeResourceManager) -> None:
            instance.get_resource_response = resource
            return

        rm_patch = _patch_resource_manager(configure=_seed_rm)

        def _seed_am(instance: _FakeAllocationManager) -> None:
            instance.get_active_allocations_response = [
                _FakeAllocation(allocation_id=99)
            ]
            return

        am_patch = _patch_allocation_manager(configure=_seed_am)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"resource_id": "42"},
        )
        response = resources_routes.handle_resource_detail(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["resource"], resource)
        testbase.assert_equal(len(ctx["active_allocations"]), 1)
    finally:
        for p in (am_patch, rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_resource_detail_redirects_when_unparsable_id():
    """
    **Feature: webworks resources port T5.8 (E1)**
    **Property: A non-int resource_id path param yields a
    redirect to /resources/list with an error flash without
    constructing the manager.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()
        rm_patch = _patch_resource_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"resource_id": "not-an-int"},
        )
        response = resources_routes.handle_resource_detail(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/list"
        )
        testbase.assert_equal(_FakeResourceManager.last_instance, None)
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_resource_detail_redirects_when_missing():
    """
    **Feature: webworks resources port T5.8 (E1)**
    **Property: get_resource returning None yields a redirect
    to /resources/list with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()
        rm_patch = _patch_resource_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"resource_id": "999"},
        )
        response = resources_routes.handle_resource_detail(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/list"
        )
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Resource edit
# ===========================================================================


def test_handle_resource_edit_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks resources port T5.9 (E1)**
    **Property: A valid edit POST calls update_resource and
    redirects to /resources/{id} with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    upd_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeResourceManager) -> None:
            instance.get_resource_response = _FakeResource(
                resource_id=7, name="boardA"
            )
            return

        rm_patch = _patch_resource_manager(configure=_seed)
        upd_patch = _patch_resource_update_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&description=Updated&capacity=4"
            b"&tags=alpha"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"resource_id": "7"},
        )
        response = resources_routes.handle_resource_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/7"
        )
        rm = _FakeResourceManager.last_instance
        testbase.assert_equal(len(rm.update_resource_calls), 1)
        target_id, ar, user_id = rm.update_resource_calls[0]
        testbase.assert_equal(target_id, 7)
        testbase.assert_equal(ar.description, "Updated")
        testbase.assert_equal(ar.capacity, 4)
        testbase.assert_equal(ar.tags, ["alpha"])
    finally:
        for p in (upd_patch, rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_resource_edit_redirects_when_user_lacks_admin():
    """
    **Feature: webworks resources port T5.9 (E1)**
    **Property: A non-admin user cannot reach the edit form;
    they're redirected to /resources/dashboard.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager(
            check_permission_response=False
        )

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"resource_id": "7"},
        )
        response = resources_routes.handle_resource_edit(request)

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


# ===========================================================================
# Resource delete
# ===========================================================================


def test_handle_resource_delete_happy_path_redirects_to_list():
    """
    **Feature: webworks resources port T5.10 (E1)**
    **Property: A valid POST calls delete_resource and
    redirects to /resources/list with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()
        rm_patch = _patch_resource_manager()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"resource_id": "9"},
        )
        response = resources_routes.handle_resource_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/list"
        )
        rm = _FakeResourceManager.last_instance
        testbase.assert_equal(
            rm.delete_resource_calls, [(9, "u-admin")]
        )
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_resource_delete_manager_error_flashes_error():
    """
    **Feature: webworks resources port T5.10 (E1)**
    **Property: delete_resource raising yields a 303 redirect
    to /resources/list with an error-category flash.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeResourceManager) -> None:
            instance.delete_resource_raises = RuntimeError(
                "resource has active allocations"
            )
            return

        rm_patch = _patch_resource_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"resource_id": "9"},
        )
        response = resources_routes.handle_resource_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Resource checkout
# ===========================================================================


def test_handle_resource_checkout_happy_path_redirects_to_detail():
    """
    **Feature: webworks resources port T5.11 (E1)**
    **Property: A valid POST calls allocation_manager.checkout
    with the parsed CheckoutRequest and redirects to
    /resources/{id} with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    cr_patch = None
    mode_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeAllocationManager) -> None:
            instance.checkout_response = _FakeAllocation(allocation_id=55)
            return

        am_patch = _patch_allocation_manager(configure=_seed)
        cr_patch = _patch_checkout_request_factory()
        mode_patch = _patch_allocation_mode_resolver()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&job_id=job-123"
            b"&mode=exclusive&timeout_minutes=30"
            b"&reason=running+test+suite"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"resource_id": "7"},
        )
        response = resources_routes.handle_resource_checkout(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/7"
        )
        am = _FakeAllocationManager.last_instance
        testbase.assert_equal(len(am.checkout_calls), 1)
        ar, user_id = am.checkout_calls[0]
        testbase.assert_equal(ar.resource_id, 7)
        testbase.assert_equal(ar.job_id, "job-123")
        testbase.assert_equal(ar.timeout_minutes, 30)
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (mode_patch, cr_patch, am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_resource_checkout_manager_error_flashes_error():
    """
    **Feature: webworks resources port T5.11 (E1)**
    **Property: checkout raising yields a 303 redirect to
    /resources/{id} with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    am_patch = None
    cr_patch = None
    mode_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        app = _FakeApp()
        resources_routes.register_resources_routes(app=app)
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeAllocationManager) -> None:
            instance.checkout_raises = RuntimeError(
                "resource is already checked out"
            )
            return

        am_patch = _patch_allocation_manager(configure=_seed)
        cr_patch = _patch_checkout_request_factory()
        mode_patch = _patch_allocation_mode_resolver()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&mode=exclusive"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"resource_id": "7"},
        )
        response = resources_routes.handle_resource_checkout(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/7"
        )
    finally:
        for p in (mode_patch, cr_patch, am_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return
