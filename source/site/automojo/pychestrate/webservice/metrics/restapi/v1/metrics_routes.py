"""
.. module:: metrics.restapi.v1.metrics_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the metrics tag.

.. moduleauthor:: Automation Mojo LLC

Implements the metric-query operations from
``specs/openapi/pychestrate.yaml``:

* ``GET /api/v1/metrics/catalog``
* ``GET /api/v1/metrics/timeseries``
* ``GET /api/v1/projects/{project_id}/test-metrics``

The catalog + timeseries endpoints expose the timeseries store
seeded by the metrics-ingest layer (``metrics.timeseries``). The
per-project test-metrics endpoint computes a read-time roll-up
directly from the result-ingest tables (``ingest.result``) -- the
metrics domain does not yet aggregate test results into the
timeseries store, so the simplest correct surface is a read-time
rollup query over the persisted ``RunResultSummary`` rows.

Each handler follows the shape of
``orchestration.build.restapi.v1.build_runs_routes``: request
session validation, RBAC permission check, then delegation to the
in-tree domain services. Error responses are RFC 7807 problem
documents emitted via :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.ingest.result import (
    repositories as result_repo,
)
from automojo.pychestrate.webservice.metrics.timeseries import (
    service as timeseries_service,
)
from automojo.pychestrate.webservice.projects import repository as projects_repo
from automojo.pychestrate.webservice.security.rbac import rbac_evaluator


METRICS_PATH_PREFIX = "/metrics"
PROJECTS_PATH_PREFIX = "/projects"

METRICS_READ_PERMISSION_KEY = "system:metrics.read"

DEFAULT_SAMPLE_LIMIT = 500
MAX_SAMPLE_LIMIT = 5000

DEFAULT_TEST_METRICS_RUN_LIMIT = 500
MAX_TEST_METRICS_RUN_LIMIT = 2000

_LOGGER = logging.getLogger("pychestrate.metrics.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a webworks
        problem response so nested helpers can signal an error
        once and the top-level handler converts it at the
        boundary.
    """

    def __init__(self, response: Response) -> None:
        super().__init__("problem abort")
        self.response: Response = response
        return


def _abort_problem(
        *,
        request: Request,
        status: int,
        detail: str,
        extensions: Optional[Dict[str, Any]] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional namespaced extension members.

        :returns: Never returns.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session or ``None``.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session.
    """
    db_session = _resolve_db_session(request=request)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
    return rtnval


def _resolve_auth_principal(request: Request) -> Optional[Any]:
    """
        Return the ``AuthPrincipal`` attached by the session
        middleware, or ``None`` when the request is anonymous.

        :param request: Incoming webworks request.

        :returns: AuthPrincipal or None.
    """
    rtnval = getattr(request, "auth_principal", None)
    return rtnval


def _require_permission(
        *,
        request: Request,
        db_session: Any,
        permission_key: str
    ) -> Any:
    """
        Require the calling principal to hold ``permission_key``.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param permission_key: Required ``system:*`` permission key.

        :returns: The :class:`AuthPrincipal`.
    """
    principal = _resolve_auth_principal(request=request)
    if principal is None:
        _abort_problem(
            request=request,
            status=401,
            detail="Authentication required.",
        )

    now = datetime.now(timezone.utc)
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=permission_key,
        now=now,
    )
    if decision.allowed is False:
        _abort_problem(
            request=request,
            status=403,
            detail="Permission denied: {}".format(permission_key),
            extensions={"required_permission": permission_key},
        )
    rtnval = principal
    return rtnval


def _require_project_exists(
        *,
        request: Request,
        db_session: Any,
        project_id: str
    ) -> Any:
    """
        Look up the project row, aborting 404 when not found.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param project_id: Project UUID from the path.

        :returns: Project ORM row.
    """
    row = projects_repo.get_project_by_id(
        db_session=db_session,
        project_id=project_id,
    )
    if row is None:
        _abort_problem(
            request=request,
            status=404,
            detail="Project not found.",
            extensions={"project_id": project_id},
        )
    rtnval = row
    return rtnval


def _parse_positive_int(
        *,
        request: Request,
        name: str,
        raw: Optional[str],
        default: int,
        minimum: int,
        maximum: Optional[int] = None
    ) -> int:
    """
        Coerce a positive-integer query param with bounds checking.

        :param request: Incoming webworks request.
        :param name: Query-param name (for error context).
        :param raw: Raw query value or None.
        :param default: Fallback when the param is absent.
        :param minimum: Lower bound (inclusive).
        :param maximum: Optional upper bound (inclusive).

        :returns: Coerced integer.
    """
    if raw is None or len(raw) == 0:
        rtnval = default
        return rtnval

    try:
        candidate = int(raw)
    except ValueError:
        _abort_problem(
            request=request,
            status=422,
            detail="Query param '{}' must be an integer.".format(name),
            extensions={"query_param": name, "raw_value": raw},
        )
        candidate = default  # unreachable

    if candidate < minimum:
        _abort_problem(
            request=request,
            status=422,
            detail="Query param '{}' must be >= {}.".format(name, minimum),
            extensions={"query_param": name, "raw_value": raw},
        )
    if maximum is not None and candidate > maximum:
        _abort_problem(
            request=request,
            status=422,
            detail="Query param '{}' must be <= {}.".format(name, maximum),
            extensions={"query_param": name, "raw_value": raw},
        )

    rtnval = candidate
    return rtnval


def _parse_iso_datetime(
        *,
        request: Request,
        name: str,
        raw: Optional[str]
    ) -> Optional[datetime]:
    """
        Parse an optional ISO-8601 datetime query param.

        :param request: Incoming webworks request.
        :param name: Query-param name (for error context).
        :param raw: Raw query value or None.

        :returns: Parsed datetime or None when absent.
    """
    if raw is None or len(raw) == 0:
        rtnval = None
        return rtnval

    candidate_text = raw
    if candidate_text.endswith("Z"):
        candidate_text = candidate_text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate_text)
    except ValueError:
        _abort_problem(
            request=request,
            status=422,
            detail="Query param '{}' must be an ISO-8601 datetime.".format(
                name,
            ),
            extensions={"query_param": name, "raw_value": raw},
        )
        parsed = None  # unreachable

    rtnval = parsed
    return rtnval


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _iso_or_none(value: Any) -> Optional[str]:
    """
        ISO-8601 serialize a datetime or return ``None``.

        :param value: Datetime or None.

        :returns: ISO-formatted string or None.
    """
    if value is None:
        rtnval = None
        return rtnval
    if isinstance(value, datetime):
        rtnval = value.isoformat()
        return rtnval
    rtnval = str(value)
    return rtnval


def _definition_to_catalog_entry(definition: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`MetricDefinition` to the OpenAPI
        ``MetricCatalogEntry`` schema.

        :param definition: Registered metric definition.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "name": definition.name,
        "kind": definition.kind.value,
        "label_names": list(definition.label_names),
        "help_text": definition.help_text,
        "cardinality_max": int(definition.cardinality_max),
    }
    return rtnval


def _sample_view_to_point(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`SampleView` to the OpenAPI
        ``TimeseriesPoint`` schema.

        :param view: Persisted sample read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "observed_at": _iso_or_none(view.observed_at),
        "value": float(view.value),
        "labels": dict(view.labels or {}),
        "label_signature": view.label_signature,
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/metrics/catalog
# ---------------------------------------------------------------------------


def handle_list_metric_catalog(request: Request) -> Response:
    """
        ``GET /api/v1/metrics/catalog``

        Returns the registered metric definitions -- name, kind,
        and declared label dimensions -- so a UI knows what is
        queryable through the timeseries endpoint.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items, meta}``
                  page, or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=METRICS_READ_PERMISSION_KEY,
        )

        definitions = timeseries_service.list_definitions()
        items: List[Dict[str, Any]] = []
        for definition in definitions:
            items.append(_definition_to_catalog_entry(definition=definition))

        body = {
            "items": items,
            "meta": {
                "page": 1,
                "per_page": len(items),
                "total": len(items),
                "next_cursor": None,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/metrics/timeseries
# ---------------------------------------------------------------------------


def handle_query_timeseries(request: Request) -> Response:
    """
        ``GET /api/v1/metrics/timeseries``

        Query params: ``metric`` (required), ``from``, ``to``,
        ``limit``. Returns timestamped data points for the named
        metric, newest-first, optionally bounded by the ``from`` /
        ``to`` observation window.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a ``TimeseriesQuery``
                  result, or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=METRICS_READ_PERMISSION_KEY,
        )

        metric_name = request.query_params.get("metric", None)
        if metric_name is None or len(metric_name) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Query param 'metric' is required.",
                extensions={"query_param": "metric"},
            )

        from_dt = _parse_iso_datetime(
            request=request,
            name="from",
            raw=request.query_params.get("from", None),
        )
        to_dt = _parse_iso_datetime(
            request=request,
            name="to",
            raw=request.query_params.get("to", None),
        )
        limit = _parse_positive_int(
            request=request,
            name="limit",
            raw=request.query_params.get("limit", None),
            default=DEFAULT_SAMPLE_LIMIT,
            minimum=1,
            maximum=MAX_SAMPLE_LIMIT,
        )

        definition = timeseries_service.get_metric_registry().find(
            name=metric_name,
        )
        if definition is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Metric is not registered.",
                extensions={"metric": metric_name},
            )

        sample_views = timeseries_service.list_samples_for_metric(
            db_session=db_session,
            metric_name=metric_name,
            limit=limit,
        )

        points: List[Dict[str, Any]] = []
        for view in sample_views:
            observed_at = view.observed_at
            if from_dt is not None and observed_at is not None:
                if observed_at < from_dt:
                    continue
            if to_dt is not None and observed_at is not None:
                if observed_at > to_dt:
                    continue
            points.append(_sample_view_to_point(view=view))

        body = {
            "metric": metric_name,
            "kind": definition.kind.value,
            "from": _iso_or_none(from_dt),
            "to": _iso_or_none(to_dt),
            "points": points,
            "meta": {
                "point_count": len(points),
                "limit": limit,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/test-metrics
# ---------------------------------------------------------------------------


def _compute_test_metrics_rollup(
        *,
        summaries: List[Any]
    ) -> Dict[str, Any]:
    """
        Compute a read-time roll-up over the supplied
        result-ingest summary rows.

        :param summaries: List of :class:`RunResultSummary` rows.

        :returns: ``TestMetricsSummary``-shaped dict.
    """
    run_count = len(summaries)
    tests_total = 0
    tests_passed = 0
    tests_failed = 0
    tests_skipped = 0
    tests_errored = 0
    runs_with_failures = 0
    duration_total_seconds = 0.0
    duration_sample_count = 0

    for summary in summaries:
        tests_total = tests_total + int(summary.tests_total or 0)
        tests_passed = tests_passed + int(summary.tests_passed or 0)
        tests_failed = tests_failed + int(summary.tests_failed or 0)
        tests_skipped = tests_skipped + int(summary.tests_skipped or 0)
        tests_errored = tests_errored + int(summary.tests_errored or 0)

        failed_in_run = int(summary.tests_failed or 0)
        errored_in_run = int(summary.tests_errored or 0)
        if failed_in_run > 0 or errored_in_run > 0:
            runs_with_failures = runs_with_failures + 1

        started_at = summary.started_at
        finished_at = summary.finished_at
        if started_at is not None and finished_at is not None:
            delta_seconds = (finished_at - started_at).total_seconds()
            if delta_seconds >= 0.0:
                duration_total_seconds = (
                    duration_total_seconds + delta_seconds
                )
                duration_sample_count = duration_sample_count + 1

    pass_rate = 0.0
    fail_rate = 0.0
    if tests_total > 0:
        pass_rate = float(tests_passed) / float(tests_total)
        fail_rate = (
            float(tests_failed + tests_errored) / float(tests_total)
        )

    flake_run_rate = 0.0
    if run_count > 0:
        flake_run_rate = float(runs_with_failures) / float(run_count)

    average_duration_seconds = 0.0
    if duration_sample_count > 0:
        average_duration_seconds = (
            duration_total_seconds / float(duration_sample_count)
        )

    rtnval: Dict[str, Any] = {
        "run_count": run_count,
        "tests_total": tests_total,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "tests_skipped": tests_skipped,
        "tests_errored": tests_errored,
        "pass_rate": round(pass_rate, 6),
        "fail_rate": round(fail_rate, 6),
        "runs_with_failures": runs_with_failures,
        "flake_run_rate": round(flake_run_rate, 6),
        "average_run_duration_seconds": round(average_duration_seconds, 3),
    }
    return rtnval


def _summary_to_run_entry(summary: Any) -> Dict[str, Any]:
    """
        Serialize one result-ingest summary row to a per-run
        rollup entry.

        :param summary: :class:`RunResultSummary` row.

        :returns: JSON-friendly dict.
    """
    duration_seconds: Optional[float] = None
    started_at = summary.started_at
    finished_at = summary.finished_at
    if started_at is not None and finished_at is not None:
        delta_seconds = (finished_at - started_at).total_seconds()
        if delta_seconds >= 0.0:
            duration_seconds = round(delta_seconds, 3)

    rtnval: Dict[str, Any] = {
        "run_id": str(summary.run_id),
        "parser_tag": summary.parser_tag,
        "tests_total": int(summary.tests_total or 0),
        "tests_passed": int(summary.tests_passed or 0),
        "tests_failed": int(summary.tests_failed or 0),
        "tests_skipped": int(summary.tests_skipped or 0),
        "tests_errored": int(summary.tests_errored or 0),
        "started_at": _iso_or_none(summary.started_at),
        "finished_at": _iso_or_none(summary.finished_at),
        "ingested_at": _iso_or_none(summary.ingested_at),
        "duration_seconds": duration_seconds,
    }
    return rtnval


def handle_read_test_metrics(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/test-metrics``

        Returns a read-time roll-up of testbase / testplus test
        results for the project: aggregate pass / fail / flake
        rates, run counts, and duration trends, plus a recent
        per-run breakdown.

        The metrics domain does not pre-aggregate test results
        into the timeseries store; this endpoint computes the
        roll-up directly from the persisted result-ingest summary
        rows (``ingest.result.RunResultSummary``). Query param
        ``limit`` caps the number of recent runs considered.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a ``TestMetricsSummary``
                  body, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=METRICS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        limit = _parse_positive_int(
            request=request,
            name="limit",
            raw=request.query_params.get("limit", None),
            default=DEFAULT_TEST_METRICS_RUN_LIMIT,
            minimum=1,
            maximum=MAX_TEST_METRICS_RUN_LIMIT,
        )

        summaries = result_repo.list_summaries_for_project(
            db_session=db_session,
            project_id=project_id,
            limit=limit,
        )

        rollup = _compute_test_metrics_rollup(summaries=summaries)
        recent_runs: List[Dict[str, Any]] = []
        for summary in summaries:
            recent_runs.append(_summary_to_run_entry(summary=summary))

        body = {
            "project_id": str(project_id),
            "summary": rollup,
            "recent_runs": recent_runs,
            "meta": {
                "run_limit": limit,
                "run_count": len(summaries),
                "source": "ingest.result.run_result_summary",
                "aggregation": "read_time_rollup",
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_metrics_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the metric-query REST routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    app.attach_route(
        version_prefix + METRICS_PATH_PREFIX + "/catalog",
        methods=["GET"],
    )(handle_list_metric_catalog)
    app.attach_route(
        version_prefix + METRICS_PATH_PREFIX + "/timeseries",
        methods=["GET"],
    )(handle_query_timeseries)
    app.attach_route(
        version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}/test-metrics",
        methods=["GET"],
    )(handle_read_test_metrics)
    return


__all__ = [
    "METRICS_READ_PERMISSION_KEY",
    "DEFAULT_SAMPLE_LIMIT",
    "MAX_SAMPLE_LIMIT",
    "register_metrics_routes",
    "handle_list_metric_catalog",
    "handle_query_timeseries",
    "handle_read_test_metrics",
]
