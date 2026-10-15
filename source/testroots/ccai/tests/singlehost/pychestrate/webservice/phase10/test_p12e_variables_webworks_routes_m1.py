"""
.. module:: test_p12e_variables_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native variables REST routes.

.. moduleauthor:: Code Craft AI LLC

The variables port has five routes spanning 1/2/3-segment depths
under ``/variables``, plus a typed binding shape that requires
both URL scope coercion AND body value_type coercion. Tests cover
the route matrix, the 503 sweep, the per-error extension members,
the optional-trace branch on the effective endpoint, and the
404/204 paths on read/delete.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.errors.exceptions import SemanticError
from ccai.testbase.mocking import create_module_patch
from ccai.webworks.routing.response import JSONResponse

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
)
from ccai.pychestrate.webservice.variables.exceptions import (
    InvalidVariableScopeError,
    InvalidVariableValueError,
    VariableNotFoundError,
)
from ccai.pychestrate.webservice.variables.models import (
    VariableScope,
    VariableValueType,
)
from ccai.pychestrate.webservice.variables.restapi.v1 import (
    variables_routes,
)


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeQueryParams:
    def __init__(self, *, values: Optional[Dict[str, str]] = None) -> None:
        self._values: Dict[str, str] = values if values is not None else {}
        return

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, str]] = None,
        body: Any = None,
        body_raises: bool = False,
        db_session: Optional[Any] = None,
        actor_user_id: Optional[str] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self._body_raises: bool = body_raises
        self.db_session: Optional[Any] = db_session
        self.actor_user_id: Optional[str] = actor_user_id
        return

    def json(self) -> Any:
        if self._body_raises:
            raise ValueError("malformed json")
        return self._body


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


class _FakeBinding:
    def __init__(
        self,
        *,
        binding_id: str,
        scope: VariableScope = VariableScope.SYSTEM,
        scope_id: str = "global",
        name: str = "var-x",
        value_type: VariableValueType = VariableValueType.STRING,
        set_by_user_id: Optional[str] = None,
    ) -> None:
        self.binding_id: str = binding_id
        self.scope: VariableScope = scope
        self.scope_id: str = scope_id
        self.name: str = name
        self.value_type: VariableValueType = value_type
        self.set_by_user_id: Optional[str] = set_by_user_id
        self.description: Optional[str] = None
        self.set_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _raises(exc: BaseException) -> Callable[..., Any]:
    def side(*args: Any, **kwargs: Any) -> Any:
        raise exc

    rtnval = side
    return rtnval


def _patch_service_attr(*, name: str, value: Any) -> Any:
    """
        Patch ``variables_routes.variable_service`` so the named
        attribute is the supplied callable / value.
    """
    patch = create_module_patch(variables_routes, "variable_service")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    # decode_binding_value is read by _binding_to_dict; default to a
    # passthrough so happy-path serialization works without each test
    # restubbing it.
    mock_module.mock_context().set_attribute(
        "decode_binding_value", lambda **kwargs: "decoded-value"
    )
    mock_module.mock_context().set_attribute(name, value)
    return patch


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_variables_routes_attaches_five_routes():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: register_variables_routes attaches the same five
    method+path pairs the flask_restx controller exposed.**
    """
    app = _FakeApp()
    variables_routes.register_variables_routes(
        app=app, version_prefix="/api/v1"
    )

    expected_pairs = (
        ("/api/v1/variables/effective", ("GET",)),
        ("/api/v1/variables/{scope}/{scope_id}", ("GET",)),
        ("/api/v1/variables/{scope}/{scope_id}/{name}", ("GET",)),
        ("/api/v1/variables/{scope}/{scope_id}/{name}", ("PUT",)),
        ("/api/v1/variables/{scope}/{scope_id}/{name}", ("DELETE",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# 503 sweep
# ---------------------------------------------------------------------------


def test_handle_set_returns_503_when_session_missing():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: set handler returns 503 problem+json on missing
    session.**
    """
    request = _FakeRequest(
        path="/api/v1/variables/system/global/var-x",
        path_params={"scope": "system", "scope_id": "global", "name": "var-x"},
        body={"value": "hello", "value_type": "STRING"},
        db_session=None,
    )
    response = variables_routes.handle_set_variable(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_read_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/variables/system/global/var-x",
        path_params={"scope": "system", "scope_id": "global", "name": "var-x"},
        db_session=None,
    )
    response = variables_routes.handle_read_variable(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_unset_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/variables/system/global/var-x",
        path_params={"scope": "system", "scope_id": "global", "name": "var-x"},
        db_session=None,
    )
    response = variables_routes.handle_unset_variable(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_list_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/variables/system/global",
        path_params={"scope": "system", "scope_id": "global"},
        db_session=None,
    )
    response = variables_routes.handle_list_variables(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_effective_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/variables/effective",
        query={"name": "var-x"},
        db_session=None,
    )
    response = variables_routes.handle_effective_variable(request)
    testbase.assert_equal(response.status_code, 503)
    return


# ---------------------------------------------------------------------------
# handle_set_variable
# ---------------------------------------------------------------------------


def test_handle_set_returns_200_with_actor_propagation_and_value_type_coercion():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: Successful set returns 200 with the binding dict;
    actor_user_id and value_type enum propagate to set_variable.**
    """
    binding = _FakeBinding(binding_id="b-1", name="var-x")
    captured: Dict[str, Any] = {}

    def fake_set(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return binding

    patch = _patch_service_attr(name="set_variable", value=fake_set)
    try:
        request = _FakeRequest(
            path="/api/v1/variables/system/global/var-x",
            path_params={"scope": "system", "scope_id": "global", "name": "var-x"},
            db_session=object(),
            actor_user_id="user-42",
            body={"value": "hello", "value_type": "STRING"},
        )
        response = variables_routes.handle_set_variable(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["binding_id"], "b-1")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    testbase.assert_equal(captured["scope"], VariableScope.SYSTEM)
    testbase.assert_equal(captured["value_type"], VariableValueType.STRING)
    return


def test_handle_set_returns_400_on_unknown_scope_with_extension():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: An unknown URL scope segment returns 400 problem
    +json with the raw scope string as an extension member.**
    """
    request = _FakeRequest(
        path="/api/v1/variables/garbage/global/var-x",
        path_params={"scope": "garbage", "scope_id": "global", "name": "var-x"},
        db_session=object(),
        body={"value": "x", "value_type": "STRING"},
    )
    response = variables_routes.handle_set_variable(request)
    testbase.assert_equal(response.status_code, 400)
    decoded = _decode_body(response)
    testbase.assert_equal(decoded["scope"], "garbage")
    return


def test_handle_set_returns_400_on_unknown_value_type_with_extension():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: An unknown body value_type returns 400 problem+json
    with the raw value_type as an extension member.**
    """
    request = _FakeRequest(
        path="/api/v1/variables/system/global/var-x",
        path_params={"scope": "system", "scope_id": "global", "name": "var-x"},
        db_session=object(),
        body={"value": "x", "value_type": "GARBAGE"},
    )
    response = variables_routes.handle_set_variable(request)
    testbase.assert_equal(response.status_code, 400)
    decoded = _decode_body(response)
    testbase.assert_equal(decoded["value_type"], "GARBAGE")
    return


def test_handle_set_returns_400_on_invalid_variable_value():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: InvalidVariableValueError → 400 problem+json with
    {scope, scope_id, name} as extension members.**
    """
    patch = _patch_service_attr(
        name="set_variable",
        value=_raises(InvalidVariableValueError("not an int")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/variables/system/global/var-x",
            path_params={"scope": "system", "scope_id": "global", "name": "var-x"},
            db_session=object(),
            body={"value": "abc", "value_type": "INTEGER"},
        )
        response = variables_routes.handle_set_variable(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["scope"], "system")
    testbase.assert_equal(body["scope_id"], "global")
    testbase.assert_equal(body["name"], "var-x")
    return


def test_handle_set_returns_400_on_undecodable_body():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: An undecodable body returns 400, not 500.**
    """
    request = _FakeRequest(
        path="/api/v1/variables/system/global/var-x",
        path_params={"scope": "system", "scope_id": "global", "name": "var-x"},
        db_session=object(),
        body_raises=True,
    )
    response = variables_routes.handle_set_variable(request)
    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# handle_read_variable
# ---------------------------------------------------------------------------


def test_handle_read_returns_serialized_binding_on_match():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: A known binding returns 200 with the binding dict
    (decoded value included via decode_binding_value).**
    """
    binding = _FakeBinding(binding_id="b-1", name="var-x")
    patch = _patch_service_attr(
        name="get_variable", value=lambda **kwargs: binding
    )
    try:
        request = _FakeRequest(
            path="/api/v1/variables/system/global/var-x",
            path_params={"scope": "system", "scope_id": "global", "name": "var-x"},
            db_session=object(),
        )
        response = variables_routes.handle_read_variable(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["binding_id"], "b-1")
    testbase.assert_equal(body["value"], "decoded-value")
    return


def test_handle_read_returns_404_with_extensions_on_missing():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: VariableNotFoundError → 404 problem+json with
    {scope, scope_id, name} as extension members.**
    """
    patch = _patch_service_attr(
        name="get_variable", value=_raises(VariableNotFoundError("missing"))
    )
    try:
        request = _FakeRequest(
            path="/api/v1/variables/system/global/var-missing",
            path_params={"scope": "system", "scope_id": "global", "name": "var-missing"},
            db_session=object(),
        )
        response = variables_routes.handle_read_variable(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["name"], "var-missing")
    return


# ---------------------------------------------------------------------------
# handle_unset_variable
# ---------------------------------------------------------------------------


def test_handle_unset_returns_204_on_success():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: Successful unset returns 204 with empty body.**
    """
    captured: Dict[str, Any] = {}

    def fake_unset(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return None

    patch = _patch_service_attr(name="unset_variable", value=fake_unset)
    try:
        request = _FakeRequest(
            path="/api/v1/variables/system/global/var-x",
            path_params={"scope": "system", "scope_id": "global", "name": "var-x"},
            db_session=object(),
            actor_user_id="user-42",
        )
        response = variables_routes.handle_unset_variable(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 204)
    testbase.assert_equal(response.body, b"")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    return


def test_handle_unset_returns_404_with_extensions_on_missing():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: VariableNotFoundError → 404 problem+json with
    {scope, scope_id, name} as extension members.**
    """
    patch = _patch_service_attr(
        name="unset_variable", value=_raises(VariableNotFoundError("missing"))
    )
    try:
        request = _FakeRequest(
            path="/api/v1/variables/system/global/var-missing",
            path_params={"scope": "system", "scope_id": "global", "name": "var-missing"},
            db_session=object(),
        )
        response = variables_routes.handle_unset_variable(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["name"], "var-missing")
    return


# ---------------------------------------------------------------------------
# handle_list_variables
# ---------------------------------------------------------------------------


def test_handle_list_returns_serialized_bindings():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: list returns 200 with serialized bindings for the
    given scope.**
    """
    rows = [
        _FakeBinding(binding_id="b-1", name="var-1"),
        _FakeBinding(binding_id="b-2", name="var-2"),
    ]
    patch = _patch_service_attr(
        name="list_for_scope", value=lambda **kwargs: rows
    )
    try:
        request = _FakeRequest(
            path="/api/v1/variables/system/global",
            path_params={"scope": "system", "scope_id": "global"},
            db_session=object(),
        )
        response = variables_routes.handle_list_variables(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[0]["binding_id"], "b-1")
    return


def test_handle_list_returns_400_on_invalid_scope_combination():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: InvalidVariableScopeError from the service →
    400 problem+json with scope + scope_id extensions.**
    """
    patch = _patch_service_attr(
        name="list_for_scope",
        value=_raises(InvalidVariableScopeError("project_id required")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/variables/project/",
            path_params={"scope": "project", "scope_id": ""},
            db_session=object(),
        )
        response = variables_routes.handle_list_variables(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["scope"], "project")
    return


# ---------------------------------------------------------------------------
# handle_effective_variable
# ---------------------------------------------------------------------------


def test_handle_effective_returns_value_with_no_trace_by_default():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: effective returns ``{name, value}`` -- no trace
    when include_trace is unset.**
    """
    captured: Dict[str, Any] = {}

    def fake_resolve(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return "resolved-value"

    patch = _patch_service_attr(name="resolve_effective", value=fake_resolve)
    try:
        request = _FakeRequest(
            path="/api/v1/variables/effective",
            db_session=object(),
            query={"name": "var-x", "project": "p-1"},
        )
        response = variables_routes.handle_effective_variable(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["name"], "var-x")
    testbase.assert_equal(body["value"], "resolved-value")
    has_trace = "trace" in body
    testbase.assert_equal(has_trace, False)
    testbase.assert_equal(captured["project_id"], "p-1")
    return


def test_handle_effective_includes_trace_when_requested():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: effective with include_trace=true adds a trace
    array shaped {scope, scope_id, present, value_type,
    set_by_user_id, set_at}. dereference_secrets propagates
    through to resolve_effective.**
    """
    binding = _FakeBinding(
        binding_id="b-1",
        scope=VariableScope.SYSTEM,
        scope_id="global",
        name="var-x",
        value_type=VariableValueType.STRING,
        set_by_user_id="user-42",
    )
    trace_entries = [
        {"scope": "system", "scope_id": "global", "binding": binding},
        {"scope": "project", "scope_id": "p-1", "binding": None},
    ]
    captured_resolve: Dict[str, Any] = {}

    def fake_resolve(**kwargs: Any) -> Any:
        captured_resolve.update(kwargs)
        return "resolved-value"

    patch = _patch_service_attr(name="resolve_effective", value=fake_resolve)
    try:
        # Add the build_trace stub to the same patched module.
        import ccai.pychestrate.webservice.variables.restapi.v1.variables_routes as vr_mod
        vr_mod.variable_service.mock_context().set_attribute(
            "build_trace", lambda **kwargs: trace_entries
        )
        request = _FakeRequest(
            path="/api/v1/variables/effective",
            db_session=object(),
            query={
                "name": "var-x",
                "project": "p-1",
                "include_trace": "true",
                "dereference_secrets": "yes",
            },
        )
        response = variables_routes.handle_effective_variable(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(captured_resolve["dereference_secrets"], True)
    trace = body["trace"]
    testbase.assert_equal(len(trace), 2)
    testbase.assert_equal(trace[0]["present"], True)
    testbase.assert_equal(trace[0]["value_type"], "STRING")
    testbase.assert_equal(trace[0]["set_by_user_id"], "user-42")
    testbase.assert_equal(trace[1]["present"], False)
    testbase.assert_equal(trace[1]["value_type"], None)
    return


def test_handle_effective_returns_400_when_name_missing():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: effective without ``name`` query param returns 400
    problem+json -- name is required.**
    """
    request = _FakeRequest(
        path="/api/v1/variables/effective",
        db_session=object(),
    )
    response = variables_routes.handle_effective_variable(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_variables_routes_and_calls_it():
    """
    **Feature: 2-global-variables T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires
    register_variables_routes into register_service_extensions.**
    """
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    repo_source_root = os.path.normpath(
        os.path.join(
            here, "..", "..", "..", "..", "..", "..", "..", "..",
            "source", "site",
        )
    )
    bootstrap_path = os.path.join(repo_source_root, "app_pychestrate_main.py")
    with open(bootstrap_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    has_import = (
        "from ccai.pychestrate.webservice.variables.restapi.v1.variables_routes import"
        in text
    )
    has_call = "register_variables_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
