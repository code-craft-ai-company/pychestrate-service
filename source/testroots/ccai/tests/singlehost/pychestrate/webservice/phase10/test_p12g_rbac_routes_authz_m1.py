"""
.. module:: test_p12g_rbac_routes_authz_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Authorization-gate tests for the RBAC REST routes.

.. moduleauthor:: Code Craft AI LLC

Closes the gaps identified in the REST-auth-hardening audit. Each
handler in :mod:`rbac_routes` now requires:

* An authenticated caller (``auth_principal`` present → 401 if absent).
* The caller to hold a specific permission key (``system:rbac.read``
  for catalog/check endpoints, ``system:rbac.admin`` for
  create/revoke bindings → 403 if denied).

Tests here cover:

* ``GET /api/v1/rbac/permissions`` → 401 / 403 / 200.
* ``GET /api/v1/rbac/roles`` → 401 / 403 / 200.
* ``POST /api/v1/rbac/bindings`` → 401 / 403 / 201.
* ``DELETE /api/v1/rbac/bindings/{id}`` → 401 / 403 / 200.
* ``POST /api/v1/rbac/check`` → 401 / 403 / 200.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_FORBIDDEN,
    PROBLEM_TYPE_UNAUTHENTICATED,
)
from ccai.pychestrate.webservice.security.rbac.restapi.v1 import rbac_routes


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _FakeQueryParams:
    def __init__(self, *, values: Optional[Dict[str, str]] = None) -> None:
        self._values: Dict[str, str] = values if values is not None else {}
        return

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakePrincipal:
    def __init__(self, *, user_id: str = "caller-1") -> None:
        self.user_id: str = user_id
        self.session_id: str = "sess-caller-1"
        return


class _FakeDecision:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed: bool = allowed
        self.reason: str = "allow" if allowed else "no binding"
        self.permission_key: str = "system:rbac.read"
        return


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, str]] = None,
        body: Any = None,
        db_session: Optional[Any] = None,
        auth_principal: Optional[Any] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        self.actor_user_id: Optional[str] = None
        return

    def json(self) -> Any:
        return self._body


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_evaluator(*, allowed: bool) -> Any:
    """
        Patch ``rbac_routes.rbac_evaluator.check_permission`` to return
        an allowed or denied decision unconditionally.

        :param allowed: Whether the decision should allow.

        :returns: Active patch; caller must call ``.deactivate()``.
    """
    decision = _FakeDecision(allowed=allowed)
    patch = create_module_patch(rbac_routes, "rbac_evaluator")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute(
        "check_permission", lambda **kwargs: decision
    )
    return patch


def _patch_catalog(
        *,
        permissions: Optional[Dict[str, Any]] = None,
        roles: Optional[Dict[str, Any]] = None
    ) -> Any:
    """
        Patch ``rbac_routes.load_catalog_from_registry`` with a minimal
        fake catalog so catalog-read handlers can reach the response
        body.

        :param permissions: Permissions dict to expose.
        :param roles: Roles dict to expose.

        :returns: Active patch; caller must call ``.deactivate()``.
    """

    class _FakeCatalog:
        def __init__(self) -> None:
            self.permissions: Dict[str, Any] = (
                permissions if permissions is not None else {}
            )
            self.roles: Dict[str, Any] = (
                roles if roles is not None else {}
            )
            return

    catalog = _FakeCatalog()
    patch = create_module_patch(rbac_routes, "load_catalog_from_registry")
    mock = patch.activate()
    mock.configure(side_effect=lambda: catalog)
    return patch


def _patch_binding_service_allow() -> Any:
    """
        Patch ``rbac_routes.binding_service`` so the ``assign_role`` call
        returns a fake binding and ``list_bindings`` returns a view that
        matches. Used by the create-binding 201 happy path.

        :returns: Active patch; caller must call ``.deactivate()``.
    """

    class _FakeBinding:
        def __init__(self) -> None:
            self.binding_id: str = "b-new"
            return

    class _FakeView:
        def __init__(self) -> None:
            from ccai.pychestrate.webservice.security.rbac.models import (
                BindingScope,
                PrincipalKind,
            )
            self.binding_id: str = "b-new"
            self.role_name: str = "system-admin"
            self.principal_kind = PrincipalKind.USER
            self.principal_id: str = "target-1"
            self.scope_kind = BindingScope.SYSTEM
            self.scope_id: Optional[str] = None
            self.inherits_into_project: bool = False
            self.created_at_iso: str = "2026-06-01T00:00:00+00:00"
            self.created_by: Optional[str] = None
            return

    binding = _FakeBinding()
    view = _FakeView()
    patch = create_module_patch(rbac_routes, "binding_service")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute(
        "assign_role", lambda **kwargs: binding
    )
    mock_module.mock_context().set_attribute(
        "list_bindings", lambda **kwargs: [view]
    )
    return patch


def _patch_revoke_allow() -> Any:
    """
        Patch ``binding_service.revoke_role`` to return None (success).

        :returns: Active patch; caller must call ``.deactivate()``.
    """
    patch = create_module_patch(rbac_routes, "binding_service")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute(
        "revoke_role", lambda **kwargs: None
    )
    return patch


# ---------------------------------------------------------------------------
# GET /api/v1/rbac/permissions
# ---------------------------------------------------------------------------


def test_list_permissions_returns_401_when_no_principal():
    """
    **Feature: rest-auth-hardening hole #2**
    **Property: GET /api/v1/rbac/permissions returns 401 when
    no auth_principal is on the request.**
    """
    request = _FakeRequest(
        path="/api/v1/rbac/permissions",
        db_session=object(),
        auth_principal=None,
    )
    response = rbac_routes.handle_list_permissions(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_permissions_returns_403_when_permission_denied():
    """
    **Feature: rest-auth-hardening hole #2**
    **Property: GET /api/v1/rbac/permissions returns 403 when
    the caller is authenticated but does not hold
    system:rbac.read.**
    """
    eval_patch = _patch_evaluator(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/permissions",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = rbac_routes.handle_list_permissions(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_FORBIDDEN)
    return


def test_list_permissions_returns_200_when_authorized():
    """
    **Feature: rest-auth-hardening hole #2**
    **Property: GET /api/v1/rbac/permissions returns 200 when
    the caller holds system:rbac.read.**
    """
    eval_patch = _patch_evaluator(allowed=True)
    cat_patch = _patch_catalog(permissions={}, roles={})
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/permissions",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = rbac_routes.handle_list_permissions(request)
    finally:
        eval_patch.deactivate()
        cat_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    return


# ---------------------------------------------------------------------------
# GET /api/v1/rbac/roles
# ---------------------------------------------------------------------------


def test_list_roles_returns_401_when_no_principal():
    """
    **Feature: rest-auth-hardening hole #2**
    **Property: GET /api/v1/rbac/roles returns 401 when no
    auth_principal is present.**
    """
    request = _FakeRequest(
        path="/api/v1/rbac/roles",
        db_session=object(),
        auth_principal=None,
    )
    response = rbac_routes.handle_list_roles(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_list_roles_returns_403_when_permission_denied():
    """
    **Feature: rest-auth-hardening hole #2**
    **Property: GET /api/v1/rbac/roles returns 403 when the
    caller does not hold system:rbac.read.**
    """
    eval_patch = _patch_evaluator(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/roles",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = rbac_routes.handle_list_roles(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 403)
    return


def test_list_roles_returns_200_when_authorized():
    """
    **Feature: rest-auth-hardening hole #2**
    **Property: GET /api/v1/rbac/roles returns 200 when the
    caller holds system:rbac.read.**
    """
    eval_patch = _patch_evaluator(allowed=True)
    cat_patch = _patch_catalog(permissions={}, roles={})
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/roles",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = rbac_routes.handle_list_roles(request)
    finally:
        eval_patch.deactivate()
        cat_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    return


# ---------------------------------------------------------------------------
# POST /api/v1/rbac/bindings
# ---------------------------------------------------------------------------


def test_create_binding_returns_401_when_no_principal():
    """
    **Feature: rest-auth-hardening hole #1**
    **Property: POST /api/v1/rbac/bindings returns 401 when
    no auth_principal is on the request.**
    """
    request = _FakeRequest(
        path="/api/v1/rbac/bindings",
        db_session=object(),
        auth_principal=None,
        body={
            "role_name": "system-admin",
            "principal_kind": "USER",
            "principal_id": "target-1",
            "scope_kind": "SYSTEM",
        },
    )
    response = rbac_routes.handle_create_binding(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_create_binding_returns_403_when_permission_denied():
    """
    **Feature: rest-auth-hardening hole #1**
    **Property: POST /api/v1/rbac/bindings returns 403 when the
    caller is authenticated but does not hold system:rbac.admin.
    Any actor — even one without a session — must NOT be able to
    grant system-admin.**
    """
    eval_patch = _patch_evaluator(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "role_name": "system-admin",
                "principal_kind": "USER",
                "principal_id": "target-1",
                "scope_kind": "SYSTEM",
            },
        )
        response = rbac_routes.handle_create_binding(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_FORBIDDEN)
    return


def test_create_binding_returns_201_when_authorized():
    """
    **Feature: rest-auth-hardening hole #1**
    **Property: POST /api/v1/rbac/bindings returns 201 when the
    caller holds system:rbac.admin.**
    """
    eval_patch = _patch_evaluator(allowed=True)
    svc_patch = _patch_binding_service_allow()
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "role_name": "system-admin",
                "principal_kind": "USER",
                "principal_id": "target-1",
                "scope_kind": "SYSTEM",
            },
        )
        response = rbac_routes.handle_create_binding(request)
    finally:
        eval_patch.deactivate()
        svc_patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["binding_id"], "b-new")
    return


# ---------------------------------------------------------------------------
# GET /api/v1/rbac/bindings  (list)
# ---------------------------------------------------------------------------


def test_list_bindings_returns_401_when_no_principal():
    """
    **Feature: rest-auth-hardening sibling (list_bindings)**
    **Property: GET /api/v1/rbac/bindings returns 401 when no
    auth_principal is on the request. The binding list reveals which
    principals hold which roles, so it is gated the same as other
    RBAC read endpoints.**
    """
    request = _FakeRequest(
        path="/api/v1/rbac/bindings",
        db_session=object(),
        auth_principal=None,
    )
    response = rbac_routes.handle_list_bindings(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_bindings_returns_403_when_permission_denied():
    """
    **Feature: rest-auth-hardening sibling (list_bindings)**
    **Property: GET /api/v1/rbac/bindings returns 403 when the
    caller is authenticated but does not hold system:rbac.read.**
    """
    eval_patch = _patch_evaluator(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = rbac_routes.handle_list_bindings(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_FORBIDDEN)
    return


def test_list_bindings_returns_200_when_authorized():
    """
    **Feature: rest-auth-hardening sibling (list_bindings)**
    **Property: GET /api/v1/rbac/bindings returns 200 with the
    bindings list when the caller holds system:rbac.read.**
    """
    eval_patch = _patch_evaluator(allowed=True)
    patch = create_module_patch(rbac_routes, "binding_service")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute(
        "list_bindings", lambda **kwargs: []
    )
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = rbac_routes.handle_list_bindings(request)
    finally:
        eval_patch.deactivate()
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 0)
    return


# ---------------------------------------------------------------------------
# DELETE /api/v1/rbac/bindings/{binding_id}
# ---------------------------------------------------------------------------


def test_revoke_binding_returns_401_when_no_principal():
    """
    **Feature: rest-auth-hardening hole #1**
    **Property: DELETE /api/v1/rbac/bindings/{id} returns 401
    when no auth_principal is present.**
    """
    request = _FakeRequest(
        path="/api/v1/rbac/bindings/b-1",
        path_params={"binding_id": "b-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = rbac_routes.handle_revoke_binding(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_revoke_binding_returns_403_when_permission_denied():
    """
    **Feature: rest-auth-hardening hole #1**
    **Property: DELETE /api/v1/rbac/bindings/{id} returns 403
    when the caller does not hold system:rbac.admin.**
    """
    eval_patch = _patch_evaluator(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings/b-1",
            path_params={"binding_id": "b-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = rbac_routes.handle_revoke_binding(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 403)
    return


def test_revoke_binding_returns_200_when_authorized():
    """
    **Feature: rest-auth-hardening hole #1**
    **Property: DELETE /api/v1/rbac/bindings/{id} returns 200 with
    ``{binding_id, status: revoked}`` when the caller holds
    system:rbac.admin.**
    """
    eval_patch = _patch_evaluator(allowed=True)
    svc_patch = _patch_revoke_allow()
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/bindings/b-1",
            path_params={"binding_id": "b-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = rbac_routes.handle_revoke_binding(request)
    finally:
        eval_patch.deactivate()
        svc_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["binding_id"], "b-1")
    testbase.assert_equal(body["status"], "revoked")
    return


# ---------------------------------------------------------------------------
# POST /api/v1/rbac/check
# ---------------------------------------------------------------------------


def test_check_permission_returns_401_when_no_principal():
    """
    **Feature: rest-auth-hardening hole #3**
    **Property: POST /api/v1/rbac/check returns 401 when no
    auth_principal is on the request.**
    """
    request = _FakeRequest(
        path="/api/v1/rbac/check",
        db_session=object(),
        auth_principal=None,
        body={"principal_id": "u-1", "permission_key": "system:rbac.read"},
    )
    response = rbac_routes.handle_check_permission(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_check_permission_returns_403_when_caller_lacks_rbac_read():
    """
    **Feature: rest-auth-hardening hole #3**
    **Property: POST /api/v1/rbac/check returns 403 when the caller
    does not hold system:rbac.read. The supplied principal_id is
    never evaluated.**
    """
    eval_patch = _patch_evaluator(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/check",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "principal_id": "u-1",
                "permission_key": "system:rbac.admin",
            },
        )
        response = rbac_routes.handle_check_permission(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 403)
    return


def test_check_permission_returns_200_when_caller_authorized():
    """
    **Feature: rest-auth-hardening hole #3**
    **Property: POST /api/v1/rbac/check returns 200 with the
    decision when the caller holds system:rbac.read. The evaluator
    is called twice (once to gate the caller, once to evaluate the
    target); both return allowed=True here.**
    """
    allowed_decision = _FakeDecision(allowed=True)
    call_count: Dict[str, int] = {"n": 0}

    def fake_check(**kwargs: Any) -> Any:
        call_count["n"] += 1
        return allowed_decision

    patch = create_module_patch(rbac_routes, "rbac_evaluator")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute("check_permission", fake_check)
    try:
        request = _FakeRequest(
            path="/api/v1/rbac/check",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "principal_id": "u-1",
                "permission_key": "system:rbac.read",
            },
        )
        response = rbac_routes.handle_check_permission(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["allowed"], True)
    # Evaluator must have been called exactly twice: caller gate + business check.
    testbase.assert_equal(call_count["n"], 2)
    return
