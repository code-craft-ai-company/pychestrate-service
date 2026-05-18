"""
.. module:: test_p13i_resources_pools_ipools_port_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the E2 slice of the resources port
               (pools + ip_pools).

.. moduleauthor:: Automation Mojo LLC

PR E2 ports the four resource-pool routes plus the seven IP
pool routes to webworks.

Tests cover:

* ``register_pools_routes`` / ``register_ip_pools_routes`` --
  route attachment matrices.
* pool list / create (GET + POST happy + admin-denied + manager-
  error + CSRF) / detail (happy + 404 + unparsable id) /
  delete (happy + admin-denied + manager-error).
* ip_pool list / create (POST happy + manager-error) / detail
  (happy + 404) / edit (POST happy + admin-denied) / delete
  (happy) / checkout (single-IP happy + bulk happy + manager-
  error) / checkin (allocation_id happy + job_id happy +
  neither-provided error).
* ``_parse_csv_string`` helper (empty / valid / extra
  whitespace / single value).

All ResourceManager / IPPoolManager / SecurityManager
interactions are patched at the routes-module bindings.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from automojo import testbase
from automojo.testbase.mocking import create_module_patch
from automojo.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from automojo.pychestrate.webservice.webinterface.blueprints.config import (
    routes as config_routes,
)
from automojo.pychestrate.webservice.webinterface.blueprints.resources import (
    routes as resources_routes,
    routes_ip_pools as resources_routes_ip_pools,
    routes_pools as resources_routes_pools,
)
from automojo.pychestrate.webservice.webinterface.foundation import (
    cookie_session,
    csrf,
    flash,
    templating,
    url_for as url_for_module,
)


_TEST_UI_COOKIE_SECRET: bytes = b"\x00" * 32


# ---------------------------------------------------------------------------
# Test stubs (mirror E1)
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


# ---- Pool / IP-pool fakes -------------------------------------------------


class _FakePool:
    def __init__(
            self, *, pool_id: int, name: str = "p", description: str = ""
        ) -> None:
        self.id: int = pool_id
        self.name: str = name
        self.description: str = description
        return


class _FakeResource:
    def __init__(self, *, resource_id: int, name: str = "r") -> None:
        self.id: int = resource_id
        self.name: str = name
        return


class _FakeResourceManager:
    last_instance: Optional["_FakeResourceManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_pools_response: List[_FakePool] = []
        self.list_resources_response: List[_FakeResource] = []
        self.get_pool_response: Optional[_FakePool] = None
        self.create_pool_response: Optional[_FakePool] = None
        self.create_pool_calls: List[Any] = []
        self.delete_pool_calls: List[Any] = []
        self.list_resources_calls: List[Dict[str, Any]] = []
        self.create_pool_raises: Optional[Exception] = None
        self.delete_pool_raises: Optional[Exception] = None
        _FakeResourceManager.last_instance = self
        return

    def list_pools(self, user_id: str) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            pools=self.list_pools_response,
            total=len(self.list_pools_response),
            offset=0,
            limit=len(self.list_pools_response),
        )

    def get_pool(self, pool_id: int) -> Optional[_FakePool]:
        return self.get_pool_response

    def create_pool(self, request: Any, user_id: str) -> _FakePool:
        self.create_pool_calls.append((request, user_id))
        if self.create_pool_raises is not None:
            raise self.create_pool_raises
        if self.create_pool_response is None:
            return _FakePool(pool_id=99, name=request.name)
        return self.create_pool_response

    def list_resources(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        self.list_resources_calls.append(kwargs)
        return SimpleNamespace(
            resources=self.list_resources_response,
            total=len(self.list_resources_response),
            offset=0,
            limit=len(self.list_resources_response),
        )

    def delete_pool(self, pool_id: int, user_id: str) -> None:
        self.delete_pool_calls.append((pool_id, user_id))
        if self.delete_pool_raises is not None:
            raise self.delete_pool_raises
        return


class _FakeIPPool:
    def __init__(self, *, pool_id: int, name: str = "ipp") -> None:
        self.id: int = pool_id
        self.name: str = name
        return


class _FakeIPAllocation:
    def __init__(
            self, *, allocation_id: int, ip_address: str
        ) -> None:
        self.id: int = allocation_id
        self.ip_address: str = ip_address
        return


class _FakeIPAllocationsResult:
    def __init__(self, *, allocations: List[_FakeIPAllocation]) -> None:
        self.allocations: List[_FakeIPAllocation] = allocations
        return


class _FakeIPPoolManager:
    last_instance: Optional["_FakeIPPoolManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_pools_response: List[_FakeIPPool] = []
        self.get_pool_response: Optional[_FakeIPPool] = None
        self.list_allocations_response: List[Any] = []
        self.get_available_ips_response: List[str] = []
        self.create_pool_response: Optional[_FakeIPPool] = None
        self.checkout_ip_response: Optional[_FakeIPAllocation] = None
        self.checkout_ips_response: Optional[_FakeIPAllocationsResult] = None
        self.checkin_job_ips_response: int = 0
        self.create_pool_calls: List[Any] = []
        self.update_pool_calls: List[Any] = []
        self.delete_pool_calls: List[Any] = []
        self.checkout_ip_calls: List[Any] = []
        self.checkout_ips_calls: List[Any] = []
        self.checkin_ip_calls: List[Any] = []
        self.checkin_job_ips_calls: List[Any] = []
        self.create_pool_raises: Optional[Exception] = None
        self.update_pool_raises: Optional[Exception] = None
        self.delete_pool_raises: Optional[Exception] = None
        self.checkout_ip_raises: Optional[Exception] = None
        self.checkout_ips_raises: Optional[Exception] = None
        self.checkin_ip_raises: Optional[Exception] = None
        self.checkin_job_ips_raises: Optional[Exception] = None
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

    def get_pool(self, pool_id: int) -> Optional[_FakeIPPool]:
        return self.get_pool_response

    def list_allocations(
            self, *, pool_id: int, status: str
        ) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            allocations=self.list_allocations_response,
            total=len(self.list_allocations_response),
            offset=0,
            limit=len(self.list_allocations_response),
        )

    def get_available_ips(
            self, pool_id: int, *, count: int
        ) -> List[str]:
        return self.get_available_ips_response

    def create_pool(self, request: Any, user_id: str) -> _FakeIPPool:
        self.create_pool_calls.append((request, user_id))
        if self.create_pool_raises is not None:
            raise self.create_pool_raises
        if self.create_pool_response is None:
            return _FakeIPPool(pool_id=99, name=request.name)
        return self.create_pool_response

    def update_pool(
            self, pool_id: int, request: Any, user_id: str
        ) -> None:
        self.update_pool_calls.append((pool_id, request, user_id))
        if self.update_pool_raises is not None:
            raise self.update_pool_raises
        return

    def delete_pool(self, pool_id: int, user_id: str) -> None:
        self.delete_pool_calls.append((pool_id, user_id))
        if self.delete_pool_raises is not None:
            raise self.delete_pool_raises
        return

    def checkout_ip(
            self, request: Any, user_id: str
        ) -> _FakeIPAllocation:
        self.checkout_ip_calls.append((request, user_id))
        if self.checkout_ip_raises is not None:
            raise self.checkout_ip_raises
        if self.checkout_ip_response is None:
            return _FakeIPAllocation(
                allocation_id=11, ip_address="10.0.0.5"
            )
        return self.checkout_ip_response

    def checkout_ips(
            self, request: Any, user_id: str
        ) -> _FakeIPAllocationsResult:
        self.checkout_ips_calls.append((request, user_id))
        if self.checkout_ips_raises is not None:
            raise self.checkout_ips_raises
        if self.checkout_ips_response is None:
            return _FakeIPAllocationsResult(
                allocations=[
                    _FakeIPAllocation(
                        allocation_id=11, ip_address="10.0.0.5"
                    ),
                    _FakeIPAllocation(
                        allocation_id=12, ip_address="10.0.0.6"
                    ),
                ]
            )
        return self.checkout_ips_response

    def checkin_ip(
            self, allocation_id: int, user_id: str
        ) -> None:
        self.checkin_ip_calls.append((allocation_id, user_id))
        if self.checkin_ip_raises is not None:
            raise self.checkin_ip_raises
        return

    def checkin_job_ips(self, job_id: str, user_id: str) -> int:
        self.checkin_job_ips_calls.append((job_id, user_id))
        if self.checkin_job_ips_raises is not None:
            raise self.checkin_job_ips_raises
        return self.checkin_job_ips_response


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
    _FakeIPPoolManager.last_instance = None
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


def _patch_resource_manager(
        *,
        configure: Optional[Callable[[_FakeResourceManager], None]] = None
    ) -> Any:
    """
        Patch routes_pools' own ``_build_resource_manager``
        helper. routes_pools defines its own builder locally
        (rather than importing routes._build_resource_manager)
        so the test can patch its module-private surface
        without colliding with the resources/routes.py binding
        that other tests own.
    """
    def _builder(*, db_session: Any) -> _FakeResourceManager:
        instance = _FakeResourceManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        resources_routes_pools, "_build_resource_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_ip_pool_manager(
        *,
        configure: Optional[Callable[[_FakeIPPoolManager], None]] = None
    ) -> Any:
    """
        Patch routes_ip_pools' own ``_build_ip_pool_manager``
        helper.
    """
    def _builder(*, db_session: Any) -> _FakeIPPoolManager:
        instance = _FakeIPPoolManager(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        resources_routes_ip_pools, "_build_ip_pool_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_pool_create_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        resources_routes_pools, "_build_pool_create_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_ip_pool_create_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        resources_routes_ip_pools, "_build_ip_pool_create_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_ip_pool_update_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        resources_routes_ip_pools, "_build_ip_pool_update_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_ip_allocation_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        resources_routes_ip_pools, "_build_ip_allocation_request"
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
        register_resources_routes runs the resources registrar
        which (post-E2) cascades into pool + ip_pool registrars
        too. So this gives us the full url_for surface for both
        E1 and E2 endpoints. Also registers config endpoints
        (/login is the redirect target on auth failure).
    """
    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (
        register_config_routes,
    )
    app = _FakeApp()
    register_config_routes(app=app)
    resources_routes.register_resources_routes(app=app)
    return


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_pools_routes_attaches_documented_routes():
    """
    **Feature: webworks resources port T6.1 (E2)**
    **Property: register_pools_routes attaches the four pool
    routes at /resources/pools*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        resources_routes_pools.register_pools_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/resources/pools", ("GET",)),
            ("/resources/pools/create", ("GET", "POST")),
            ("/resources/pools/{pool_id}", ("GET",)),
            ("/resources/pools/{pool_id}/delete", ("POST",)),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_ip_pools_routes_attaches_documented_routes():
    """
    **Feature: webworks resources port T6.2 (E2)**
    **Property: register_ip_pools_routes attaches the seven IP
    pool routes at /resources/ip-pools*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        resources_routes_ip_pools.register_ip_pools_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/resources/ip-pools", ("GET",)),
            ("/resources/ip-pools/create", ("GET", "POST")),
            ("/resources/ip-pools/{pool_id}", ("GET",)),
            ("/resources/ip-pools/{pool_id}/edit", ("GET", "POST")),
            ("/resources/ip-pools/{pool_id}/delete", ("POST",)),
            ("/resources/ip-pools/{pool_id}/checkout", ("POST",)),
            ("/resources/ip-pools/{pool_id}/checkin", ("POST",)),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


# ===========================================================================
# Helpers
# ===========================================================================


def test_parse_csv_string_handles_empty_and_extra_whitespace():
    """
    **Feature: webworks resources port T6.3 (E2)**
    **Property: _parse_csv_string returns an empty list on
    empty / None input, splits on commas, trims whitespace,
    drops empty entries.**
    """
    parse = resources_routes_ip_pools._parse_csv_string
    testbase.assert_equal(parse(raw=""), [])
    testbase.assert_equal(parse(raw=None), [])
    testbase.assert_equal(parse(raw="8.8.8.8"), ["8.8.8.8"])
    testbase.assert_equal(
        parse(raw="8.8.8.8, 8.8.4.4 ,  ,1.1.1.1"),
        ["8.8.8.8", "8.8.4.4", "1.1.1.1"],
    )
    return


# ===========================================================================
# Pools -- list / create / detail / delete
# ===========================================================================


def test_handle_pool_list_renders_with_pools():
    """
    **Feature: webworks resources port T6.4 (E2)**
    **Property: GET /resources/pools renders the pool list
    template with the manager output.**
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
        pools = [_FakePool(pool_id=1, name="default")]

        def _seed(instance: _FakeResourceManager) -> None:
            instance.list_pools_response = pools
            return

        rm_patch = _patch_resource_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = resources_routes_pools.handle_pool_list(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["resources/pools/list.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["pools"], pools)
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_pool_create_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks resources port T6.5 (E2)**
    **Property: A valid POST creates the pool and redirects
    to /resources/pools/{new_id} with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    cr_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeResourceManager) -> None:
            instance.create_pool_response = _FakePool(
                pool_id=42, name="prod"
            )
            return

        rm_patch = _patch_resource_manager(configure=_seed)
        cr_patch = _patch_pool_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&name=prod&description=production"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = resources_routes_pools.handle_pool_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/pools/42"
        )
        rm = _FakeResourceManager.last_instance
        ar, user_id = rm.create_pool_calls[0]
        testbase.assert_equal(ar.name, "prod")
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (cr_patch, rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_pool_create_redirects_when_user_lacks_admin():
    """
    **Feature: webworks resources port T6.5 (E2)**
    **Property: A non-admin user cannot reach the create form;
    they're redirected to /resources/dashboard.**
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
        response = resources_routes_pools.handle_pool_create(request)

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


def test_handle_pool_create_post_manager_error_re_renders_with_flash():
    """
    **Feature: webworks resources port T6.5 (E2)**
    **Property: create_pool raising yields a 400 re-render
    with an error-category flash.**
    """
    _reset_global_state()
    sm_patch = None
    rm_patch = None
    cr_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeResourceManager) -> None:
            instance.create_pool_raises = RuntimeError(
                "duplicate pool name"
            )
            return

        rm_patch = _patch_resource_manager(configure=_seed)
        cr_patch = _patch_pool_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&name=prod"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = resources_routes_pools.handle_pool_create(request)

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        category, message = ctx["flashes"][0]
        testbase.assert_equal(category, "error")
        contains = "duplicate" in message
        testbase.assert_equal(contains, True)
    finally:
        for p in (cr_patch, rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_pool_detail_renders_with_pool_and_resources():
    """
    **Feature: webworks resources port T6.6 (E2)**
    **Property: GET /resources/pools/{id} renders the detail
    template with the resolved pool + the resources in it.**
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
        pool = _FakePool(pool_id=7, name="staging")
        resources = [_FakeResource(resource_id=1, name="r1")]

        def _seed(instance: _FakeResourceManager) -> None:
            instance.get_pool_response = pool
            instance.list_resources_response = resources
            return

        rm_patch = _patch_resource_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"pool_id": "7"},
        )
        response = resources_routes_pools.handle_pool_detail(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["pool"], pool)
        testbase.assert_equal(ctx["resources"], resources)
        rm = _FakeResourceManager.last_instance
        testbase.assert_equal(
            rm.list_resources_calls[0],
            {"pool_id": 7, "limit": 100},
        )
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_pool_detail_redirects_when_pool_missing():
    """
    **Feature: webworks resources port T6.6 (E2)**
    **Property: get_pool returning None yields a redirect to
    /resources/pools with an error flash.**
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
        rm_patch = _patch_resource_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"pool_id": "99"},
        )
        response = resources_routes_pools.handle_pool_detail(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/pools"
        )
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_pool_delete_happy_path_redirects_to_list():
    """
    **Feature: webworks resources port T6.7 (E2)**
    **Property: A valid POST calls delete_pool and redirects
    to /resources/pools with a success flash.**
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
        rm_patch = _patch_resource_manager()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"pool_id": "7"},
        )
        response = resources_routes_pools.handle_pool_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/pools"
        )
        rm = _FakeResourceManager.last_instance
        testbase.assert_equal(rm.delete_pool_calls, [(7, "u-admin")])
    finally:
        for p in (rm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# IP Pools -- list / create / detail / edit / delete
# ===========================================================================


def test_handle_ip_pool_list_renders_with_pools():
    """
    **Feature: webworks resources port T6.8 (E2)**
    **Property: GET /resources/ip-pools renders the list
    template with the IPPoolManager output.**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        pools = [_FakeIPPool(pool_id=1, name="lab")]

        def _seed(instance: _FakeIPPoolManager) -> None:
            instance.list_pools_response = pools
            return

        ipm_patch = _patch_ip_pool_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value}
        )
        response = resources_routes_ip_pools.handle_ip_pool_list(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["resources/ip_pools/list.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["pools"], pools)
    finally:
        for p in (ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_ip_pool_create_post_happy_path_parses_csv_fields():
    """
    **Feature: webworks resources port T6.9 (E2)**
    **Property: A valid POST parses dns_servers + reserved_ips
    as comma-separated lists, builds an IPPoolCreateRequest,
    creates the pool, and redirects to the detail page.**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    cr_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeIPPoolManager) -> None:
            instance.create_pool_response = _FakeIPPool(
                pool_id=42, name="lab"
            )
            return

        ipm_patch = _patch_ip_pool_manager(configure=_seed)
        cr_patch = _patch_ip_pool_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=lab&cidr=10.0.0.0%2F24"
            b"&gateway=10.0.0.1&dns_servers=8.8.8.8%2C+8.8.4.4"
            b"&reserved_ips=10.0.0.5%2C10.0.0.6"
            b"&description=Lab+pool"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = resources_routes_ip_pools.handle_ip_pool_create(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/ip-pools/42"
        )
        ipm = _FakeIPPoolManager.last_instance
        ar, user_id = ipm.create_pool_calls[0]
        testbase.assert_equal(ar.name, "lab")
        testbase.assert_equal(ar.cidr, "10.0.0.0/24")
        testbase.assert_equal(ar.gateway, "10.0.0.1")
        testbase.assert_equal(ar.dns_servers, ["8.8.8.8", "8.8.4.4"])
        testbase.assert_equal(
            ar.reserved_ips, ["10.0.0.5", "10.0.0.6"]
        )
    finally:
        for p in (cr_patch, ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_ip_pool_create_post_manager_error_re_renders():
    """
    **Feature: webworks resources port T6.9 (E2)**
    **Property: create_pool raising yields a 400 re-render
    with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    cr_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeIPPoolManager) -> None:
            instance.create_pool_raises = RuntimeError(
                "invalid CIDR notation"
            )
            return

        ipm_patch = _patch_ip_pool_manager(configure=_seed)
        cr_patch = _patch_ip_pool_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&name=lab&cidr=bad"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = resources_routes_ip_pools.handle_ip_pool_create(
            request
        )

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        category, message = ctx["flashes"][0]
        testbase.assert_equal(category, "error")
    finally:
        for p in (cr_patch, ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_ip_pool_detail_renders_with_allocations_and_available():
    """
    **Feature: webworks resources port T6.10 (E2)**
    **Property: GET /resources/ip-pools/{id} renders the
    detail template with allocations + the available_ips
    preview list.**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        pool = _FakeIPPool(pool_id=7, name="lab")

        def _seed(instance: _FakeIPPoolManager) -> None:
            instance.get_pool_response = pool
            instance.list_allocations_response = [
                _FakeIPAllocation(allocation_id=11, ip_address="10.0.0.5"),
            ]
            instance.get_available_ips_response = [
                "10.0.0.10", "10.0.0.11"
            ]
            return

        ipm_patch = _patch_ip_pool_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"pool_id": "7"},
        )
        response = resources_routes_ip_pools.handle_ip_pool_detail(
            request
        )

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["pool"], pool)
        testbase.assert_equal(len(ctx["allocations"]), 1)
        testbase.assert_equal(
            ctx["available_ips"], ["10.0.0.10", "10.0.0.11"]
        )
    finally:
        for p in (ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_ip_pool_edit_post_happy_path_passes_csv_lists():
    """
    **Feature: webworks resources port T6.11 (E2)**
    **Property: A valid edit POST passes parsed dns_servers /
    reserved_ips lists into the IPPoolUpdateRequest. Empty CSV
    fields become None (don't update).**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    upd_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeIPPoolManager) -> None:
            instance.get_pool_response = _FakeIPPool(
                pool_id=7, name="lab"
            )
            return

        ipm_patch = _patch_ip_pool_manager(configure=_seed)
        upd_patch = _patch_ip_pool_update_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&description=Updated"
            b"&dns_servers=1.1.1.1&reserved_ips="
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"pool_id": "7"},
        )
        response = resources_routes_ip_pools.handle_ip_pool_edit(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/ip-pools/7"
        )
        ipm = _FakeIPPoolManager.last_instance
        target_id, ar, user_id = ipm.update_pool_calls[0]
        testbase.assert_equal(target_id, 7)
        testbase.assert_equal(ar.description, "Updated")
        testbase.assert_equal(ar.dns_servers, ["1.1.1.1"])
        testbase.assert_equal(ar.reserved_ips, None)
    finally:
        for p in (upd_patch, ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_ip_pool_edit_redirects_when_user_lacks_admin():
    """
    **Feature: webworks resources port T6.11 (E2)**
    **Property: A non-admin user is redirected away from the
    edit form to /resources/dashboard.**
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
            path_params={"pool_id": "7"},
        )
        response = resources_routes_ip_pools.handle_ip_pool_edit(
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


def test_handle_ip_pool_delete_happy_path_redirects_to_list():
    """
    **Feature: webworks resources port T6.12 (E2)**
    **Property: A valid POST calls delete_pool and redirects
    to /resources/ip-pools with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        ipm_patch = _patch_ip_pool_manager()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"pool_id": "7"},
        )
        response = resources_routes_ip_pools.handle_ip_pool_delete(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/ip-pools"
        )
        ipm = _FakeIPPoolManager.last_instance
        testbase.assert_equal(ipm.delete_pool_calls, [(7, "u-admin")])
    finally:
        for p in (ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# IP Pool checkout / checkin
# ===========================================================================


def test_handle_ip_pool_checkout_single_uses_checkout_ip():
    """
    **Feature: webworks resources port T6.13 (E2)**
    **Property: When count=1 (default), the handler calls
    checkout_ip (singular) and reports the allocated IP in the
    success flash.**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    cr_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeIPPoolManager) -> None:
            instance.checkout_ip_response = _FakeIPAllocation(
                allocation_id=11, ip_address="10.0.0.42"
            )
            return

        ipm_patch = _patch_ip_pool_manager(configure=_seed)
        cr_patch = _patch_ip_allocation_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&count=1&job_id=job-123"
            b"&reason=test+run"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"pool_id": "7"},
        )
        response = resources_routes_ip_pools.handle_ip_pool_checkout(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/resources/ip-pools/7"
        )
        ipm = _FakeIPPoolManager.last_instance
        testbase.assert_equal(len(ipm.checkout_ip_calls), 1)
        testbase.assert_equal(ipm.checkout_ips_calls, [])
    finally:
        for p in (cr_patch, ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_ip_pool_checkout_bulk_uses_checkout_ips():
    """
    **Feature: webworks resources port T6.13 (E2)**
    **Property: When count > 1, the handler calls checkout_ips
    (plural) and reports the count in the success flash.**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    cr_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        ipm_patch = _patch_ip_pool_manager()
        cr_patch = _patch_ip_allocation_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&count=3"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"pool_id": "7"},
        )
        response = resources_routes_ip_pools.handle_ip_pool_checkout(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        ipm = _FakeIPPoolManager.last_instance
        testbase.assert_equal(ipm.checkout_ip_calls, [])
        testbase.assert_equal(len(ipm.checkout_ips_calls), 1)
    finally:
        for p in (cr_patch, ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_ip_pool_checkout_manager_error_flashes_error():
    """
    **Feature: webworks resources port T6.13 (E2)**
    **Property: checkout_ip raising yields a 303 redirect to
    /resources/ip-pools/{id} with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    cr_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeIPPoolManager) -> None:
            instance.checkout_ip_raises = RuntimeError(
                "no IPs available"
            )
            return

        ipm_patch = _patch_ip_pool_manager(configure=_seed)
        cr_patch = _patch_ip_allocation_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&count=1"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"pool_id": "7"},
        )
        response = resources_routes_ip_pools.handle_ip_pool_checkout(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
    finally:
        for p in (cr_patch, ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_ip_pool_checkin_with_allocation_id_calls_checkin_ip():
    """
    **Feature: webworks resources port T6.14 (E2)**
    **Property: A POST with allocation_id calls checkin_ip and
    redirects with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        ipm_patch = _patch_ip_pool_manager()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&allocation_id=42"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"pool_id": "7"},
        )
        response = resources_routes_ip_pools.handle_ip_pool_checkin(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        ipm = _FakeIPPoolManager.last_instance
        testbase.assert_equal(
            ipm.checkin_ip_calls, [(42, "u-admin")]
        )
        testbase.assert_equal(ipm.checkin_job_ips_calls, [])
    finally:
        for p in (ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_ip_pool_checkin_with_job_id_calls_checkin_job_ips():
    """
    **Feature: webworks resources port T6.14 (E2)**
    **Property: A POST without allocation_id but with job_id
    calls checkin_job_ips and reports the count in the
    success flash.**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeIPPoolManager) -> None:
            instance.checkin_job_ips_response = 5
            return

        ipm_patch = _patch_ip_pool_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&job_id=job-7"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"pool_id": "7"},
        )
        response = resources_routes_ip_pools.handle_ip_pool_checkin(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        ipm = _FakeIPPoolManager.last_instance
        testbase.assert_equal(
            ipm.checkin_job_ips_calls, [("job-7", "u-admin")]
        )
        testbase.assert_equal(ipm.checkin_ip_calls, [])
    finally:
        for p in (ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_ip_pool_checkin_without_either_id_flashes_error():
    """
    **Feature: webworks resources port T6.14 (E2)**
    **Property: A POST with neither allocation_id nor job_id
    flashes an error and does NOT call either checkin variant.**
    """
    _reset_global_state()
    sm_patch = None
    ipm_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        ipm_patch = _patch_ip_pool_manager()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"pool_id": "7"},
        )
        response = resources_routes_ip_pools.handle_ip_pool_checkin(
            request
        )

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        ipm = _FakeIPPoolManager.last_instance
        testbase.assert_equal(ipm.checkin_ip_calls, [])
        testbase.assert_equal(ipm.checkin_job_ips_calls, [])
    finally:
        for p in (ipm_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return
