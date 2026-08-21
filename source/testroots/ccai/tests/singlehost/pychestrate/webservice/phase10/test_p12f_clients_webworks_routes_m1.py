"""
.. module:: test_p12f_clients_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native clients-admin REST routes.

.. moduleauthor:: Code Craft AI LLC

The clients-admin port has four routes plus three documented
exception types and several enum coercions on both query and
body fields. Tests cover the route matrix, the 503 sweep, the
filter-coercion error paths (with their specific
``requested_status`` / ``requested_liveness_state`` extension
keys that match the flask controller), the revoke flow with
RevocationReason coercion, and the attribute-batch validator's
shape errors.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_module_patch
from ccai.webworks.routing.response import JSONResponse

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_FORBIDDEN,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
)
from ccai.pychestrate.webservice.clients.enums import (
    ClientStatus,
    LivenessState,
    RevocationReason,
)
from ccai.pychestrate.webservice.clients.exceptions import (
    ClientNotFoundError,
    InvalidAttributeValueError,
    UnknownAttributeKindError,
)
from ccai.pychestrate.webservice.clients.restapi.v1 import (
    clients_routes,
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
        auth_principal: Optional[Any] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self._body_raises: bool = body_raises
        self.db_session: Optional[Any] = db_session
        self.actor_user_id: Optional[str] = actor_user_id
        self.auth_principal: Optional[Any] = auth_principal
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
        Stand-in for a :class:`ClientView` with attribute names
        matching ``_view_to_dict``.
    """

    def __init__(
        self,
        *,
        client_id: str,
        project_id: str = "p-1",
        pod_name: str = "pod-x",
        status: ClientStatus = ClientStatus.ACTIVE,
        liveness_state: LivenessState = LivenessState.ALIVE,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.client_id: str = client_id
        self.project_id: str = project_id
        self.pod_name: str = pod_name
        self.status: ClientStatus = status
        self.liveness_state: LivenessState = liveness_state
        self.enrolled_at_iso: str = "2026-05-03T12:00:00+00:00"
        self.last_seen_iso: str = "2026-05-03T12:00:00+00:00"
        self.last_agent_version: str = "1.0.0"
        self.transport_name: str = "websocket"
        self.degraded_at_iso: Optional[str] = None
        self.revision_token: str = "rev-1"
        self.attributes: Dict[str, Any] = attributes if attributes is not None else {}
        return


class _FakePrincipal:
    def __init__(self, *, user_id: str = "user-1") -> None:
        self.user_id: str = user_id
        return


class _FakeDecision:
    def __init__(self, *, allowed: bool, reason: str = "") -> None:
        self.allowed: bool = allowed
        self.reason: str = reason
        return


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        clients_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


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
        Patch ``clients_routes.<name>`` to the supplied callable.
        Returns the Patch so callers deactivate in finally blocks.
    """
    patch = create_module_patch(clients_routes, name)
    mock = patch.activate()
    mock.configure(side_effect=value)
    return patch


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_clients_routes_attaches_four_routes():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: register_clients_routes attaches the same four
    method+path pairs the flask_restx controller exposed.**
    """
    app = _FakeApp()
    clients_routes.register_clients_routes(
        app=app, version_prefix="/api/v1"
    )

    expected_pairs = (
        ("/api/v1/clients", ("GET",)),
        ("/api/v1/clients/{client_id}", ("GET",)),
        ("/api/v1/clients/{client_id}/revoke", ("POST",)),
        ("/api/v1/clients/{client_id}/attributes", ("PUT",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# 503 sweep
# ---------------------------------------------------------------------------


def test_handle_list_returns_503_when_session_missing():
    request = _FakeRequest(path="/api/v1/clients", db_session=None)
    response = clients_routes.handle_list_clients(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_read_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/clients/c-1",
        path_params={"client_id": "c-1"},
        db_session=None,
    )
    response = clients_routes.handle_read_client(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_revoke_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/clients/c-1/revoke",
        path_params={"client_id": "c-1"},
        body={"reason": "ROTATED"},
        db_session=None,
    )
    response = clients_routes.handle_revoke_client(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_update_attributes_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/clients/c-1/attributes",
        path_params={"client_id": "c-1"},
        body={"updates": []},
        db_session=None,
    )
    response = clients_routes.handle_update_client_attributes(request)
    testbase.assert_equal(response.status_code, 503)
    return


# ---------------------------------------------------------------------------
# RBAC sweep
# ---------------------------------------------------------------------------


def test_handle_list_returns_401_when_no_principal():
    """
    **Feature: 3-client-registry (RBAC gating)**
    **Property: GET /clients returns 401 problem+json when no
    AuthPrincipal is bound to the request.**
    """
    request = _FakeRequest(
        path="/api/v1/clients",
        db_session=object(),
        auth_principal=None,
    )
    response = clients_routes.handle_list_clients(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_handle_list_returns_403_when_read_permission_denied():
    """
    **Feature: 3-client-registry (RBAC gating)**
    **Property: GET /clients returns 403 problem+json carrying
    system:clients.read as required_permission when the principal
    lacks the read key.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/clients",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = clients_routes.handle_list_clients(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_FORBIDDEN)
    testbase.assert_equal(
        body["required_permission"], "system:clients.read",
    )
    return


def test_handle_revoke_returns_403_when_write_permission_denied():
    """
    **Feature: 3-client-registry (RBAC gating)**
    **Property: POST /clients/{id}/revoke returns 403 problem+json
    carrying system:clients.write as required_permission when the
    principal lacks the write key.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-1/revoke",
            path_params={"client_id": "c-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"reason": "ROTATED"},
        )
        response = clients_routes.handle_revoke_client(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:clients.write",
    )
    return


def test_handle_update_attributes_returns_401_when_no_principal():
    """
    **Feature: 3-client-registry (RBAC gating)**
    **Property: PUT /clients/{id}/attributes returns 401 when no
    AuthPrincipal is bound to the request.**
    """
    request = _FakeRequest(
        path="/api/v1/clients/c-1/attributes",
        path_params={"client_id": "c-1"},
        db_session=object(),
        auth_principal=None,
        body={"updates": []},
    )
    response = clients_routes.handle_update_client_attributes(request)
    testbase.assert_equal(response.status_code, 401)
    return


# ---------------------------------------------------------------------------
# handle_list_clients
# ---------------------------------------------------------------------------


def test_handle_list_returns_serialized_views_with_no_filters():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: With no filter query params, list returns 200 with
    a serialized list of views; project_id / status /
    liveness_state forward as None to the registry service.**
    """
    captured: Dict[str, Any] = {}
    views = [_FakeView(client_id="c-1"), _FakeView(client_id="c-2")]

    def fake_list(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return views

    patch = _patch_routes_attr(name="list_clients", value=fake_list)
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = clients_routes.handle_list_clients(request)
    finally:
        perm_patch.deactivate()
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(captured["project_id"], None)
    testbase.assert_equal(captured["status"], None)
    testbase.assert_equal(captured["liveness_state"], None)
    return


def test_handle_list_propagates_all_three_filters():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: project_id / status / liveness_state propagate
    through with enum coercion on the latter two.**
    """
    captured: Dict[str, Any] = {}

    def fake_list(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return []

    patch = _patch_routes_attr(name="list_clients", value=fake_list)
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={
                "project_id": "p-7",
                "status": "ACTIVE",
                "liveness_state": "ALIVE",
            },
        )
        clients_routes.handle_list_clients(request)
    finally:
        perm_patch.deactivate()
        patch.deactivate()

    testbase.assert_equal(captured["project_id"], "p-7")
    testbase.assert_equal(captured["status"], ClientStatus.ACTIVE)
    testbase.assert_equal(captured["liveness_state"], LivenessState.ALIVE)
    return


def test_handle_list_returns_400_with_requested_status_extension_on_unknown_status():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: Unknown ``status`` filter returns 400 problem+json
    carrying the raw value as ``requested_status`` -- preserves
    the flask controller's specific extension key (not a generic
    ``status``).**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"status": "GARBAGE"},
        )
        response = clients_routes.handle_list_clients(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    testbase.assert_equal(body["requested_status"], "GARBAGE")
    return


def test_handle_list_returns_400_with_requested_liveness_state_extension():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: Unknown liveness_state filter returns 400 problem
    +json carrying ``requested_liveness_state`` as the extension
    key.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"liveness_state": "GARBAGE"},
        )
        response = clients_routes.handle_list_clients(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["requested_liveness_state"], "GARBAGE")
    return


# ---------------------------------------------------------------------------
# handle_read_client
# ---------------------------------------------------------------------------


def test_handle_read_returns_view_on_match():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: A known client_id returns 200 with the view
    dict.**
    """
    view = _FakeView(client_id="c-1", attributes={"toolchain": "py-3.12"})
    patch = _patch_routes_attr(
        name="get_client", value=lambda **kwargs: view,
    )
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-1",
            path_params={"client_id": "c-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = clients_routes.handle_read_client(request)
    finally:
        perm_patch.deactivate()
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], "c-1")
    testbase.assert_equal(body["attributes"]["toolchain"], "py-3.12")
    return


def test_handle_read_returns_404_with_client_id_extension():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: ClientNotFoundError → 404 problem+json with
    client_id as an extension member.**
    """
    patch = _patch_routes_attr(
        name="get_client", value=_raises(ClientNotFoundError("missing")),
    )
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-missing",
            path_params={"client_id": "c-missing"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = clients_routes.handle_read_client(request)
    finally:
        perm_patch.deactivate()
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["client_id"], "c-missing")
    return


# ---------------------------------------------------------------------------
# handle_revoke_client
# ---------------------------------------------------------------------------


def test_handle_revoke_returns_200_with_actor_propagation():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: Successful revoke returns 200 with
    ``{client_id, status: revoked}``, propagates actor_user_id,
    coerces RevocationReason, and forwards the optional note.**
    """
    captured: Dict[str, Any] = {}

    def fake_revoke(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return None

    patch = _patch_routes_attr(name="revoke_client", value=fake_revoke)
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-1/revoke",
            path_params={"client_id": "c-1"},
            db_session=object(),
            actor_user_id="user-42",
            auth_principal=_FakePrincipal(),
            body={"reason": "ROTATED", "note": "scheduled rotation"},
        )
        response = clients_routes.handle_revoke_client(request)
    finally:
        perm_patch.deactivate()
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], "c-1")
    testbase.assert_equal(body["status"], "revoked")
    testbase.assert_equal(captured["reason"], RevocationReason.ROTATED)
    testbase.assert_equal(captured["revoked_by"], "user-42")
    testbase.assert_equal(captured["note"], "scheduled rotation")
    return


def test_handle_revoke_returns_400_on_unknown_reason():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: An unknown reason raises SemanticError internally,
    which the handler converts to 400 problem+json with the
    client_id extension.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-1/revoke",
            path_params={"client_id": "c-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"reason": "GARBAGE"},
        )
        response = clients_routes.handle_revoke_client(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], "c-1")
    return


def test_handle_revoke_returns_404_on_unknown_client():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: ClientNotFoundError → 404 problem+json with
    client_id extension.**
    """
    patch = _patch_routes_attr(
        name="revoke_client",
        value=_raises(ClientNotFoundError("missing")),
    )
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-missing/revoke",
            path_params={"client_id": "c-missing"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"reason": "ROTATED"},
        )
        response = clients_routes.handle_revoke_client(request)
    finally:
        perm_patch.deactivate()
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], "c-missing")
    return


def test_handle_revoke_returns_400_on_undecodable_body():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: Undecodable body returns 400, not 500.**
    """
    request = _FakeRequest(
        path="/api/v1/clients/c-1/revoke",
        path_params={"client_id": "c-1"},
        db_session=object(),
        body_raises=True,
    )
    response = clients_routes.handle_revoke_client(request)
    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# handle_update_client_attributes
# ---------------------------------------------------------------------------


def test_handle_update_attributes_returns_200_with_kinds_written():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: Successful batch update returns 200 with
    ``{client_id, kinds_written}`` and forwards the optional
    expected_revision_token through.**
    """
    captured: Dict[str, Any] = {}

    def fake_update(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return ["toolchain", "concurrency"]

    patch = _patch_routes_attr(name="update_attributes", value=fake_update)
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-1/attributes",
            path_params={"client_id": "c-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "expected_revision_token": "rev-7",
                "updates": [
                    {"kind": "toolchain", "value": "py-3.12"},
                    {"kind": "concurrency", "value": 4},
                ],
            },
        )
        response = clients_routes.handle_update_client_attributes(request)
    finally:
        perm_patch.deactivate()
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], "c-1")
    testbase.assert_equal(body["kinds_written"], ["toolchain", "concurrency"])
    testbase.assert_equal(captured["expected_revision_token"], "rev-7")
    testbase.assert_equal(len(captured["updates"]), 2)
    testbase.assert_equal(captured["updates"][0].kind, "toolchain")
    return


def test_handle_update_attributes_returns_400_when_updates_is_not_a_list():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: ``updates`` field that is not a list returns 400
    problem+json with the client_id extension.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-1/attributes",
            path_params={"client_id": "c-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"updates": "wrong shape"},
        )
        response = clients_routes.handle_update_client_attributes(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], "c-1")
    return


def test_handle_update_attributes_returns_400_on_empty_kind():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: An update entry with an empty ``kind`` returns 400.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-1/attributes",
            path_params={"client_id": "c-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"updates": [{"kind": "", "value": "x"}]},
        )
        response = clients_routes.handle_update_client_attributes(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_update_attributes_returns_400_when_entry_is_not_an_object():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: A non-object update entry returns 400.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-1/attributes",
            path_params={"client_id": "c-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"updates": ["just-a-string"]},
        )
        response = clients_routes.handle_update_client_attributes(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_update_attributes_returns_400_on_unknown_attribute_kind():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: UnknownAttributeKindError → 400 problem+json with
    client_id extension.**
    """
    patch = _patch_routes_attr(
        name="update_attributes",
        value=_raises(UnknownAttributeKindError("unknown kind")),
    )
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-1/attributes",
            path_params={"client_id": "c-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"updates": [{"kind": "fake_kind", "value": 1}]},
        )
        response = clients_routes.handle_update_client_attributes(request)
    finally:
        perm_patch.deactivate()
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_update_attributes_returns_400_on_invalid_attribute_value():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: InvalidAttributeValueError → 400 problem+json.**
    """
    patch = _patch_routes_attr(
        name="update_attributes",
        value=_raises(InvalidAttributeValueError("bad value")),
    )
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-1/attributes",
            path_params={"client_id": "c-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"updates": [{"kind": "concurrency", "value": "x"}]},
        )
        response = clients_routes.handle_update_client_attributes(request)
    finally:
        perm_patch.deactivate()
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_update_attributes_returns_404_on_unknown_client():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: ClientNotFoundError → 404 problem+json with
    client_id extension.**
    """
    patch = _patch_routes_attr(
        name="update_attributes",
        value=_raises(ClientNotFoundError("missing")),
    )
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/c-missing/attributes",
            path_params={"client_id": "c-missing"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"updates": [{"kind": "k", "value": 1}]},
        )
        response = clients_routes.handle_update_client_attributes(request)
    finally:
        perm_patch.deactivate()
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], "c-missing")
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_clients_routes_and_calls_it():
    """
    **Feature: 3-client-registry T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires
    register_clients_routes into register_service_extensions.**
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
        "from ccai.pychestrate.webservice.clients.restapi.v1.clients_routes import"
        in text
    )
    has_call = "register_clients_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
