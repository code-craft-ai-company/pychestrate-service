"""
.. module:: test_p20f_dashboards_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the project-dashboard REST endpoints (PR p20f).

.. moduleauthor:: Automation Mojo LLC

Covers the dashboard operations attached by
``register_dashboards_routes``:

* GET  /api/v1/projects/{project_id}/dashboards
* POST /api/v1/projects/{project_id}/dashboards
* GET  /api/v1/projects/{project_id}/dashboards/{dashboard_id}

Auth (401/403), session boundary (503), project not-found (404),
malformed body (422), name conflict (409), and happy-path
200/201 each get explicit coverage.
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
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from automojo.pychestrate.webservice.metrics.dashboards.errors import (
    DashboardConflictError,
    DashboardNotFoundError,
)
from automojo.pychestrate.webservice.metrics.dashboards.service import (
    DashboardView,
)
from automojo.pychestrate.webservice.metrics.restapi.v1 import (
    dashboards_routes,
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


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        dashboards_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(
        dashboards_routes.projects_repo, "get_project_by_id",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _make_dashboard_view(
        *,
        dashboard_id: str = "dash-1",
        project_id: str = "proj-1",
        name: str = "Quality Overview"
    ) -> DashboardView:
    rtnval = DashboardView(
        dashboard_id=dashboard_id,
        project_id=project_id,
        name=name,
        description="",
        owner_principal_id="user-1",
        grid_columns_max=12,
        tiles=(),
        version=1,
        created_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_dashboards_routes_attaches_three_endpoints():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: register_dashboards_routes attaches the three
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    dashboards_routes.register_dashboards_routes(
        app=app, version_prefix="/api/v1",
    )
    expected_pairs = (
        ("/api/v1/projects/{project_id}/dashboards", ("GET",)),
        ("/api/v1/projects/{project_id}/dashboards", ("POST",)),
        (
            "/api/v1/projects/{project_id}/dashboards/{dashboard_id}",
            ("GET",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET /dashboards
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: GET dashboards returns 503 when no db_session is
    bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/dashboards",
        path_params={"project_id": "proj-1"},
        db_session=None,
    )
    response = dashboards_routes.handle_list_dashboards(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: GET dashboards returns 401 when no AuthPrincipal is
    bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/dashboards",
        path_params={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = dashboards_routes.handle_list_dashboards(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: GET dashboards returns 403 when the principal lacks
    system:dashboards.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/dashboards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = dashboards_routes.handle_list_dashboards(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:dashboards.read",
    )
    return


def test_list_returns_404_when_project_missing():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: GET dashboards returns 404 when the project does
    not exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/dashboards",
            path_params={"project_id": "proj-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = dashboards_routes.handle_list_dashboards(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    return


def test_list_returns_page_envelope_on_happy_path():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: GET dashboards returns a {items, meta} page with
    Dashboard-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    list_patch = create_module_patch(
        dashboards_routes.dashboards_service, "list_dashboards_for_project",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [_make_dashboard_view()],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/dashboards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = dashboards_routes.handle_list_dashboards(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["dashboard_id"], "dash-1")
    testbase.assert_equal(body["meta"]["total"], 1)
    return


# ---------------------------------------------------------------------------
# POST /dashboards
# ---------------------------------------------------------------------------


def test_create_returns_422_on_missing_body():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: POST dashboards returns 422 when the body is
    missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/dashboards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = dashboards_routes.handle_create_dashboard(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_create_returns_422_on_missing_name():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: POST dashboards returns 422 when name is absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/dashboards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"description": "no name here"},
        )
        response = dashboards_routes.handle_create_dashboard(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal("name" in body["missing_fields"], True)
    return


def test_create_returns_409_on_name_conflict():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: POST dashboards returns 409 when the name already
    exists in the project.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    create_patch = create_module_patch(
        dashboards_routes.dashboards_service, "create_dashboard",
    )
    create_mock = create_patch.activate()

    def _raise(**kwargs):
        raise DashboardConflictError("duplicate name")

    create_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/dashboards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"name": "Quality Overview"},
        )
        response = dashboards_routes.handle_create_dashboard(request)
    finally:
        create_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["name"], "Quality Overview")
    return


def test_create_returns_201_on_happy_path():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: POST dashboards returns 201 with the Dashboard
    shape on a valid body.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    create_patch = create_module_patch(
        dashboards_routes.dashboards_service, "create_dashboard",
    )
    create_mock = create_patch.activate()
    create_mock.configure(
        side_effect=lambda **kwargs: _make_dashboard_view(
            dashboard_id="dash-new",
        ),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/dashboards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"name": "Quality Overview", "tiles": []},
        )
        response = dashboards_routes.handle_create_dashboard(request)
    finally:
        create_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["dashboard_id"], "dash-new")
    testbase.assert_equal(body["name"], "Quality Overview")
    return


def test_create_returns_403_when_permission_denied():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: POST dashboards returns 403 when the principal
    lacks system:dashboards.write.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/dashboards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"name": "Quality Overview"},
        )
        response = dashboards_routes.handle_create_dashboard(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:dashboards.write",
    )
    return


# ---------------------------------------------------------------------------
# GET /dashboards/{dashboard_id}
# ---------------------------------------------------------------------------


def test_read_returns_404_when_dashboard_missing():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: GET dashboards/{id} returns 404 when the dashboard
    is not found.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        dashboards_routes.dashboards_service, "get_dashboard",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs):
        raise DashboardNotFoundError("missing")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/dashboards/dash-x",
            path_params={"project_id": "proj-1", "dashboard_id": "dash-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = dashboards_routes.handle_read_dashboard(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["dashboard_id"], "dash-x")
    return


def test_read_returns_404_on_project_mismatch():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: GET dashboards/{id} returns 404 when the dashboard
    belongs to a different project.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        dashboards_routes.dashboards_service, "get_dashboard",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_dashboard_view(
            dashboard_id="dash-9", project_id="other-proj",
        ),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/dashboards/dash-9",
            path_params={"project_id": "proj-1", "dashboard_id": "dash-9"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = dashboards_routes.handle_read_dashboard(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_read_returns_200_on_happy_path():
    """
    **Feature: 7-project-dashboards PR p20f**
    **Property: GET dashboards/{id} returns 200 with the Dashboard
    shape.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        dashboards_routes.dashboards_service, "get_dashboard",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_dashboard_view(
            dashboard_id="dash-7",
        ),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/dashboards/dash-7",
            path_params={"project_id": "proj-1", "dashboard_id": "dash-7"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = dashboards_routes.handle_read_dashboard(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["dashboard_id"], "dash-7")
    return
