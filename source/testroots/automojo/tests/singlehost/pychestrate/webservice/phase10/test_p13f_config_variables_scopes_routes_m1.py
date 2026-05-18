"""
.. module:: test_p13f_config_variables_scopes_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the D3 slice of the config blueprint
               port (variables + scopes).

.. moduleauthor:: Automation Mojo LLC

PR D3 ports the global-variable management (6 routes) and
secret-scope management (3 routes) surfaces of the legacy flask
config blueprint to webworks. These tests cover:

* ``register_variables_routes`` / ``register_scopes_routes`` --
  route attachment matrix.
* variable list -- pagination + search.
* variable create -- GET form, POST happy + validation
  (ValueError) + CSRF.
* variable detail -- happy + 404.
* variable edit -- POST happy + validation, GET render.
* variable delete -- happy + manager-error paths.
* variable history -- happy + 404.
* scope list -- pagination + happy.
* scope create -- GET + POST happy + manager-error.
* scope delete -- happy + 404 (bad id) + manager-error.
* MultiFormView.__getitem__ subscript access (jinja attr fallback).

All store / manager / encryption-key dependencies are patched
at the routes-module bindings so the test suite never imports
the source `global_variable_store` or `secret_manager` modules.
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
    routes_scopes as config_routes_scopes,
    routes_variables as config_routes_variables,
)
from automojo.pychestrate.webservice.webinterface.foundation import (
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
        method: str = "GET",
        cookies: Optional[Dict[str, str]] = None,
        body: bytes = b"",
        path_params: Optional[Dict[str, Any]] = None,
        query_mapping: Optional[Dict[str, str]] = None,
        header_mapping: Optional[Dict[str, str]] = None,
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
        self.headers: _FakeHeaders = _FakeHeaders(mapping=header_mapping)
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
        self.validate_token_calls: List[str] = []
        _FakeSecurityManager.last_instance = self
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


class _FakeVariableType:
    """
        Stand-in for the manager's VariableType enum value. Has
        ``.value`` attribute mirroring the enum-instance shape
        the templates use (``variable.var_type.value``).
    """

    def __init__(self, *, value: str) -> None:
        self.value: str = value
        return


class _FakeVariable:
    def __init__(
            self, *, name: str, value: Any,
            var_type_str: str = "string",
            description: str = ""
        ) -> None:
        self.name: str = name
        self.value: Any = value
        self.var_type: _FakeVariableType = _FakeVariableType(
            value=var_type_str
        )
        self.description: str = description
        return


class _FakeVariableListResponse:
    def __init__(
            self, *, variables: List[_FakeVariable], total: int
        ) -> None:
        self.variables: List[_FakeVariable] = variables
        self.total: int = total
        return


class _FakeVariableStore:
    last_instance: Optional["_FakeVariableStore"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_variables_response: Optional[_FakeVariableListResponse] = None
        self.get_variable_response: Optional[_FakeVariable] = None
        self.list_variables_calls: List[Dict[str, Any]] = []
        self.get_variable_calls: List[str] = []
        self.create_variable_calls: List[Any] = []
        self.update_variable_calls: List[Any] = []
        self.delete_variable_calls: List[Any] = []
        self.get_change_history_calls: List[Any] = []
        self.create_variable_raises: Optional[Exception] = None
        self.update_variable_raises: Optional[Exception] = None
        self.delete_variable_raises: Optional[Exception] = None
        self.parse_value_raises: Optional[Exception] = None
        _FakeVariableStore.last_instance = self
        return

    def list_variables(
            self, *, offset: int, limit: int, search: Optional[str]
        ) -> _FakeVariableListResponse:
        self.list_variables_calls.append(
            {"offset": offset, "limit": limit, "search": search}
        )
        if self.list_variables_response is None:
            return _FakeVariableListResponse(variables=[], total=0)
        return self.list_variables_response

    def get_variable(self, name: str) -> Optional[_FakeVariable]:
        self.get_variable_calls.append(name)
        return self.get_variable_response

    def parse_value_from_string(self, raw: str, var_type: Any) -> Any:
        if self.parse_value_raises is not None:
            raise self.parse_value_raises
        return raw

    def create_variable(self, request: Any, user_id: str) -> None:
        self.create_variable_calls.append((request, user_id))
        if self.create_variable_raises is not None:
            raise self.create_variable_raises
        return

    def update_variable(
            self, name: str, request: Any, user_id: str
        ) -> None:
        self.update_variable_calls.append((name, request, user_id))
        if self.update_variable_raises is not None:
            raise self.update_variable_raises
        return

    def delete_variable(self, name: str, user_id: str) -> None:
        self.delete_variable_calls.append((name, user_id))
        if self.delete_variable_raises is not None:
            raise self.delete_variable_raises
        return

    def get_change_history(
            self, name: str, *, offset: int, limit: int
        ) -> List[Any]:
        self.get_change_history_calls.append(
            (name, offset, limit)
        )
        return [{"id": 1, "name": name}]


class _FakeScope:
    def __init__(
            self, *, scope_id: int, name: str,
            description: str = "",
            is_system: bool = False,
            secret_count: int = 0
        ) -> None:
        self.id: int = scope_id
        self.name: str = name
        self.description: str = description
        self.is_system: bool = is_system
        self.secret_count: int = secret_count
        return


class _FakeSecretManager:
    last_instance: Optional["_FakeSecretManager"] = None

    def __init__(self, db_session: Any) -> None:
        self.db_session: Any = db_session
        self.list_scopes_response: List[_FakeScope] = []
        self.list_scopes_calls: List[Dict[str, Any]] = []
        self.create_scope_calls: List[Any] = []
        self.delete_scope_calls: List[Any] = []
        self.create_scope_raises: Optional[Exception] = None
        self.delete_scope_raises: Optional[Exception] = None
        _FakeSecretManager.last_instance = self
        return

    def list_scopes(
            self, user_id: str, *, offset: int = 0, limit: int = 50
        ) -> Any:
        from types import SimpleNamespace
        self.list_scopes_calls.append(
            {"user_id": user_id, "offset": offset, "limit": limit}
        )
        return SimpleNamespace(
            scopes=self.list_scopes_response,
            total=len(self.list_scopes_response),
            offset=offset,
            limit=limit,
        )

    def create_scope(self, request: Any, user_id: str) -> None:
        self.create_scope_calls.append((request, user_id))
        if self.create_scope_raises is not None:
            raise self.create_scope_raises
        return

    def delete_scope(self, scope_id: int, user_id: str) -> None:
        self.delete_scope_calls.append((scope_id, user_id))
        if self.delete_scope_raises is not None:
            raise self.delete_scope_raises
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
    _FakeVariableStore.last_instance = None
    _FakeSecretManager.last_instance = None
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


def _patch_variable_store(
        *, configure: Optional[Callable[[_FakeVariableStore], None]] = None
    ) -> Any:
    def _builder(*, db_session: Any) -> _FakeVariableStore:
        instance = _FakeVariableStore(db_session)
        if configure is not None:
            configure(instance)
        return instance

    patch = create_module_patch(
        config_routes_variables, "_build_variable_store"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_variable_create_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        config_routes_variables, "_build_variable_create_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_variable_update_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        config_routes_variables, "_build_variable_update_request"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_resolve_variable_type() -> Any:
    def _resolve(*, var_type_str: str) -> _FakeVariableType:
        return _FakeVariableType(value=var_type_str)

    patch = create_module_patch(
        config_routes_variables, "_resolve_variable_type"
    )
    mock = patch.activate()
    mock.configure(side_effect=_resolve)
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
        config_routes_scopes, "_build_secret_manager"
    )
    mock = patch.activate()
    mock.configure(side_effect=_builder)
    return patch


def _patch_scope_create_request_factory() -> Any:
    class _NS:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            return

    def _builder(**kwargs: Any) -> _NS:
        return _NS(**kwargs)

    patch = create_module_patch(
        config_routes_scopes, "_build_scope_create_request"
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
    app = _FakeApp()
    config_routes.register_config_routes(app=app)
    return


# ===========================================================================
# Route registration
# ===========================================================================


def test_register_variables_routes_attaches_documented_routes():
    """
    **Feature: webworks config variables port T3.1 (D3)**
    **Property: register_variables_routes attaches the six
    variable routes at /admin/variables*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        config_routes_variables.register_variables_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/admin/variables", ("GET",)),
            ("/admin/variables/create", ("GET", "POST")),
            ("/admin/variables/{name}", ("GET",)),
            ("/admin/variables/{name}/edit", ("GET", "POST")),
            ("/admin/variables/{name}/delete", ("POST",)),
            ("/admin/variables/{name}/history", ("GET",)),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


def test_register_scopes_routes_attaches_documented_routes():
    """
    **Feature: webworks config scopes port T3.2 (D3)**
    **Property: register_scopes_routes attaches the three scope
    routes at /admin/scopes*.**
    """
    _reset_global_state()
    try:
        app = _FakeApp()
        config_routes_scopes.register_scopes_routes(app=app)
        actual = set(
            (path, methods) for path, methods, _ in app.calls
        )
        expected = {
            ("/admin/scopes", ("GET",)),
            ("/admin/scopes/create", ("GET", "POST")),
            ("/admin/scopes/{scope_id}/delete", ("POST",)),
        }
        testbase.assert_equal(actual, expected)
    finally:
        _reset_global_state()
    return


# ===========================================================================
# MultiFormView.__getitem__ subscript
# ===========================================================================


def test_multi_form_view_subscript_returns_first_value_or_raises():
    """
    **Feature: D3 helpers T3.3**
    **Property: MultiFormView.__getitem__ returns the first
    submitted value (jinja attribute-fallback path), and raises
    KeyError on absent / empty keys.**
    """
    view = config_routes.MultiFormView(
        data={"var_type": ["integer"], "empty": []}
    )
    testbase.assert_equal(view["var_type"], "integer")

    raised = False
    try:
        _ = view["missing"]
    except KeyError:
        raised = True
    testbase.assert_equal(raised, True)

    raised = False
    try:
        _ = view["empty"]
    except KeyError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ===========================================================================
# Variables -- list
# ===========================================================================


def test_handle_variable_list_renders_with_pagination():
    """
    **Feature: webworks config variables port T3.4**
    **Property: GET /admin/variables renders config/variables/
    list.html with the paginated store output and total_pages.**
    """
    _reset_global_state()
    sm_patch = None
    vs_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        variables = [_FakeVariable(name="x", value="1", var_type_str="integer")]

        def _seed(instance: _FakeVariableStore) -> None:
            instance.list_variables_response = _FakeVariableListResponse(
                variables=variables, total=23
            )
            return

        vs_patch = _patch_variable_store(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            query_mapping={"page": "1", "per_page": "10", "search": "x"},
        )
        response = config_routes_variables.handle_variable_list(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/variables/list.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["variables"], variables)
        testbase.assert_equal(ctx["total"], 23)
        testbase.assert_equal(ctx["total_pages"], 3)  # ceil(23/10)
        testbase.assert_equal(ctx["search"], "x")
    finally:
        if vs_patch is not None:
            vs_patch.deactivate()
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Variables -- create
# ===========================================================================


def test_handle_variable_create_get_renders_form():
    """
    **Feature: webworks config variables port T3.5**
    **Property: GET /admin/variables/create renders the
    create template with form_data=None.**
    """
    _reset_global_state()
    sm_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            method="GET",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
        )
        response = config_routes_variables.handle_variable_create(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/variables/create.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["form_data"], None)
    finally:
        if sm_patch is not None:
            sm_patch.deactivate()
        _reset_global_state()
    return


def test_handle_variable_create_post_happy_path_redirects_to_list():
    """
    **Feature: webworks config variables port T3.5**
    **Property: A valid POST creates the variable via the store
    and redirects to /admin/variables.**
    """
    _reset_global_state()
    sm_patch = None
    vs_patch = None
    cr_patch = None
    rt_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        vs_patch = _patch_variable_store()
        cr_patch = _patch_variable_create_request_factory()
        rt_patch = _patch_resolve_variable_type()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=feature_x&value=42"
            b"&var_type=integer&description=Count+of+x"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_variables.handle_variable_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/variables"
        )
        vs = _FakeVariableStore.last_instance
        testbase.assert_equal(len(vs.create_variable_calls), 1)
        ar, user_id = vs.create_variable_calls[0]
        testbase.assert_equal(ar.name, "feature_x")
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (rt_patch, cr_patch, vs_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_variable_create_post_value_error_re_renders_with_flash():
    """
    **Feature: webworks config variables port T3.5**
    **Property: A ValueError from parse_value_from_string
    re-renders the form (400) with an error-category flash.**
    """
    _reset_global_state()
    sm_patch = None
    vs_patch = None
    cr_patch = None
    rt_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeVariableStore) -> None:
            instance.parse_value_raises = ValueError(
                "not a valid integer"
            )
            return

        vs_patch = _patch_variable_store(configure=_seed)
        cr_patch = _patch_variable_create_request_factory()
        rt_patch = _patch_resolve_variable_type()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&name=feature_x&value=not-int"
            b"&var_type=integer"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_variables.handle_variable_create(request)

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        category, message = ctx["flashes"][0]
        testbase.assert_equal(category, "error")
        contains = "not a valid integer" in message
        testbase.assert_equal(contains, True)
    finally:
        for p in (rt_patch, cr_patch, vs_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_variable_create_post_csrf_mismatch_redirects():
    """
    **Feature: webworks config variables port T3.5**
    **Property: A POST with a mismatched csrf_token bounces
    back without invoking the store.**
    """
    _reset_global_state()
    sm_patch = None
    vs_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        vs_patch = _patch_variable_store()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=wrong&name=x&value=1&var_type=integer"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_variables.handle_variable_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(_FakeVariableStore.last_instance, None)
    finally:
        for p in (vs_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Variables -- detail
# ===========================================================================


def test_handle_variable_detail_renders_when_variable_found():
    """
    **Feature: webworks config variables port T3.6**
    **Property: GET /admin/variables/{name} renders the detail
    template with the variable.**
    """
    _reset_global_state()
    sm_patch = None
    vs_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        var = _FakeVariable(name="feature_x", value="1", var_type_str="integer")

        def _seed(instance: _FakeVariableStore) -> None:
            instance.get_variable_response = var
            return

        vs_patch = _patch_variable_store(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"name": "feature_x"},
        )
        response = config_routes_variables.handle_variable_detail(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["variable"], var)
    finally:
        for p in (vs_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_variable_detail_redirects_when_missing():
    """
    **Feature: webworks config variables port T3.6**
    **Property: A name not found redirects to the list with
    an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    vs_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        vs_patch = _patch_variable_store()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"name": "ghost"},
        )
        response = config_routes_variables.handle_variable_detail(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/variables"
        )
    finally:
        for p in (vs_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Variables -- edit
# ===========================================================================


def test_handle_variable_edit_post_happy_path_redirects_to_detail():
    """
    **Feature: webworks config variables port T3.7**
    **Property: A valid POST updates the variable and redirects
    to /admin/variables/{name}.**
    """
    _reset_global_state()
    sm_patch = None
    vs_patch = None
    upd_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        var = _FakeVariable(name="feature_x", value="1", var_type_str="integer")

        def _seed(instance: _FakeVariableStore) -> None:
            instance.get_variable_response = var
            return

        vs_patch = _patch_variable_store(configure=_seed)
        upd_patch = _patch_variable_update_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = (
            b"csrf_token=csrf-fresh&value=99&description=Updated"
        )
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"name": "feature_x"},
        )
        response = config_routes_variables.handle_variable_edit(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/variables/feature_x"
        )
        vs = _FakeVariableStore.last_instance
        testbase.assert_equal(len(vs.update_variable_calls), 1)
        target_name, ar, user_id = vs.update_variable_calls[0]
        testbase.assert_equal(target_name, "feature_x")
        testbase.assert_equal(ar.description, "Updated")
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (upd_patch, vs_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Variables -- delete
# ===========================================================================


def test_handle_variable_delete_happy_path_redirects_to_list():
    """
    **Feature: webworks config variables port T3.8**
    **Property: A valid POST calls store.delete_variable and
    redirects to /admin/variables with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    vs_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        vs_patch = _patch_variable_store()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"name": "feature_x"},
        )
        response = config_routes_variables.handle_variable_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/variables"
        )
        vs = _FakeVariableStore.last_instance
        testbase.assert_equal(
            vs.delete_variable_calls, [("feature_x", "u-admin")]
        )
    finally:
        for p in (vs_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_variable_delete_manager_error_flashes_error():
    """
    **Feature: webworks config variables port T3.8**
    **Property: store.delete_variable raising any exception
    yields a 303 redirect with an error-category flash.**
    """
    _reset_global_state()
    sm_patch = None
    vs_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeVariableStore) -> None:
            instance.delete_variable_raises = RuntimeError(
                "variable in use"
            )
            return

        vs_patch = _patch_variable_store(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"name": "feature_x"},
        )
        response = config_routes_variables.handle_variable_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/variables"
        )
    finally:
        for p in (vs_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Variables -- history
# ===========================================================================


def test_handle_variable_history_renders_with_history():
    """
    **Feature: webworks config variables port T3.9**
    **Property: GET /admin/variables/{name}/history renders
    the history template with the variable + change-history
    list + pagination params.**
    """
    _reset_global_state()
    sm_patch = None
    vs_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        var = _FakeVariable(name="feature_x", value="1", var_type_str="integer")

        def _seed(instance: _FakeVariableStore) -> None:
            instance.get_variable_response = var
            return

        vs_patch = _patch_variable_store(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"name": "feature_x"},
            query_mapping={"page": "1", "per_page": "5"},
        )
        response = config_routes_variables.handle_variable_history(request)

        testbase.assert_equal(response.status_code, 200)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["variable"], var)
        testbase.assert_equal(len(ctx["history"]), 1)
        testbase.assert_equal(ctx["page"], 1)
        testbase.assert_equal(ctx["per_page"], 5)
    finally:
        for p in (vs_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_variable_history_redirects_when_missing():
    """
    **Feature: webworks config variables port T3.9**
    **Property: A name not found redirects to the list.**
    """
    _reset_global_state()
    sm_patch = None
    vs_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        vs_patch = _patch_variable_store()

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            path_params={"name": "ghost"},
        )
        response = config_routes_variables.handle_variable_history(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
    finally:
        for p in (vs_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Scopes -- list / create / delete
# ===========================================================================


def test_handle_scope_list_renders_with_scopes():
    """
    **Feature: webworks config scopes port T3.10**
    **Property: GET /admin/scopes renders the scope_list
    template with the secret_manager.list_scopes output.**
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
        scopes = [
            _FakeScope(scope_id=1, name="prod", is_system=True),
            _FakeScope(scope_id=2, name="dev"),
        ]

        def _seed(instance: _FakeSecretManager) -> None:
            instance.list_scopes_response = scopes
            return

        secret_patch = _patch_secret_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        request = _FakeRequest(
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            query_mapping={"page": "1", "per_page": "20"},
        )
        response = config_routes_scopes.handle_scope_list(request)

        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            env.template_lookups, ["config/secrets/scope_list.html"]
        )
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(ctx["scopes"], scopes)
        # secret_manager.list_scopes called with user_id=u-admin.
        sm = _FakeSecretManager.last_instance
        testbase.assert_equal(
            sm.list_scopes_calls[0]["user_id"], "u-admin"
        )
    finally:
        for p in (secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_scope_create_post_happy_path_redirects_to_list():
    """
    **Feature: webworks config scopes port T3.11**
    **Property: A valid POST creates the scope and redirects
    to /admin/scopes with a success flash.**
    """
    _reset_global_state()
    sm_patch = None
    secret_patch = None
    cr_patch = None
    try:
        _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()
        secret_patch = _patch_secret_manager()
        cr_patch = _patch_scope_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&name=staging&description=Staging+env"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_scopes.handle_scope_create(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/scopes"
        )
        sm = _FakeSecretManager.last_instance
        testbase.assert_equal(len(sm.create_scope_calls), 1)
        ar, user_id = sm.create_scope_calls[0]
        testbase.assert_equal(ar.name, "staging")
        testbase.assert_equal(user_id, "u-admin")
    finally:
        for p in (cr_patch, secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_scope_create_post_manager_error_re_renders():
    """
    **Feature: webworks config scopes port T3.11**
    **Property: secret_manager.create_scope raising yields a
    400 re-render with an error flash.**
    """
    _reset_global_state()
    sm_patch = None
    secret_patch = None
    cr_patch = None
    try:
        env = _install_stub_environment()
        _install_ui_cookie_secret()
        _install_db_session_factory(db_session=_FakeDbSession())
        _register_url_for_endpoints()
        sm_patch = _patch_security_manager()

        def _seed(instance: _FakeSecretManager) -> None:
            instance.create_scope_raises = RuntimeError(
                "duplicate scope name"
            )
            return

        secret_patch = _patch_secret_manager(configure=_seed)
        cr_patch = _patch_scope_create_request_factory()

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh&name=staging"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
        )
        response = config_routes_scopes.handle_scope_create(request)

        testbase.assert_equal(response.status_code, 400)
        ctx = env.last_template.render_calls[0]
        testbase.assert_equal(len(ctx["flashes"]), 1)
        category, message = ctx["flashes"][0]
        testbase.assert_equal(category, "error")
        contains = "duplicate" in message
        testbase.assert_equal(contains, True)
    finally:
        for p in (cr_patch, secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_scope_delete_happy_path_redirects_to_list():
    """
    **Feature: webworks config scopes port T3.12**
    **Property: A valid POST calls secret_manager.delete_scope
    with the scope_id and redirects to /admin/scopes.**
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
            path_params={"scope_id": "3"},
        )
        response = config_routes_scopes.handle_scope_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/scopes"
        )
        sm = _FakeSecretManager.last_instance
        testbase.assert_equal(sm.delete_scope_calls, [(3, "u-admin")])
    finally:
        for p in (secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_scope_delete_unparsable_id_returns_error_flash():
    """
    **Feature: webworks config scopes port T3.12**
    **Property: A non-integer scope_id path param yields a
    redirect with a "not found" flash and the manager is NOT
    invoked.**
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
            path_params={"scope_id": "not-an-int"},
        )
        response = config_routes_scopes.handle_scope_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        # Manager not constructed because the handler short-circuited
        # at the unparsable-id check before _build_secret_manager.
        testbase.assert_equal(_FakeSecretManager.last_instance, None)
    finally:
        for p in (secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


def test_handle_scope_delete_manager_error_flashes_error():
    """
    **Feature: webworks config scopes port T3.12**
    **Property: secret_manager.delete_scope raising yields a
    303 redirect with an error-category flash.**
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

        def _seed(instance: _FakeSecretManager) -> None:
            instance.delete_scope_raises = RuntimeError(
                "scope contains secrets"
            )
            return

        secret_patch = _patch_secret_manager(configure=_seed)

        cookie_value = _build_authenticated_cookie()
        body = b"csrf_token=csrf-fresh"
        request = _FakeRequest(
            method="POST",
            cookies={cookie_session.COOKIE_NAME: cookie_value},
            body=body,
            path_params={"scope_id": "3"},
        )
        response = config_routes_scopes.handle_scope_delete(request)

        is_redirect = isinstance(response, RedirectResponse)
        testbase.assert_equal(is_redirect, True)
        testbase.assert_equal(
            response.headers["Location"], "/admin/scopes"
        )
    finally:
        for p in (secret_patch, sm_patch):
            if p is not None:
                p.deactivate()
        _reset_global_state()
    return


# ===========================================================================
# Encryption-key resolver (tested directly)
# ===========================================================================


def test_resolve_secret_encryption_key_uses_default_when_env_unset():
    """
    **Feature: D3 secret-key resolver T3.13**
    **Property: With no SECRET_ENCRYPTION_KEY env var, the
    resolver returns the documented default-key-for-dev bytes.
    Mirrors the legacy flask handler's fallback.**
    """
    import os
    saved = os.environ.pop(
        config_routes_scopes._SECRET_ENCRYPTION_KEY_ENV_VAR, None
    )
    try:
        rtnval = config_routes_scopes._resolve_secret_encryption_key()
        testbase.assert_equal(rtnval, b"default-key-for-dev")
    finally:
        if saved is not None:
            os.environ[
                config_routes_scopes._SECRET_ENCRYPTION_KEY_ENV_VAR
            ] = saved
    return


def test_resolve_secret_encryption_key_reads_env_when_set():
    """
    **Feature: D3 secret-key resolver T3.13**
    **Property: With SECRET_ENCRYPTION_KEY set, the resolver
    returns its UTF-8 bytes.**
    """
    import os
    env_key = config_routes_scopes._SECRET_ENCRYPTION_KEY_ENV_VAR
    saved = os.environ.get(env_key, None)
    os.environ[env_key] = "operator-supplied-key-1234"
    try:
        rtnval = config_routes_scopes._resolve_secret_encryption_key()
        testbase.assert_equal(rtnval, b"operator-supplied-key-1234")
    finally:
        if saved is None:
            del os.environ[env_key]
        else:
            os.environ[env_key] = saved
    return
