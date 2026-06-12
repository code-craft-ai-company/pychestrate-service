"""
.. module:: test_p12g_rbac_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native RBAC REST routes.

.. moduleauthor:: Code Craft AI LLC

The RBAC port has six routes spanning catalog reads (no session
required) and binding CRUD + permission check (session required).
Tests cover the route matrix, the 503 sweep on the
session-requiring handlers, the catalog read shapes, the binding
create/list/revoke flows including enum coercion errors, and the
permission-check flow.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

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
from ccai.pychestrate.webservice.security.rbac.exceptions import (
    BindingNotFoundError,
    InvalidBindingScopeError,
    RoleNotFoundError,
)
from ccai.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PrincipalKind,
)
from ccai.pychestrate.webservice.security.rbac.restapi.v1 import (
    rbac_routes,
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


class _FakeView:
    """
        Stand-in for a :class:`BindingView`.
    """

    def __init__(
        self,
        *,
        binding_id: str,
        role_name: str = "viewer",
        principal_kind: PrincipalKind = PrincipalKind.USER,
        principal_id: str = "u-1",
        scope_kind: BindingScope = BindingScope.SYSTEM,
        scope_id: Optional[str] = None,
        inherits_into_project: bool = False,
        created_at_iso: str = "2026-05-03T12:00:00+00:00",
        created_by: Optional[str] = None,
    ) -> None:
        self.binding_id: str = binding_id
        self.role_name: str = role_name
        self.principal_kind: PrincipalKind = principal_kind
        self.principal_id: str = principal_id
        self.scope_kind: BindingScope = scope_kind
        self.scope_id: Optional[str] = scope_id
        self.inherits_into_project: bool = inherits_into_project
        self.created_at_iso: str = created_at_iso
        self.created_by: Optional[str] = created_by
        return


class _FakeBinding:
    def __init__(self, *, binding_id: str) -> None:
        self.binding_id: str = binding_id
        return


class _FakeDecision:
    def __init__(
        self,
        *,
        allowed: bool,
        reason: str,
        permission_key: str,
    ) -> None:
        self.allowed: bool = allowed
        self.reason: str = reason
        self.permission_key: str = permission_key
        return


class _FakePermissionDescriptor:
    def __init__(
        self,
        *,
        permission_key: str,
        description: str,
        namespace: str,
    ) -> None:
        self.permission_key: str = permission_key
        self.description: str = description
        self.namespace: str = namespace
        return


class _FakeCatalog:
    def __init__(
        self,
        *,
        permissions: Dict[str, _FakePermissionDescriptor],
        roles: Dict[str, List[Any]],
    ) -> None:
        self.permissions: Dict[str, _FakePermissionDescriptor] = permissions
        self.roles: Dict[str, List[Any]] = roles
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


def _patch_routes_attr(*, name: str, value: Any) -> Any:
    """
        Patch ``rbac_routes.<name>`` to the supplied callable.
    """
    patch = create_module_patch(rbac_routes, name)
    mock = patch.activate()
    mock.configure(side_effect=value)
    return patch


def _patch_service_module_attr(
        *, module_attr: str, attr_name: str, value: Any
    ) -> Any:
    """
        Patch ``rbac_routes.<module_attr>.<attr_name>`` -- e.g.
        ``rbac_routes.binding_service.assign_role`` -- since the
        controller imports the service modules and accesses
        functions via attribute access.
    """
    patch = create_module_patch(rbac_routes, module_attr)
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute(attr_name, value)
    return patch


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_rbac_routes_attaches_six_routes():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: register_rbac_routes attaches the same six
    method+path pairs the flask_restx controller exposed.**
    """
    app = _FakeApp()
    rbac_routes.register_rbac_routes(app=app, version_prefix="/api/v1")

    expected_pairs = (
        ("/api/v1/rbac/permissions", ("GET",)),
        ("/api/v1/rbac/roles", ("GET",)),
        ("/api/v1/rbac/bindings", ("GET",)),
        ("/api/v1/rbac/bindings", ("POST",)),
        ("/api/v1/rbac/bindings/{binding_id}", ("DELETE",)),
        ("/api/v1/rbac/check", ("POST",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# Catalog reads (no session required)
# ---------------------------------------------------------------------------


def test_handle_list_permissions_returns_sorted_descriptors():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: list_permissions returns 200 with descriptors
    sorted by permission_key.**
    """
    catalog = _FakeCatalog(
        permissions={
            "system:write": _FakePermissionDescriptor(
                permission_key="system:write",
                description="Write",
                namespace="system",
            ),
            "system:read": _FakePermissionDescriptor(
                permission_key="system:read",
                description="Read",
                namespace="system",
            ),
        },
        roles={},
    )
    patch = _patch_routes_attr(
        name="load_catalog_from_registry",
        value=lambda: catalog,
    )
    try:
        request = _FakeRequest(path="/api/v1/rbac/permissions")
        response = rbac_routes.handle_list_permissions(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[0]["permission_key"], "system:read")
    testbase.assert_equal(body[1]["permission_key"], "system:write")
    return


def test_handle_list_roles_returns_sorted_summaries_with_grant_count():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: list_roles returns 200 with role summaries sorted
    by role_name; permission_count reflects the grants list
    length.**
    """
    catalog = _FakeCatalog(
        permissions={},
        roles={
            "viewer": ["g1"],
            "admin": ["g1", "g2", "g3"],
        },
    )
    patch = _patch_routes_attr(
        name="load_catalog_from_registry",
        value=lambda: catalog,
    )
    try:
        request = _FakeRequest(path="/api/v1/rbac/roles")
        response = rbac_routes.handle_list_roles(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body[0]["role_name"], "admin")
    testbase.assert_equal(body[0]["permission_count"], 3)
    testbase.assert_equal(body[1]["role_name"], "viewer")
    testbase.assert_equal(body[1]["permission_count"], 1)
    return


# ---------------------------------------------------------------------------
# 503 sweep on session-requiring handlers
# ---------------------------------------------------------------------------


def test_handle_create_binding_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/rbac/bindings",
        body={
            "role_name": "viewer", "principal_kind": "USER",
            "principal_id": "u-1", "scope_kind": "SYSTEM",
        },
        db_session=None,
    )
    response = rbac_routes.handle_create_binding(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_list_bindings_returns_503_when_session_missing():
    request = _FakeRequest(path="/api/v1/rbac/bindings", db_session=None)
    response = rbac_routes.handle_list_bindings(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_revoke_binding_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/rbac/bindings/b-1",
        path_params={"binding_id": "b-1"},
        db_session=None,
    )
    response = rbac_routes.handle_revoke_binding(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_check_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/rbac/check",
        body={"principal_id": "u-1", "permission_key": "system:read"},
        db_session=None,
    )
    response = rbac_routes.handle_check_permission(request)
    testbase.assert_equal(response.status_code, 503)
    return


# ---------------------------------------------------------------------------
# handle_create_binding
# ---------------------------------------------------------------------------


def test_handle_create_binding_returns_201_with_normalized_view():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: Successful create returns 201 with the BindingView
    re-read via list_bindings (so created_at is normalized).**
    """
    binding = _FakeBinding(binding_id="b-1")
    view = _FakeView(binding_id="b-1", role_name="viewer")
    captured_assign: Dict[str, Any] = {}

    def fake_assign(**kwargs: Any) -> Any:
        captured_assign.update(kwargs)
        return binding

    def fake_list(**kwargs: Any) -> Any:
        return [view]

    patch = create_module_patch(rbac_routes, "binding_service")
    try:
        mock_module = patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute("assign_role", fake_assign)
        mock_module.mock_context().set_attribute("list_bindings", fake_list)
        request = _FakeRequest(
            path="/api/v1/rbac/bindings",
            db_session=object(),
            actor_user_id="user-42",
            body={
                "role_name": "viewer",
                "principal_kind": "USER",
                "principal_id": "u-1",
                "scope_kind": "SYSTEM",
                "inherits_into_project": True,
            },
        )
        response = rbac_routes.handle_create_binding(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["binding_id"], "b-1")
    testbase.assert_equal(body["role_name"], "viewer")
    testbase.assert_equal(captured_assign["actor_user_id"], "user-42")
    testbase.assert_equal(
        captured_assign["principal_kind"], PrincipalKind.USER
    )
    testbase.assert_equal(
        captured_assign["scope_kind"], BindingScope.SYSTEM
    )
    testbase.assert_equal(captured_assign["inherits_into_project"], True)
    return


def test_handle_create_binding_returns_400_on_unknown_principal_kind():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: An unknown principal_kind returns 400 problem+json
    with role_name as an extension member.**
    """
    request = _FakeRequest(
        path="/api/v1/rbac/bindings",
        db_session=object(),
        body={
            "role_name": "viewer",
            "principal_kind": "GARBAGE",
            "principal_id": "u-1",
            "scope_kind": "SYSTEM",
        },
    )
    response = rbac_routes.handle_create_binding(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["role_name"], "viewer")
    return


def test_handle_create_binding_returns_404_on_unknown_role_with_extension():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: RoleNotFoundError → 404 problem+json with
    role_name as an extension member.**
    """
    patch = _patch_service_module_attr(
        module_attr="binding_service",
        attr_name="assign_role",
        value=_raises(RoleNotFoundError("no such role")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings",
            db_session=object(),
            body={
                "role_name": "missing-role",
                "principal_kind": "USER",
                "principal_id": "u-1",
                "scope_kind": "SYSTEM",
            },
        )
        response = rbac_routes.handle_create_binding(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["role_name"], "missing-role")
    return


def test_handle_create_binding_returns_400_on_invalid_scope():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: InvalidBindingScopeError → 400 problem+json with
    scope_kind / scope_id extension members.**
    """
    patch = _patch_service_module_attr(
        module_attr="binding_service",
        attr_name="assign_role",
        value=_raises(InvalidBindingScopeError("scope_id required")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings",
            db_session=object(),
            body={
                "role_name": "viewer",
                "principal_kind": "USER",
                "principal_id": "u-1",
                "scope_kind": "PROJECT",
            },
        )
        response = rbac_routes.handle_create_binding(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["scope_kind"], "PROJECT")
    return


def test_handle_create_binding_returns_500_when_view_lookup_fails():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: When the post-create view lookup returns no
    matching row, the handler emits a 500 problem document with
    binding_id extension. Mirrors the flask controller's hard
    fall-through and gives operators the binding id to investigate
    with.**
    """
    binding = _FakeBinding(binding_id="b-orphan")

    def fake_assign(**kwargs: Any) -> Any:
        return binding

    def fake_list(**kwargs: Any) -> Any:
        return []  # empty -- view lookup misses

    patch = create_module_patch(rbac_routes, "binding_service")
    try:
        mock_module = patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute("assign_role", fake_assign)
        mock_module.mock_context().set_attribute("list_bindings", fake_list)
        request = _FakeRequest(
            path="/api/v1/rbac/bindings",
            db_session=object(),
            body={
                "role_name": "viewer",
                "principal_kind": "USER",
                "principal_id": "u-1",
                "scope_kind": "SYSTEM",
            },
        )
        response = rbac_routes.handle_create_binding(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 500)
    body = _decode_body(response)
    testbase.assert_equal(body["binding_id"], "b-orphan")
    return


def test_handle_create_binding_returns_400_on_undecodable_body():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: Undecodable body returns 400, not 500.**
    """
    request = _FakeRequest(
        path="/api/v1/rbac/bindings",
        db_session=object(),
        body_raises=True,
    )
    response = rbac_routes.handle_create_binding(request)
    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# handle_list_bindings
# ---------------------------------------------------------------------------


def test_handle_list_bindings_returns_serialized_views_with_no_filters():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: With no filters, list_bindings returns 200 with
    serialized views; all four filter args forward as None.**
    """
    captured: Dict[str, Any] = {}
    views = [
        _FakeView(binding_id="b-1"),
        _FakeView(binding_id="b-2"),
    ]

    def fake_list(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return views

    patch = _patch_service_module_attr(
        module_attr="binding_service",
        attr_name="list_bindings",
        value=fake_list,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings", db_session=object()
        )
        response = rbac_routes.handle_list_bindings(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(captured["principal_kind"], None)
    testbase.assert_equal(captured["principal_id"], None)
    testbase.assert_equal(captured["scope_kind"], None)
    testbase.assert_equal(captured["scope_id"], None)
    return


def test_handle_list_bindings_propagates_all_four_filters():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: principal_kind / principal_id / scope_kind /
    scope_id query params propagate with enum coercion on the
    enum ones.**
    """
    captured: Dict[str, Any] = {}

    def fake_list(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return []

    patch = _patch_service_module_attr(
        module_attr="binding_service",
        attr_name="list_bindings",
        value=fake_list,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings",
            db_session=object(),
            query={
                "principal_kind": "USER",
                "principal_id": "u-1",
                "scope_kind": "PROJECT",
                "scope_id": "p-1",
            },
        )
        rbac_routes.handle_list_bindings(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(captured["principal_kind"], PrincipalKind.USER)
    testbase.assert_equal(captured["principal_id"], "u-1")
    testbase.assert_equal(captured["scope_kind"], BindingScope.PROJECT)
    testbase.assert_equal(captured["scope_id"], "p-1")
    return


def test_handle_list_bindings_returns_400_on_unknown_principal_kind_filter():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: Unknown principal_kind filter returns 400 problem
    +json with the raw value as an extension member.**
    """
    request = _FakeRequest(
        path="/api/v1/rbac/bindings",
        db_session=object(),
        query={"principal_kind": "GARBAGE"},
    )
    response = rbac_routes.handle_list_bindings(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["principal_kind"], "GARBAGE")
    return


def test_handle_list_bindings_returns_400_on_unknown_scope_kind_filter():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: Unknown scope_kind filter returns 400 problem+json
    with the raw value as an extension member.**
    """
    request = _FakeRequest(
        path="/api/v1/rbac/bindings",
        db_session=object(),
        query={"scope_kind": "GARBAGE"},
    )
    response = rbac_routes.handle_list_bindings(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["scope_kind"], "GARBAGE")
    return


# ---------------------------------------------------------------------------
# handle_revoke_binding
# ---------------------------------------------------------------------------


def test_handle_revoke_binding_returns_200_with_status_revoked():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: Successful revoke returns 200 with
    ``{binding_id, status: revoked}``.**
    """
    captured: Dict[str, Any] = {}

    def fake_revoke(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return None

    patch = _patch_service_module_attr(
        module_attr="binding_service",
        attr_name="revoke_role",
        value=fake_revoke,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings/b-1",
            path_params={"binding_id": "b-1"},
            db_session=object(),
            actor_user_id="user-42",
        )
        response = rbac_routes.handle_revoke_binding(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["binding_id"], "b-1")
    testbase.assert_equal(body["status"], "revoked")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    return


def test_handle_revoke_binding_returns_404_with_binding_id_extension():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: BindingNotFoundError → 404 problem+json with
    binding_id extension.**
    """
    patch = _patch_service_module_attr(
        module_attr="binding_service",
        attr_name="revoke_role",
        value=_raises(BindingNotFoundError("missing")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings/b-missing",
            path_params={"binding_id": "b-missing"},
            db_session=object(),
        )
        response = rbac_routes.handle_revoke_binding(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["binding_id"], "b-missing")
    return


# ---------------------------------------------------------------------------
# handle_check_permission
# ---------------------------------------------------------------------------


def test_handle_check_permission_returns_decision_dict():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: Successful check returns 200 with
    ``{allowed, reason, permission_key}``.**
    """
    decision = _FakeDecision(
        allowed=True, reason="binding present", permission_key="system:read"
    )

    def fake_check(**kwargs: Any) -> Any:
        return decision

    patch = _patch_service_module_attr(
        module_attr="rbac_evaluator",
        attr_name="check_permission",
        value=fake_check,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/check",
            db_session=object(),
            body={"principal_id": "u-1", "permission_key": "system:read"},
        )
        response = rbac_routes.handle_check_permission(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["allowed"], True)
    testbase.assert_equal(body["reason"], "binding present")
    testbase.assert_equal(body["permission_key"], "system:read")
    return


def test_handle_check_permission_returns_400_on_semantic_error():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: SemanticError from the evaluator → 400 problem
    +json with principal_id + permission_key extensions.**
    """
    patch = _patch_service_module_attr(
        module_attr="rbac_evaluator",
        attr_name="check_permission",
        value=_raises(SemanticError("malformed permission key")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/check",
            db_session=object(),
            body={
                "principal_id": "u-1",
                "permission_key": "garbage",
            },
        )
        response = rbac_routes.handle_check_permission(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["principal_id"], "u-1")
    testbase.assert_equal(body["permission_key"], "garbage")
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_rbac_routes_and_calls_it():
    """
    **Feature: 1-rbac T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires register_rbac_routes
    into register_service_extensions.**
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
        "from ccai.pychestrate.webservice.security.rbac.restapi.v1.rbac_routes import"
        in text
    )
    has_call = "register_rbac_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
