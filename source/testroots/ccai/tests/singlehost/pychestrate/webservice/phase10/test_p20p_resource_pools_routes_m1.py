"""
.. module:: test_p20p_resource_pools_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the resource-pools REST endpoints (PR p20p).

.. moduleauthor:: Code Craft AI LLC

Covers the resource-pool operations attached by
``register_resource_pools_routes``:

* GET    /api/v1/resource-pools
* POST   /api/v1/resource-pools
* GET    /api/v1/resource-pools/{pool_id}
* DELETE /api/v1/resource-pools/{pool_id}
* GET    /api/v1/resource-pools/{pool_id}/resources
* POST   /api/v1/resource-pools/{pool_id}/resources
* DELETE /api/v1/resource-pools/{pool_id}/resources/{resource_id}
* GET    /api/v1/resource-pools/{pool_id}/reservations
* POST   /api/v1/resource-pools/{pool_id}/reservations
* DELETE /api/v1/resource-pools/{pool_id}/reservations/{reservation_id}

Auth (401/403), session boundary (503), not-found (404), conflict
(409), malformed body (422), pagination, and happy-path 200/201/204
each get explicit coverage.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from ccai.pychestrate.webservice.resources.checkout.errors import (
    ReservationConflictError,
    ReservationNotFoundError,
)
from ccai.pychestrate.webservice.resources.checkout.models import (
    ReservationMode,
    ReservationState,
)
from ccai.pychestrate.webservice.resources.inventory.models import (
    ResourceState,
)
from ccai.pychestrate.webservice.resources.pools.errors import (
    PoolEmptyError,
    PoolMemberConflictError,
    PoolNotFoundError,
)
from ccai.pychestrate.webservice.resources.restapi.v1 import (
    resource_pools_routes,
)


# ---------------------------------------------------------------------------
# Fakes
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
            db_session: Optional[Any] = None,
            auth_principal: Optional[Any] = None
        ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        return

    def json(self) -> Any:
        rtnval = self._body
        return rtnval


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


class _FakePrincipal:
    def __init__(self, *, user_id: str = "user-1") -> None:
        self.user_id: str = user_id
        return


class _FakeDecision:
    def __init__(self, *, allowed: bool, reason: str = "") -> None:
        self.allowed: bool = allowed
        self.reason: str = reason
        return


class _FakeMemberRow:
    def __init__(
            self,
            *,
            membership_id: str = "member-1",
            pool_id: str = "11111111-1111-4111-8111-000000000001",
            resource_id: str = "22222222-2222-4222-8222-000000000001"
        ) -> None:
        self.membership_id: str = membership_id
        self.pool_id: str = pool_id
        self.resource_id: str = resource_id
        self.added_at: datetime = datetime(
            2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc,
        )
        return


class _FakeResourceRow:
    def __init__(
            self,
            *,
            resource_id: str = "22222222-2222-4222-8222-000000000001",
            display_name: str = "lab-device",
            kind: str = "device",
            state: Any = None
        ) -> None:
        self.resource_id: str = resource_id
        self.display_name: str = display_name
        self.kind: str = kind
        self.state: Any = (
            state if state is not None else ResourceState.AVAILABLE
        )
        return


class _FakeHealthRow:
    def __init__(
            self,
            *,
            resource_id: str = "22222222-2222-4222-8222-000000000001",
            last_outcome: str = "pass"
        ) -> None:
        self.resource_id: str = resource_id
        self.last_outcome: str = last_outcome
        return


def _patch_member_enrichment(
        *,
        resource_row: Any = None,
        health_row: Any = None
    ) -> Any:
    """
        Patch the inventory + health repository lookups the
        member serializer joins through, returning the two patch
        handles as ``(inventory_patch, health_patch)``.
    """
    inventory_patch = create_module_patch(
        resource_pools_routes.inventory_repository, "find_by_id",
    )
    inventory_mock = inventory_patch.activate()
    inventory_mock.configure(side_effect=lambda **kwargs: resource_row)

    health_patch = create_module_patch(
        resource_pools_routes.health_repository, "find_by_resource",
    )
    health_mock = health_patch.activate()
    health_mock.configure(side_effect=lambda **kwargs: health_row)

    rtnval = (inventory_patch, health_patch)
    return rtnval


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        resource_pools_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _make_pool_view(
        *,
        pool_id: str = "11111111-1111-4111-8111-000000000001",
        project_id: str = "33333333-3333-4333-8333-000000000001",
        name: str = "lab-pool",
        member_count: int = 0
    ) -> Any:
    rtnval = resource_pools_routes.pools_service.PoolView(
        pool_id=pool_id,
        project_id=project_id,
        name=name,
        description="",
        capability_tags=("gpu",),
        member_count=member_count,
        created_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
    )
    return rtnval


def _make_reservation_view(
        *,
        reservation_id: str = "44444444-4444-4444-8444-000000000001",
        resource_id: str = "22222222-2222-4222-8222-000000000001",
        state: Any = None
    ) -> Any:
    resolved_state = state if state is not None else ReservationState.GRANTED
    rtnval = resource_pools_routes.checkout_service.ReservationView(
        reservation_id=reservation_id,
        project_id="33333333-3333-4333-8333-000000000001",
        resource_id=resource_id,
        requested_by=None,
        mode=ReservationMode.EXCLUSIVE,
        state=resolved_state,
        note="",
        requested_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
        granted_at=datetime(2026, 5, 20, 12, 0, 1, tzinfo=timezone.utc),
        released_at=None,
        rejection_reason=None,
    )
    return rtnval


def _make_candidate(*, resource_id: str = "22222222-2222-4222-8222-000000000001") -> Any:
    rtnval = resource_pools_routes.pools_service.PoolCandidate(
        resource_id=resource_id,
        pool_id="11111111-1111-4111-8111-000000000001",
        added_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_resource_pools_routes_attaches_ten_endpoints():
    """
    **Feature: 4-resources PR p20p**
    **Property: register_resource_pools_routes attaches the ten
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    resource_pools_routes.register_resource_pools_routes(
        app=app, version_prefix="/api/v1",
    )
    expected_pairs = (
        ("/api/v1/resource-pools", ("GET",)),
        ("/api/v1/resource-pools", ("POST",)),
        ("/api/v1/resource-pools/{pool_id}", ("GET",)),
        ("/api/v1/resource-pools/{pool_id}", ("DELETE",)),
        ("/api/v1/resource-pools/{pool_id}/resources", ("GET",)),
        ("/api/v1/resource-pools/{pool_id}/resources", ("POST",)),
        (
            "/api/v1/resource-pools/{pool_id}/resources/{resource_id}",
            ("DELETE",),
        ),
        ("/api/v1/resource-pools/{pool_id}/reservations", ("GET",)),
        ("/api/v1/resource-pools/{pool_id}/reservations", ("POST",)),
        (
            "/api/v1/resource-pools/{pool_id}/reservations/{reservation_id}",
            ("DELETE",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET /resource-pools -- auth + session sweep
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resource-pools returns 503 when no db_session is
    bound.**
    """
    request = _FakeRequest(
        path="/api/v1/resource-pools",
        db_session=None,
    )
    response = resource_pools_routes.handle_list_resource_pools(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resource-pools returns 401 when no AuthPrincipal
    is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/resource-pools",
        db_session=object(),
        auth_principal=None,
    )
    response = resource_pools_routes.handle_list_resource_pools(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resource-pools returns 403 when the principal
    lacks system:resource_pools.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_list_resource_pools(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:resource_pools.read",
    )
    return


def test_list_returns_400_when_project_id_missing():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resource-pools returns 400 when the required
    project_id query param is absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_list_resource_pools(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    return


def test_list_returns_page_envelope_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resource-pools returns a {items, meta} page with
    ResourcePool-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    list_patch = create_module_patch(
        resource_pools_routes.pools_service, "list_pools",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [_make_pool_view(pool_id="11111111-1111-4111-8111-000000000001")],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"project_id": "33333333-3333-4333-8333-000000000001", "page": "1", "per_page": "10"},
        )
        response = resource_pools_routes.handle_list_resource_pools(request)
    finally:
        list_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["pool_id"], "11111111-1111-4111-8111-000000000001")
    testbase.assert_equal(body["meta"]["page"], 1)
    testbase.assert_equal(body["meta"]["total"], 1)
    return


def test_list_paginates_window():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resource-pools applies the page window over the
    project's pools.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    list_patch = create_module_patch(
        resource_pools_routes.pools_service, "list_pools",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [
            _make_pool_view(pool_id="11111111-1111-4111-8111-000000000001"),
            _make_pool_view(pool_id="11111111-1111-4111-8111-000000000002"),
            _make_pool_view(pool_id="11111111-1111-4111-8111-000000000003"),
        ],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"project_id": "33333333-3333-4333-8333-000000000001", "page": "2", "per_page": "2"},
        )
        response = resource_pools_routes.handle_list_resource_pools(request)
    finally:
        list_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["pool_id"], "11111111-1111-4111-8111-000000000003")
    testbase.assert_equal(body["meta"]["total"], 3)
    return


# ---------------------------------------------------------------------------
# POST /resource-pools
# ---------------------------------------------------------------------------


def test_create_returns_422_on_missing_body():
    """
    **Feature: 4-resources PR p20p**
    **Property: POST resource-pools returns 422 when the body is
    missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = resource_pools_routes.handle_create_resource_pool(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_create_returns_422_on_missing_name():
    """
    **Feature: 4-resources PR p20p**
    **Property: POST resource-pools returns 422 when name is
    absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"project_id": "33333333-3333-4333-8333-000000000001"},
        )
        response = resource_pools_routes.handle_create_resource_pool(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal("name" in body["missing_fields"], True)
    return


def test_create_returns_409_on_duplicate_name():
    """
    **Feature: 4-resources PR p20p**
    **Property: POST resource-pools returns 409 when the pool name
    already exists in the project.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    create_patch = create_module_patch(
        resource_pools_routes.pools_service, "create_pool",
    )
    create_mock = create_patch.activate()

    def _raise(**kwargs):
        raise PoolMemberConflictError("dup")

    create_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"project_id": "33333333-3333-4333-8333-000000000001", "name": "lab-pool"},
        )
        response = resource_pools_routes.handle_create_resource_pool(request)
    finally:
        create_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    return


def test_create_returns_201_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: POST resource-pools returns 201 with the ResourcePool
    shape on a valid body.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    create_patch = create_module_patch(
        resource_pools_routes.pools_service, "create_pool",
    )
    create_mock = create_patch.activate()
    create_mock.configure(
        side_effect=lambda **kwargs: _make_pool_view(pool_id="11111111-1111-4111-8111-00000000000e"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "project_id": "33333333-3333-4333-8333-000000000001",
                "name": "lab-pool",
                "capability_tags": ["gpu"],
            },
        )
        response = resource_pools_routes.handle_create_resource_pool(request)
    finally:
        create_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["pool_id"], "11111111-1111-4111-8111-00000000000e")
    return


def test_create_returns_403_when_permission_denied():
    """
    **Feature: 4-resources PR p20p**
    **Property: POST resource-pools returns 403 when the principal
    lacks system:resource_pools.write.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"project_id": "33333333-3333-4333-8333-000000000001", "name": "lab-pool"},
        )
        response = resource_pools_routes.handle_create_resource_pool(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:resource_pools.write",
    )
    return


# ---------------------------------------------------------------------------
# GET /resource-pools/{pool_id}
# ---------------------------------------------------------------------------


def test_read_returns_404_when_pool_missing():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resource-pools/{id} returns 404 when the pool is
    not found.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        resource_pools_routes.pools_service, "get_pool",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs):
        raise PoolNotFoundError("missing")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-x",
            path_params={"pool_id": "11111111-1111-4111-8111-00000000000a"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_read_resource_pool(request)
    finally:
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["pool_id"], "11111111-1111-4111-8111-00000000000a")
    return


def test_read_returns_200_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resource-pools/{id} returns 200 with the
    ResourcePool shape.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        resource_pools_routes.pools_service, "get_pool",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_pool_view(
            pool_id="11111111-1111-4111-8111-000000000007", member_count=3,
        ),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-7",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000007"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_read_resource_pool(request)
    finally:
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["pool_id"], "11111111-1111-4111-8111-000000000007")
    testbase.assert_equal(body["member_count"], 3)
    return


# ---------------------------------------------------------------------------
# DELETE /resource-pools/{pool_id}
# ---------------------------------------------------------------------------


def test_delete_returns_404_when_pool_missing():
    """
    **Feature: 4-resources PR p20p**
    **Property: DELETE resource-pools/{id} returns 404 when the pool
    does not exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    find_patch = create_module_patch(
        resource_pools_routes.pools_repository, "find_pool_by_id",
    )
    find_mock = find_patch.activate()
    find_mock.configure(side_effect=lambda **kwargs: None)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-x",
            path_params={"pool_id": "11111111-1111-4111-8111-00000000000a"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_delete_resource_pool(request)
    finally:
        find_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_delete_returns_204_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: DELETE resource-pools/{id} returns 204 when the pool
    is deleted.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    find_patch = create_module_patch(
        resource_pools_routes.pools_repository, "find_pool_by_id",
    )
    find_mock = find_patch.activate()
    find_mock.configure(side_effect=lambda **kwargs: object())
    delete_patch = create_module_patch(
        resource_pools_routes.pools_repository, "delete_pool",
    )
    delete_mock = delete_patch.activate()
    delete_mock.configure(side_effect=lambda **kwargs: None)

    class _Session:
        def commit(self) -> None:
            return

    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001"},
            db_session=_Session(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_delete_resource_pool(request)
    finally:
        delete_patch.deactivate()
        find_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 204)
    return


# ---------------------------------------------------------------------------
# /resource-pools/{pool_id}/resources
# ---------------------------------------------------------------------------


def test_list_pool_resources_returns_page_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET pool resources returns a {items, meta} page of
    member rows enriched with the joined resource's name / kind /
    state and current health outcome.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        resource_pools_routes.pools_service, "get_pool",
    )
    get_mock = get_patch.activate()
    get_mock.configure(side_effect=lambda **kwargs: _make_pool_view())
    members_patch = create_module_patch(
        resource_pools_routes.pools_repository, "list_members",
    )
    members_mock = members_patch.activate()
    members_mock.configure(
        side_effect=lambda **kwargs: [_FakeMemberRow(resource_id="22222222-2222-4222-8222-000000000001")],
    )
    inventory_patch, health_patch = _patch_member_enrichment(
        resource_row=_FakeResourceRow(resource_id="22222222-2222-4222-8222-000000000001"),
        health_row=_FakeHealthRow(resource_id="22222222-2222-4222-8222-000000000001"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1/resources",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_list_pool_resources(request)
    finally:
        health_patch.deactivate()
        inventory_patch.deactivate()
        members_patch.deactivate()
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["resource_id"], "22222222-2222-4222-8222-000000000001")
    testbase.assert_equal(body["items"][0]["resource_name"], "lab-device")
    testbase.assert_equal(body["items"][0]["resource_kind"], "device")
    testbase.assert_equal(body["items"][0]["resource_state"], "available")
    testbase.assert_equal(body["items"][0]["resource_health"], "pass")
    return


def test_list_pool_resources_tolerates_missing_enrichment_rows():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET pool resources serves null enrichment fields
    when the inventory / health rows are unavailable instead of
    failing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        resource_pools_routes.pools_service, "get_pool",
    )
    get_mock = get_patch.activate()
    get_mock.configure(side_effect=lambda **kwargs: _make_pool_view())
    members_patch = create_module_patch(
        resource_pools_routes.pools_repository, "list_members",
    )
    members_mock = members_patch.activate()
    members_mock.configure(
        side_effect=lambda **kwargs: [_FakeMemberRow(resource_id="22222222-2222-4222-8222-000000000001")],
    )
    inventory_patch, health_patch = _patch_member_enrichment(
        resource_row=None,
        health_row=None,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1/resources",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_list_pool_resources(request)
    finally:
        health_patch.deactivate()
        inventory_patch.deactivate()
        members_patch.deactivate()
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["resource_name"], None)
    testbase.assert_equal(body["items"][0]["resource_kind"], None)
    testbase.assert_equal(body["items"][0]["resource_state"], None)
    testbase.assert_equal(body["items"][0]["resource_health"], None)
    return


def test_add_pool_resource_returns_404_when_pool_missing():
    """
    **Feature: 4-resources PR p20p**
    **Property: POST pool resources returns 404 when the pool does
    not exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    add_patch = create_module_patch(
        resource_pools_routes.pools_service, "add_member",
    )
    add_mock = add_patch.activate()

    def _raise(**kwargs):
        raise PoolNotFoundError("missing")

    add_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-x/resources",
            path_params={"pool_id": "11111111-1111-4111-8111-00000000000a"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"resource_id": "22222222-2222-4222-8222-000000000001"},
        )
        response = resource_pools_routes.handle_add_pool_resource(request)
    finally:
        add_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_add_pool_resource_returns_201_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: POST pool resources returns 201 with the membership
    dict.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    add_patch = create_module_patch(
        resource_pools_routes.pools_service, "add_member",
    )
    add_mock = add_patch.activate()
    add_mock.configure(
        side_effect=lambda **kwargs: _FakeMemberRow(resource_id="22222222-2222-4222-8222-000000000009"),
    )
    inventory_patch, health_patch = _patch_member_enrichment(
        resource_row=_FakeResourceRow(resource_id="22222222-2222-4222-8222-000000000009"),
        health_row=None,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1/resources",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"resource_id": "22222222-2222-4222-8222-000000000009"},
        )
        response = resource_pools_routes.handle_add_pool_resource(request)
    finally:
        health_patch.deactivate()
        inventory_patch.deactivate()
        add_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["resource_id"], "22222222-2222-4222-8222-000000000009")
    testbase.assert_equal(body["resource_name"], "lab-device")
    testbase.assert_equal(body["resource_health"], None)
    return


def test_remove_pool_resource_returns_204_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: DELETE pool resource returns 204 (idempotent
    removal).**
    """
    perm_patch = _patch_check_permission(allowed=True)
    remove_patch = create_module_patch(
        resource_pools_routes.pools_service, "remove_member",
    )
    remove_mock = remove_patch.activate()
    remove_mock.configure(side_effect=lambda **kwargs: None)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1/resources/res-1",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001", "resource_id": "22222222-2222-4222-8222-000000000001"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_remove_pool_resource(request)
    finally:
        remove_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 204)
    return


# ---------------------------------------------------------------------------
# /resource-pools/{pool_id}/reservations
# ---------------------------------------------------------------------------


def test_list_reservations_returns_aggregated_page():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET pool reservations aggregates reservations across
    pool member resources into one page.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        resource_pools_routes.pools_service, "get_pool",
    )
    get_mock = get_patch.activate()
    get_mock.configure(side_effect=lambda **kwargs: _make_pool_view())
    members_patch = create_module_patch(
        resource_pools_routes.pools_repository, "list_members",
    )
    members_mock = members_patch.activate()
    members_mock.configure(
        side_effect=lambda **kwargs: [_FakeMemberRow(resource_id="22222222-2222-4222-8222-000000000001")],
    )
    rsv_patch = create_module_patch(
        resource_pools_routes.checkout_service,
        "list_reservations_for_resource",
    )
    rsv_mock = rsv_patch.activate()
    rsv_mock.configure(
        side_effect=lambda **kwargs: [_make_reservation_view(reservation_id="44444444-4444-4444-8444-000000000001")],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1/reservations",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_list_pool_reservations(request)
    finally:
        rsv_patch.deactivate()
        members_patch.deactivate()
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["reservation_id"], "44444444-4444-4444-8444-000000000001")
    return


def test_create_reservation_returns_409_when_pool_empty():
    """
    **Feature: 4-resources PR p20p**
    **Property: POST pool reservations returns 409 when no pool
    member is in an eligible state.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    pick_patch = create_module_patch(
        resource_pools_routes.pools_service, "pick_candidate",
    )
    pick_mock = pick_patch.activate()

    def _raise(**kwargs):
        raise PoolEmptyError("empty")

    pick_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1/reservations",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"project_id": "33333333-3333-4333-8333-000000000001"},
        )
        response = resource_pools_routes.handle_create_pool_reservation(request)
    finally:
        pick_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["reason"], "pool_empty")
    return


def test_create_reservation_returns_409_when_conflict_rejected():
    """
    **Feature: 4-resources PR p20p**
    **Property: POST pool reservations returns 409 when the conflict
    evaluator vetoes the reserve.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    pick_patch = create_module_patch(
        resource_pools_routes.pools_service, "pick_candidate",
    )
    pick_mock = pick_patch.activate()
    pick_mock.configure(side_effect=lambda **kwargs: _make_candidate())
    reserve_patch = create_module_patch(
        resource_pools_routes.checkout_service, "reserve",
    )
    reserve_mock = reserve_patch.activate()

    def _raise(**kwargs):
        raise ReservationConflictError("vetoed")

    reserve_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1/reservations",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"project_id": "33333333-3333-4333-8333-000000000001", "mode": "exclusive"},
        )
        response = resource_pools_routes.handle_create_pool_reservation(request)
    finally:
        reserve_patch.deactivate()
        pick_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["reason"], "conflict_rejected")
    return


def test_create_reservation_returns_422_on_bad_mode():
    """
    **Feature: 4-resources PR p20p**
    **Property: POST pool reservations returns 422 when mode is not
    a valid reservation mode.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1/reservations",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"project_id": "33333333-3333-4333-8333-000000000001", "mode": "bogus"},
        )
        response = resource_pools_routes.handle_create_pool_reservation(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    return


def test_create_reservation_returns_201_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: POST pool reservations returns 201 with the
    Reservation shape after picking + reserving a member.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    pick_patch = create_module_patch(
        resource_pools_routes.pools_service, "pick_candidate",
    )
    pick_mock = pick_patch.activate()
    pick_mock.configure(
        side_effect=lambda **kwargs: _make_candidate(resource_id="22222222-2222-4222-8222-000000000003"),
    )
    reserve_patch = create_module_patch(
        resource_pools_routes.checkout_service, "reserve",
    )
    reserve_mock = reserve_patch.activate()
    reserve_mock.configure(
        side_effect=lambda **kwargs: _make_reservation_view(
            reservation_id="44444444-4444-4444-8444-00000000000e", resource_id="22222222-2222-4222-8222-000000000003",
        ),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1/reservations",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"project_id": "33333333-3333-4333-8333-000000000001"},
        )
        response = resource_pools_routes.handle_create_pool_reservation(request)
    finally:
        reserve_patch.deactivate()
        pick_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["reservation_id"], "44444444-4444-4444-8444-00000000000e")
    testbase.assert_equal(body["resource_id"], "22222222-2222-4222-8222-000000000003")
    testbase.assert_equal(body["state"], "granted")
    return


def test_release_reservation_returns_404_when_missing():
    """
    **Feature: 4-resources PR p20p**
    **Property: DELETE pool reservation returns 404 when the
    reservation does not exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    release_patch = create_module_patch(
        resource_pools_routes.checkout_service, "release",
    )
    release_mock = release_patch.activate()

    def _raise(**kwargs):
        raise ReservationNotFoundError("missing")

    release_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1/reservations/rsv-x",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001", "reservation_id": "44444444-4444-4444-8444-00000000000a"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_release_pool_reservation(
            request,
        )
    finally:
        release_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_release_reservation_returns_204_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: DELETE pool reservation returns 204 on release.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    release_patch = create_module_patch(
        resource_pools_routes.checkout_service, "release",
    )
    release_mock = release_patch.activate()
    release_mock.configure(
        side_effect=lambda **kwargs: _make_reservation_view(
            state=ReservationState.RELEASED,
        ),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resource-pools/pool-1/reservations/rsv-1",
            path_params={"pool_id": "11111111-1111-4111-8111-000000000001", "reservation_id": "44444444-4444-4444-8444-000000000001"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resource_pools_routes.handle_release_pool_reservation(
            request,
        )
    finally:
        release_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 204)
    return


# ---------------------------------------------------------------------------
# Malformed ids (audit finding RES-38)
# ---------------------------------------------------------------------------


_A_POOL_ID = "11111111-1111-4111-8111-000000000001"
_A_PROJECT_ID = "33333333-3333-4333-8333-000000000001"


def _call_authorised(
        *,
        handler: Callable,
        path_params: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, str]] = None,
        body: Any = None
    ) -> Any:
    """
        Call ``handler`` as an authorised caller. Returns
        ``(status_code, decoded_body)``.
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        response = handler(_FakeRequest(
            path="/api/v1/resource-pools",
            path_params=path_params,
            query=query,
            body=body,
            db_session=object(),
            auth_principal=_FakePrincipal(),
        ))
    finally:
        perm_patch.deactivate()
    rtnval = (response.status_code, _decode_body(response))
    return rtnval


def test_read_pool_with_a_malformed_id_is_a_404_problem():
    """
    **Feature: resources (RES-38 malformed ids)**
    **Property: GET resource-pools/not-a-uuid answers a 404 problem
    document instead of a 500.**
    """
    status, body = _call_authorised(
        handler=resource_pools_routes.handle_read_resource_pool, path_params={"pool_id": "not-a-uuid"},
    )

    testbase.assert_equal((status, body["type"], body["pool_id"]), (404, PROBLEM_TYPE_NOT_FOUND, "not-a-uuid"))
    return


def test_list_pools_with_a_malformed_project_id_is_a_400_problem():
    """
    **Feature: resources (RES-38 malformed ids)**
    **Property: GET resource-pools?project_id=not-a-uuid answers 400
    naming the query parameter.**
    """
    status, body = _call_authorised(
        handler=resource_pools_routes.handle_list_resource_pools, query={"project_id": "not-a-uuid"},
    )

    testbase.assert_equal((status, body["invalid_fields"]), (400, ["project_id"]))
    return


def test_create_pool_with_a_malformed_project_id_is_a_422_problem():
    """
    **Feature: resources (RES-38 malformed ids)**
    **Property: POST resource-pools with project_id "not-a-uuid" answers
    422 naming the field.**
    """
    status, body = _call_authorised(
        handler=resource_pools_routes.handle_create_resource_pool,
        body={"project_id": "not-a-uuid", "name": "android-phones"},
    )

    testbase.assert_equal((status, body["type"], body["invalid_fields"]), (422, PROBLEM_TYPE_VALIDATION_FAILED, ["project_id"]))
    return


def test_add_member_with_a_malformed_resource_id_is_a_422_problem():
    """
    **Feature: resources (RES-38 malformed ids)**
    **Property: POST resource-pools/{id}/resources with resource_id
    "bad" answers 422 naming the field.**
    """
    status, body = _call_authorised(
        handler=resource_pools_routes.handle_add_pool_resource,
        path_params={"pool_id": _A_POOL_ID},
        body={"resource_id": "bad"},
    )

    testbase.assert_equal((status, body["invalid_fields"]), (422, ["resource_id"]))
    return


def test_remove_member_with_a_malformed_resource_id_is_a_404_problem():
    """
    **Feature: resources (RES-38 malformed ids)**
    **Property: DELETE resource-pools/{id}/resources/bad answers 404
    instead of a 500.**
    """
    status, body = _call_authorised(
        handler=resource_pools_routes.handle_remove_pool_resource,
        path_params={"pool_id": _A_POOL_ID, "resource_id": "bad"},
    )

    testbase.assert_equal((status, body["type"]), (404, PROBLEM_TYPE_NOT_FOUND))
    return


def test_release_reservation_with_a_malformed_id_is_a_404_problem():
    """
    **Feature: resources (RES-38 malformed ids)**
    **Property: DELETE resource-pools/{id}/reservations/bad answers 404
    instead of a 500.**
    """
    status, body = _call_authorised(
        handler=resource_pools_routes.handle_release_pool_reservation,
        path_params={"pool_id": _A_POOL_ID, "reservation_id": "bad"},
    )

    testbase.assert_equal((status, body["type"]), (404, PROBLEM_TYPE_NOT_FOUND))
    return


def test_reserve_with_a_malformed_preferred_member_is_a_422_problem():
    """
    **Feature: resources (RES-38 malformed ids)**
    **Property: POST resource-pools/{id}/reservations with a
    preferred_member that is not a UUID answers 422 naming the field.**
    """
    status, body = _call_authorised(
        handler=resource_pools_routes.handle_create_pool_reservation,
        path_params={"pool_id": _A_POOL_ID},
        body={"project_id": _A_PROJECT_ID, "preferred_member": "phone-7"},
    )

    testbase.assert_equal((status, body["invalid_fields"]), (422, ["preferred_member"]))
    return
