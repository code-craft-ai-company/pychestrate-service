"""
.. module:: test_p20p_resources_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the per-resource REST endpoints (PR p20p).

.. moduleauthor:: Automation Mojo LLC

Covers the per-resource read operations attached by
``register_resources_routes``:

* GET /api/v1/resources/{resource_id}
* GET /api/v1/resources/{resource_id}/health
* GET /api/v1/resources/{resource_id}/usage-history

Auth (401/403), session boundary (503), not-found (404), bad query
param (400), and happy-path 200 each get explicit coverage.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from automojo import testbase
from automojo.testbase.mocking import create_module_patch

from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
)
from automojo.pychestrate.webservice.resources.health.errors import (
    HealthRecordNotFoundError,
)
from automojo.pychestrate.webservice.resources.health.models import (
    ProbeOutcome,
)
from automojo.pychestrate.webservice.resources.inventory.errors import (
    ResourceNotFoundError,
)
from automojo.pychestrate.webservice.resources.inventory.models import (
    ResourceState,
)
from automojo.pychestrate.webservice.resources.usage_history.models import (
    UsageEventType,
)
from automojo.pychestrate.webservice.resources.restapi.v1 import (
    resources_routes,
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
            db_session: Optional[Any] = None,
            auth_principal: Optional[Any] = None
        ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        return

    def json(self) -> Any:
        rtnval = None
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


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        resources_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _make_resource_view(*, resource_id: str = "res-1") -> Any:
    rtnval = resources_routes.inventory_service.ResourceView(
        resource_id=resource_id,
        project_id="proj-1",
        kind="device",
        display_name="lab-device",
        description="",
        identity_hash="abc123",
        state=ResourceState.AVAILABLE,
        tags=("gpu",),
        attributes={"serial": "x1"},
        created_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
    )
    return rtnval


def _make_health_view(*, resource_id: str = "res-1") -> Any:
    rtnval = resources_routes.health_service.HealthView(
        health_id="health-1",
        resource_id=resource_id,
        project_id="proj-1",
        probe_name="device-ping",
        probe_period_seconds=60,
        last_outcome=ProbeOutcome.PASS,
        last_probe_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
        last_pass_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
        last_fail_at=None,
        next_probe_at=datetime(2026, 5, 20, 12, 1, 0, tzinfo=timezone.utc),
        pass_count=3,
        fail_count=0,
        consecutive_failures=0,
        last_error=None,
        last_payload={},
    )
    return rtnval


def _make_usage_view(*, event_id: str = "evt-1") -> Any:
    rtnval = resources_routes.usage_history_service.TimelineEventView(
        event_id=event_id,
        source_event_id="src-1",
        resource_id="res-1",
        project_id="proj-1",
        event_type=UsageEventType.RESOURCE_REGISTERED,
        actor_id=None,
        pod_event_group_id=None,
        at_ts=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
        payload={},
        annotations={},
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_resources_routes_attaches_three_endpoints():
    """
    **Feature: 4-resources PR p20p**
    **Property: register_resources_routes attaches the three
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    resources_routes.register_resources_routes(
        app=app, version_prefix="/api/v1",
    )
    expected_pairs = (
        ("/api/v1/resources/{resource_id}", ("GET",)),
        ("/api/v1/resources/{resource_id}/health", ("GET",)),
        ("/api/v1/resources/{resource_id}/usage-history", ("GET",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET /resources/{resource_id}
# ---------------------------------------------------------------------------


def test_read_resource_returns_503_when_session_missing():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resources/{id} returns 503 when no db_session is
    bound.**
    """
    request = _FakeRequest(
        path="/api/v1/resources/res-1",
        path_params={"resource_id": "res-1"},
        db_session=None,
    )
    response = resources_routes.handle_read_resource(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_read_resource_returns_401_when_no_principal():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resources/{id} returns 401 when no AuthPrincipal
    is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/resources/res-1",
        path_params={"resource_id": "res-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = resources_routes.handle_read_resource(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_read_resource_returns_403_when_permission_denied():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resources/{id} returns 403 when the principal
    lacks system:resources.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/resources/res-1",
            path_params={"resource_id": "res-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resources_routes.handle_read_resource(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:resources.read",
    )
    return


def test_read_resource_returns_404_when_missing():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resources/{id} returns 404 when the resource is
    not found.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        resources_routes.inventory_service, "get_resource",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs):
        raise ResourceNotFoundError("missing")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/resources/res-x",
            path_params={"resource_id": "res-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resources_routes.handle_read_resource(request)
    finally:
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["resource_id"], "res-x")
    return


def test_read_resource_returns_200_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resources/{id} returns 200 with the Resource
    shape.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        resources_routes.inventory_service, "get_resource",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_resource_view(resource_id="res-7"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resources/res-7",
            path_params={"resource_id": "res-7"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resources_routes.handle_read_resource(request)
    finally:
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["resource_id"], "res-7")
    testbase.assert_equal(body["state"], "available")
    return


# ---------------------------------------------------------------------------
# GET /resources/{resource_id}/health
# ---------------------------------------------------------------------------


def test_read_health_returns_404_when_never_seeded():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resources/{id}/health returns 404 when the
    resource has no health record.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        resources_routes.health_service, "get_health_record",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs):
        raise HealthRecordNotFoundError("missing")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/resources/res-x/health",
            path_params={"resource_id": "res-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resources_routes.handle_read_resource_health(request)
    finally:
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["resource_id"], "res-x")
    return


def test_read_health_returns_200_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resources/{id}/health returns 200 with the
    ResourceHealth shape.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        resources_routes.health_service, "get_health_record",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_health_view(resource_id="res-5"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resources/res-5/health",
            path_params={"resource_id": "res-5"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resources_routes.handle_read_resource_health(request)
    finally:
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["resource_id"], "res-5")
    testbase.assert_equal(body["last_outcome"], "pass")
    testbase.assert_equal(body["pass_count"], 3)
    return


def test_read_health_returns_403_when_permission_denied():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resources/{id}/health returns 403 when the
    principal lacks system:resources.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/resources/res-5/health",
            path_params={"resource_id": "res-5"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resources_routes.handle_read_resource_health(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    return


# ---------------------------------------------------------------------------
# GET /resources/{resource_id}/usage-history
# ---------------------------------------------------------------------------


def test_usage_history_returns_page_on_happy_path():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resources/{id}/usage-history returns a
    {items, meta} page of UsageRecord-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    list_patch = create_module_patch(
        resources_routes.usage_history_service, "list_timeline",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [_make_usage_view(event_id="evt-1")],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/resources/res-1/usage-history",
            path_params={"resource_id": "res-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = resources_routes.handle_list_resource_usage_history(request)
    finally:
        list_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["event_id"], "evt-1")
    testbase.assert_equal(
        body["items"][0]["event_type"], "resource.registered",
    )
    return


def test_usage_history_returns_400_on_bad_limit():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resources/{id}/usage-history returns 400 when the
    limit query param is not an integer.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/resources/res-1/usage-history",
            path_params={"resource_id": "res-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"limit": "not-an-int"},
        )
        response = resources_routes.handle_list_resource_usage_history(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    return


def test_usage_history_returns_401_when_no_principal():
    """
    **Feature: 4-resources PR p20p**
    **Property: GET resources/{id}/usage-history returns 401 when no
    AuthPrincipal is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/resources/res-1/usage-history",
        path_params={"resource_id": "res-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = resources_routes.handle_list_resource_usage_history(request)
    testbase.assert_equal(response.status_code, 401)
    return
