"""
.. module:: test_p20f_metrics_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the metric-query REST endpoints (PR p20f).

.. moduleauthor:: Automation Mojo LLC

Covers the metric-query operations attached by
``register_metrics_routes``:

* GET /api/v1/metrics/catalog
* GET /api/v1/metrics/timeseries
* GET /api/v1/projects/{project_id}/test-metrics

Auth (401/403), session boundary (503), project not-found (404),
missing/invalid query params (422/404), and happy-path 200 each
get explicit coverage.
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
from automojo.pychestrate.webservice.metrics.restapi.v1 import metrics_routes
from automojo.pychestrate.webservice.metrics.timeseries.facade import (
    MetricDefinition,
    MetricKind,
)
from automojo.pychestrate.webservice.metrics.timeseries.service import (
    SampleView,
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


class _FakeSummary:
    def __init__(
            self,
            *,
            run_id: str,
            tests_total: int,
            tests_passed: int,
            tests_failed: int,
            tests_skipped: int = 0,
            tests_errored: int = 0,
            started_at: Optional[datetime] = None,
            finished_at: Optional[datetime] = None
        ) -> None:
        self.run_id: str = run_id
        self.project_id: str = "proj-1"
        self.parser_tag: str = "testbase_v1"
        self.tests_total: int = tests_total
        self.tests_passed: int = tests_passed
        self.tests_failed: int = tests_failed
        self.tests_skipped: int = tests_skipped
        self.tests_errored: int = tests_errored
        self.started_at: Optional[datetime] = started_at
        self.finished_at: Optional[datetime] = finished_at
        self.ingested_at: datetime = datetime(
            2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc,
        )
        return


class _FakeRegistry:
    def __init__(self, *, definition: Optional[Any]) -> None:
        self._definition: Optional[Any] = definition
        return

    def find(self, *, name: str) -> Optional[Any]:
        rtnval = self._definition
        return rtnval


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        metrics_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(
        metrics_routes.projects_repo, "get_project_by_id",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _make_definition() -> MetricDefinition:
    rtnval = MetricDefinition(
        name="pychestrate_test_runs_total",
        kind=MetricKind.COUNTER,
        label_names=("project", "result"),
        help_text="Total test runs.",
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_metrics_routes_attaches_three_endpoints():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: register_metrics_routes attaches the three
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    metrics_routes.register_metrics_routes(app=app, version_prefix="/api/v1")
    expected_pairs = (
        ("/api/v1/metrics/catalog", ("GET",)),
        ("/api/v1/metrics/timeseries", ("GET",)),
        ("/api/v1/projects/{project_id}/test-metrics", ("GET",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET /metrics/catalog
# ---------------------------------------------------------------------------


def test_catalog_returns_503_when_session_missing():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: GET catalog returns 503 when no db_session is
    bound.**
    """
    request = _FakeRequest(
        path="/api/v1/metrics/catalog",
        db_session=None,
    )
    response = metrics_routes.handle_list_metric_catalog(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_catalog_returns_401_when_no_principal():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: GET catalog returns 401 when no AuthPrincipal is
    bound.**
    """
    request = _FakeRequest(
        path="/api/v1/metrics/catalog",
        db_session=object(),
        auth_principal=None,
    )
    response = metrics_routes.handle_list_metric_catalog(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_catalog_returns_403_when_permission_denied():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: GET catalog returns 403 when the principal lacks
    system:metrics.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/metrics/catalog",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = metrics_routes.handle_list_metric_catalog(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:metrics.read")
    return


def test_catalog_returns_entries_on_happy_path():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: GET catalog returns a {items, meta} page of
    MetricCatalogEntry items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    list_patch = create_module_patch(
        metrics_routes.timeseries_service, "list_definitions",
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda: (_make_definition(),))
    try:
        request = _FakeRequest(
            path="/api/v1/metrics/catalog",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = metrics_routes.handle_list_metric_catalog(request)
    finally:
        list_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(
        body["items"][0]["name"], "pychestrate_test_runs_total",
    )
    testbase.assert_equal(body["items"][0]["kind"], "counter")
    testbase.assert_equal(body["items"][0]["label_names"], ["project", "result"])
    testbase.assert_equal(body["meta"]["total"], 1)
    return


# ---------------------------------------------------------------------------
# GET /metrics/timeseries
# ---------------------------------------------------------------------------


def test_timeseries_returns_422_when_metric_param_missing():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: GET timeseries returns 422 when the required
    metric query param is absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/metrics/timeseries",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = metrics_routes.handle_query_timeseries(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_timeseries_returns_404_when_metric_unknown():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: GET timeseries returns 404 when the metric is not
    registered.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    registry_patch = create_module_patch(
        metrics_routes.timeseries_service, "get_metric_registry",
    )
    registry_mock = registry_patch.activate()
    registry_mock.configure(
        side_effect=lambda: _FakeRegistry(definition=None),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/metrics/timeseries",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"metric": "bogus_metric"},
        )
        response = metrics_routes.handle_query_timeseries(request)
    finally:
        registry_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["metric"], "bogus_metric")
    return


def test_timeseries_returns_points_on_happy_path():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: GET timeseries returns a TimeseriesQuery with
    TimeseriesPoint items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    registry_patch = create_module_patch(
        metrics_routes.timeseries_service, "get_metric_registry",
    )
    registry_mock = registry_patch.activate()
    registry_mock.configure(
        side_effect=lambda: _FakeRegistry(definition=_make_definition()),
    )
    samples_patch = create_module_patch(
        metrics_routes.timeseries_service, "list_samples_for_metric",
    )
    samples_mock = samples_patch.activate()
    sample = SampleView(
        sample_id="s-1",
        metric_name="pychestrate_test_runs_total",
        label_signature="sig-1",
        labels={"project": "proj-1", "result": "pass"},
        value=3.0,
        observed_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
    )
    samples_mock.configure(side_effect=lambda **kwargs: [sample])
    try:
        request = _FakeRequest(
            path="/api/v1/metrics/timeseries",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"metric": "pychestrate_test_runs_total"},
        )
        response = metrics_routes.handle_query_timeseries(request)
    finally:
        samples_patch.deactivate()
        registry_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["metric"], "pychestrate_test_runs_total")
    testbase.assert_equal(len(body["points"]), 1)
    testbase.assert_equal(body["points"][0]["value"], 3.0)
    testbase.assert_equal(body["meta"]["point_count"], 1)
    return


def test_timeseries_returns_422_on_bad_limit():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: GET timeseries returns 422 when limit is not an
    integer.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/metrics/timeseries",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"metric": "m", "limit": "not-a-number"},
        )
        response = metrics_routes.handle_query_timeseries(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    return


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/test-metrics
# ---------------------------------------------------------------------------


def test_test_metrics_returns_404_when_project_missing():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: GET test-metrics returns 404 when the project does
    not exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/test-metrics",
            path_params={"project_id": "proj-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = metrics_routes.handle_read_test_metrics(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["project_id"], "proj-x")
    return


def test_test_metrics_returns_403_when_permission_denied():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: GET test-metrics returns 403 when the principal
    lacks system:metrics.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-metrics",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = metrics_routes.handle_read_test_metrics(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:metrics.read")
    return


def test_test_metrics_returns_rollup_on_happy_path():
    """
    **Feature: 7-test-metrics PR p20f**
    **Property: GET test-metrics returns a TestMetricsSummary with
    a computed rollup over the result-ingest summary rows.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    summaries_patch = create_module_patch(
        metrics_routes.result_repo, "list_summaries_for_project",
    )
    summaries_mock = summaries_patch.activate()
    started = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 5, 20, 12, 10, 0, tzinfo=timezone.utc)
    summaries = [
        _FakeSummary(
            run_id="run-1",
            tests_total=10,
            tests_passed=8,
            tests_failed=2,
            started_at=started,
            finished_at=finished,
        ),
        _FakeSummary(
            run_id="run-2",
            tests_total=10,
            tests_passed=10,
            tests_failed=0,
        ),
    ]
    summaries_mock.configure(side_effect=lambda **kwargs: summaries)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-metrics",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = metrics_routes.handle_read_test_metrics(request)
    finally:
        summaries_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["project_id"], "proj-1")
    testbase.assert_equal(body["summary"]["run_count"], 2)
    testbase.assert_equal(body["summary"]["tests_total"], 20)
    testbase.assert_equal(body["summary"]["tests_passed"], 18)
    testbase.assert_equal(body["summary"]["pass_rate"], 0.9)
    testbase.assert_equal(body["summary"]["runs_with_failures"], 1)
    testbase.assert_equal(body["summary"]["flake_run_rate"], 0.5)
    testbase.assert_equal(body["summary"]["average_run_duration_seconds"], 600.0)
    testbase.assert_equal(len(body["recent_runs"]), 2)
    testbase.assert_equal(body["meta"]["aggregation"], "read_time_rollup")
    return
