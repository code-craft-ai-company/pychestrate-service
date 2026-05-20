"""
.. module:: test_p21c_slos_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the SLO-view REST endpoints (PR p21c).

.. moduleauthor:: Automation Mojo LLC

Covers the SLO operations attached by ``register_slos_routes``:

* GET    /api/v1/projects/{project_id}/slos
* POST   /api/v1/projects/{project_id}/slos
* GET    /api/v1/projects/{project_id}/slos/{slo_id}
* DELETE /api/v1/projects/{project_id}/slos/{slo_id}

Auth (401/403), session boundary (503), project not-found (404),
malformed body (422), conflict (409), pagination, status embed,
and happy-path 2xx each get explicit coverage.
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
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from automojo.pychestrate.webservice.metrics.slos.errors import (
    SLOConflictError,
    SLONotFoundError,
)
from automojo.pychestrate.webservice.metrics.slos.service import (
    SLOStatus,
    SLOView,
)
from automojo.pychestrate.webservice.metrics.restapi.v1 import (
    slos_routes,
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


class _FakeProject:
    def __init__(self, *, project_id: str) -> None:
        self.project_id: str = project_id
        return


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        slos_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(
        slos_routes.projects_repo, "get_project_by_id",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _make_slo_view(
        *,
        slo_id: str = "slo-1",
        project_id: str = "proj-1",
        name: str = "api-availability",
        kind: str = "ratio"
    ) -> Any:
    now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
    rtnval = SLOView(
        slo_id=slo_id,
        project_id=project_id,
        name=name,
        description="",
        kind=kind,
        target=0.99,
        window_seconds=2592000,
        definition_config={},
        default_notification_route_key=None,
        auto_attach_burn_rate_alerts=False,
        version=1,
        created_at=now,
        updated_at=now,
    )
    return rtnval


def _make_slo_status(*, slo_id: str = "slo-1") -> Any:
    now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
    rtnval = SLOStatus(
        slo_id=slo_id,
        achieved_ratio=0.995,
        error_budget_remaining_ratio=0.5,
        target=0.99,
        window_start=now,
        window_end=now,
        good_count=995,
        total_count=1000,
        breaching=False,
        reason="within budget",
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_slos_routes_attaches_four_endpoints():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: register_slos_routes attaches the four method+path
    pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    slos_routes.register_slos_routes(app=app, version_prefix="/api/v1")
    expected_pairs = (
        ("/api/v1/projects/{project_id}/slos", ("GET",)),
        ("/api/v1/projects/{project_id}/slos", ("POST",)),
        ("/api/v1/projects/{project_id}/slos/{slo_id}", ("GET",)),
        ("/api/v1/projects/{project_id}/slos/{slo_id}", ("DELETE",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET list -- auth + session sweep
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: GET slos returns 503 when no db_session is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/slos",
        path_params={"project_id": "proj-1"},
        db_session=None,
    )
    response = slos_routes.handle_list_slos(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: GET slos returns 401 when no AuthPrincipal bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/slos",
        path_params={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = slos_routes.handle_list_slos(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: GET slos returns 403 when the principal lacks
    system:slos.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/slos",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = slos_routes.handle_list_slos(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:slos.read")
    return


def test_list_returns_404_when_project_missing():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: GET slos returns 404 when the project does not
    exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/slos",
            path_params={"project_id": "proj-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = slos_routes.handle_list_slos(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    return


def test_list_returns_page_envelope_on_happy_path():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: GET slos returns an {items, meta} page with
    Slo-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    list_patch = create_module_patch(
        slos_routes.slos_service, "list_slos_for_project",
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: [_make_slo_view()])
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/slos",
            path_params={"project_id": "proj-1"},
            query={"page": "1", "per_page": "10"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = slos_routes.handle_list_slos(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["slo_id"], "slo-1")
    testbase.assert_equal(body["meta"]["total"], 1)
    return


# ---------------------------------------------------------------------------
# POST create
# ---------------------------------------------------------------------------


def test_create_returns_422_on_missing_body():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: POST slos returns 422 when the body is missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/slos",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = slos_routes.handle_create_slo(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_create_returns_422_on_missing_target():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: POST slos returns 422 when the target field is
    absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/slos",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"name": "api-availability", "kind": "ratio"},
        )
        response = slos_routes.handle_create_slo(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    return


def test_create_returns_409_on_name_conflict():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: POST slos returns 409 when the SLO facade raises
    SLOConflictError.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    create_patch = create_module_patch(
        slos_routes.slos_service, "create_slo",
    )
    create_mock = create_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise SLOConflictError("name exists")

    create_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/slos",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "name": "api-availability",
                "kind": "ratio",
                "target": 0.99,
            },
        )
        response = slos_routes.handle_create_slo(request)
    finally:
        create_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    return


def test_create_returns_201_on_happy_path():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: POST slos returns 201 with the created SLO.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    create_patch = create_module_patch(
        slos_routes.slos_service, "create_slo",
    )
    create_mock = create_patch.activate()
    create_mock.configure(side_effect=lambda **kwargs: _make_slo_view())
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/slos",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "name": "api-availability",
                "kind": "ratio",
                "target": 0.99,
            },
        )
        response = slos_routes.handle_create_slo(request)
    finally:
        create_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["name"], "api-availability")
    return


# ---------------------------------------------------------------------------
# GET read
# ---------------------------------------------------------------------------


def test_read_returns_404_when_slo_missing():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: GET slo returns 404 when the SLO facade raises
    SLONotFoundError.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    get_patch = create_module_patch(slos_routes.slos_service, "get_slo")
    get_mock = get_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise SLONotFoundError("no slo")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/slos/slo-x",
            path_params={"project_id": "proj-1", "slo_id": "slo-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = slos_routes.handle_read_slo(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_read_returns_200_with_embedded_status():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: GET slo returns 200 with an embedded status block
    carrying the current burn-rate / achieved ratio.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    get_patch = create_module_patch(slos_routes.slos_service, "get_slo")
    get_mock = get_patch.activate()
    get_mock.configure(side_effect=lambda **kwargs: _make_slo_view())
    status_patch = create_module_patch(
        slos_routes.slos_service, "compute_status",
    )
    status_mock = status_patch.activate()
    status_mock.configure(side_effect=lambda **kwargs: _make_slo_status())
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/slos/slo-1",
            path_params={"project_id": "proj-1", "slo_id": "slo-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = slos_routes.handle_read_slo(request)
    finally:
        status_patch.deactivate()
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["slo_id"], "slo-1")
    testbase.assert_equal(body["status"]["achieved_ratio"], 0.995)
    testbase.assert_equal(body["status"]["breaching"], False)
    return


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def test_delete_returns_204_on_happy_path():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: DELETE slo returns 204 on a successful delete.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    get_patch = create_module_patch(slos_routes.slos_service, "get_slo")
    get_mock = get_patch.activate()
    get_mock.configure(side_effect=lambda **kwargs: _make_slo_view())
    delete_patch = create_module_patch(
        slos_routes.slos_service, "delete_slo",
    )
    delete_mock = delete_patch.activate()
    delete_mock.configure(side_effect=lambda **kwargs: True)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/slos/slo-1",
            path_params={"project_id": "proj-1", "slo_id": "slo-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = slos_routes.handle_delete_slo(request)
    finally:
        delete_patch.deactivate()
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 204)
    return


def test_delete_returns_404_when_slo_in_other_project():
    """
    **Feature: 7-slo-views PR p21c**
    **Property: DELETE slo returns 404 when the SLO belongs to a
    different project.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    get_patch = create_module_patch(slos_routes.slos_service, "get_slo")
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_slo_view(project_id="proj-2"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/slos/slo-1",
            path_params={"project_id": "proj-1", "slo_id": "slo-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = slos_routes.handle_delete_slo(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return
