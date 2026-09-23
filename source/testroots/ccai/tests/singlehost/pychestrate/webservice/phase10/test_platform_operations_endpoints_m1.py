"""
.. module:: test_platform_operations_endpoints_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression locks for the liveness / readiness probes,
               Prometheus /metrics and the monitoring-friendly health
               summary (audit ORG-F17).

.. moduleauthor:: Code Craft AI LLC

Operators could not monitor the service: /api/v1/system/health needed
an admin session and /livez, /readyz, /healthz and /metrics were 404.
These tests pin:

* /livez answers without consulting dependencies; /readyz reflects the
  database (ok, failing, hung past the budget, not configured);
* /metrics is Prometheus text, closed (403) until the operator opts in,
  bearer-token gated when a token is configured, open when made public;
* the exposition carries readiness, request metrics fed by the WSGI
  layer, backups (incl. the last-success timestamp) and runs;
* the system-health route gives callers without the admin permission
  the overall status only;
* the endpoints are registered, listed with reasons in the anonymous
  access inventory, and pass the first-run setup gate;
* log rotation is installed for the unit's log files.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import re
import tempfile
import time

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid
from ccai.pychestrate.webservice.backup.models import BackupRecord, BackupStatus
from ccai.pychestrate.webservice.hardening.platform_wsgi import (
    wrap_wsgi_application_with_request_metrics,
)
from ccai.pychestrate.webservice.jobs.run.state.enums import RunState
from ccai.pychestrate.webservice.jobs.run.state.models import Run
from ccai.pychestrate.webservice.middleware_setup_gate import (
    PychestrateSetupGateMiddleware,
)
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
from ccai.pychestrate.webservice.security.auth.anonymous_access import (
    ANONYMOUS_OPERATIONS_ENDPOINTS,
    is_anonymous_request_permitted,
)
from ccai.pychestrate.webservice.system import operations
from ccai.pychestrate.webservice.system import prometheus
from ccai.pychestrate.webservice.system.restapi.v1 import (
    operations_routes,
    system_health_routes,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Headers:
    def __init__(self, values: Optional[Dict[str, str]] = None) -> None:
        self._values = {key.lower(): value for key, value in (values or {}).items()}
        return

    def get(self, name: str, default: Any = None) -> Any:
        rtnval = self._values.get(name.lower(), default)
        return rtnval


class _FakeRequest:
    def __init__(self, *, path: str, headers: Optional[Dict[str, str]] = None) -> None:
        self.path = path
        self.method = "GET"
        self.headers = _Headers(headers)
        return


class _FakeApp:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[str, ...], Callable]] = []
        return

    def attach_route(self, path: str, methods: Optional[List[str]] = None) -> Callable:
        def decorator(func: Callable) -> Callable:
            self.calls.append((path, tuple(methods or ["GET"]), func))
            return func
        return decorator


def _sqlite_factory(*, tables: List[Any]) -> Tuple[Any, Callable[[], Any]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    PychestratePhase1Base.metadata.create_all(engine, tables=[table.__table__ for table in tables])
    rtnval = (engine, sessionmaker(bind=engine))
    return rtnval


def _body(response: Any) -> Any:
    rtnval = json.loads(response.body.decode("utf-8"))
    return rtnval


class _EnvPatch:
    """Set / clear environment variables for the duration of a block."""

    def __init__(self, **values: Optional[str]) -> None:
        self._values = values
        self._previous: Dict[str, Optional[str]] = {}
        return

    def __enter__(self) -> "_EnvPatch":
        for name, value in self._values.items():
            self._previous[name] = os.environ.get(name, None)
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        return self

    def __exit__(self, *exc_info: Any) -> None:
        for name, value in self._previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        return


def _no_metrics_config() -> _EnvPatch:
    rtnval = _EnvPatch(**{
        operations.ENV_METRICS_TOKEN: None,
        operations.ENV_METRICS_TOKEN_FILE: None,
        operations.ENV_METRICS_PUBLIC: None,
    })
    return rtnval


# ---------------------------------------------------------------------------
# Liveness / readiness
# ---------------------------------------------------------------------------


def test_liveness_answers_live():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: /livez answers 200 {"status": "live"}.**
    """
    response = operations_routes.handle_liveness(_FakeRequest(path="/livez"))
    testbase.assert_equal((response.status_code, _body(response)), (200, {"status": "live"}))
    return


def test_readiness_passes_when_the_database_answers():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: readiness is true when SELECT 1 succeeds.**
    """
    _, factory = _sqlite_factory(tables=[])
    result = operations.evaluate_readiness(session_factory=factory)
    testbase.assert_equal((result.ready, result.checks), (True, {"database": True}))
    return


def test_readiness_fails_when_the_database_errors():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: a database error makes readiness fail with "database"
    listed as failing.**
    """
    def broken_factory() -> Any:
        raise RuntimeError("connection refused")

    result = operations.evaluate_readiness(session_factory=broken_factory)
    testbase.assert_equal((result.ready, result.failing()), (False, ["database"]))
    return


def test_readiness_fails_when_the_database_hangs():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: a database that does not answer within the budget
    counts as failing, and the probe returns promptly.**
    """
    def hanging_factory() -> Any:
        time.sleep(1.0)
        raise RuntimeError("too late")

    started = time.monotonic()
    result = operations.evaluate_readiness(session_factory=hanging_factory, timeout_seconds=0.1)
    elapsed = time.monotonic() - started
    testbase.assert_equal((result.ready, elapsed < 0.9), (False, True))
    return


def test_readiness_route_answers_503_with_the_failing_checks():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: /readyz answers 503 {"status": "not_ready", "failing":
    ["database"]} when the database check fails.**
    """
    from ccai.testbase.mocking import create_module_patch

    patch = create_module_patch(operations, "_default_session_factory")
    patch.activate().configure(return_value=None)
    try:
        response = operations_routes.handle_readiness(_FakeRequest(path="/readyz"))
    finally:
        patch.deactivate()
    body = _body(response)
    testbase.assert_equal(
        (response.status_code, body["status"], body["failing"]),
        (503, "not_ready", ["database"]),
    )
    return


# ---------------------------------------------------------------------------
# /metrics access
# ---------------------------------------------------------------------------


def test_metrics_are_closed_until_the_operator_opts_in():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: with neither a scrape token nor the public opt-in,
    /metrics answers 403.**
    """
    with _no_metrics_config():
        response = operations_routes.handle_metrics(_FakeRequest(path="/metrics"))
    testbase.assert_equal(response.status_code, 403)
    return


def test_metrics_refuse_a_wrong_bearer_token():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: with a token file configured, a wrong token answers 401
    with a Bearer challenge.**
    """
    token_file = tempfile.NamedTemporaryFile("w", delete=False, suffix=".token")
    token_file.write("right-token\n")
    token_file.close()
    try:
        with _no_metrics_config(), _EnvPatch(**{operations.ENV_METRICS_TOKEN_FILE: token_file.name}):
            response = operations_routes.handle_metrics(
                _FakeRequest(path="/metrics", headers={"Authorization": "Bearer wrong-token"})
            )
    finally:
        os.unlink(token_file.name)
    testbase.assert_equal(
        (response.status_code, response.headers.get("WWW-Authenticate", "").startswith("Bearer")),
        (401, True),
    )
    return


def test_metrics_serve_prometheus_text_with_the_right_token():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: the configured bearer token gets 200 in the Prometheus
    text format, including pychestrate_up.**
    """
    token_file = tempfile.NamedTemporaryFile("w", delete=False, suffix=".token")
    token_file.write("right-token\n")
    token_file.close()
    try:
        with _no_metrics_config(), _EnvPatch(**{operations.ENV_METRICS_TOKEN_FILE: token_file.name}):
            response = operations_routes.handle_metrics(
                _FakeRequest(path="/metrics", headers={"Authorization": "Bearer right-token"})
            )
    finally:
        os.unlink(token_file.name)
    text = response.body.decode("utf-8")
    testbase.assert_equal(
        (response.status_code, response.headers["Content-Type"], "\npychestrate_up " in text),
        (200, prometheus.EXPOSITION_CONTENT_TYPE, True),
    )
    return


def test_metrics_public_opt_in_serves_without_a_token():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: PYCHESTRATE_METRICS_PUBLIC=true serves /metrics without
    credentials.**
    """
    with _no_metrics_config(), _EnvPatch(**{operations.ENV_METRICS_PUBLIC: "true"}):
        response = operations_routes.handle_metrics(_FakeRequest(path="/metrics"))
    testbase.assert_equal(response.status_code, 200)
    return


def test_unreadable_token_file_keeps_metrics_closed():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: a token file that cannot be read fails closed (401),
    even with PYCHESTRATE_METRICS_PUBLIC set.**
    """
    with _no_metrics_config(), _EnvPatch(**{
            operations.ENV_METRICS_TOKEN_FILE: "/nonexistent/metrics-token",
            operations.ENV_METRICS_PUBLIC: "true"}):
        decision = operations.metrics_access(authorization=None)
    testbase.assert_equal((decision.allowed, decision.status), (False, 401))
    return


# ---------------------------------------------------------------------------
# Exposition content
# ---------------------------------------------------------------------------


def test_exposition_reports_the_newest_completed_backup():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: pychestrate_backup_last_success_timestamp_seconds is the
    completion time of the newest completed backup, and backups are
    counted by status.**
    """
    _, factory = _sqlite_factory(tables=[BackupRecord, Run])
    session = factory()
    finished = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)
    session.add(BackupRecord(backup_id=new_uuid(), status=BackupStatus.COMPLETED, backend="local",
                             manifest={}, note="", completed_at=finished))
    session.add(BackupRecord(backup_id=new_uuid(), status=BackupStatus.FAILED, backend="local",
                             manifest={}, note=""))
    session.commit()
    session.close()
    text = prometheus.render_exposition(families=operations.collect_metric_families(
        runtime_environment="testing", session_factory=factory,
    ))
    testbase.assert_equal(
        (
            "pychestrate_backup_last_success_timestamp_seconds {}".format(int(finished.timestamp())) in text,
            'pychestrate_backups{status="completed"} 1' in text,
            'pychestrate_backups{status="failed"} 1' in text,
        ),
        (True, True, True),
    )
    return


def test_exposition_counts_runs_by_state():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: pychestrate_runs carries one gauge per run state.**
    """
    _, factory = _sqlite_factory(tables=[BackupRecord, Run])
    session = factory()
    for state in (RunState.RUNNING, RunState.RUNNING, RunState.COMPLETED):
        session.add(Run(run_id=new_uuid(), project_id=new_uuid(), job_type="rpa", state=state))
    session.commit()
    session.close()
    text = prometheus.render_exposition(families=operations.collect_metric_families(
        runtime_environment="testing", session_factory=factory,
    ))
    running = 'pychestrate_runs{{state="{}"}} 2'.format(RunState.RUNNING.value)
    testbase.assert_true(running in text, text)
    return


def test_wsgi_layer_counts_responses_for_metrics():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: a response through the platform request-metrics layer
    increments pychestrate_http_requests_total and the latency
    histogram.**
    """
    def inner(environ: Dict[str, Any], start_response: Any) -> Any:
        start_response("404 Not Found", [("Content-Type", "application/json")])
        return [b"{}"]

    app = wrap_wsgi_application_with_request_metrics(wsgi_app=inner)
    before = operations.HTTP_REQUESTS_TOTAL.value(labels=("DELETE", "4xx"))
    before_count = operations.HTTP_REQUEST_DURATION.count(labels=("DELETE",))
    list(app({"REQUEST_METHOD": "DELETE", "PATH_INFO": "/x"}, lambda status, headers, exc_info=None: None))
    after = operations.HTTP_REQUESTS_TOTAL.value(labels=("DELETE", "4xx"))
    after_count = operations.HTTP_REQUEST_DURATION.count(labels=("DELETE",))
    testbase.assert_equal((after - before, after_count - before_count), (1.0, 1.0))
    return


def test_histogram_exposition_is_cumulative_with_inf_sum_and_count():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: histogram buckets are cumulative and end with +Inf,
    _sum and _count.**
    """
    histogram = prometheus.HistogramMetric(name="t_seconds", help="t", label_names=(), buckets=(0.1, 1.0))
    for value in (0.05, 0.5, 5.0):
        histogram.observe(value=value)
    text = prometheus.render_exposition(families=[histogram.collect()])
    expected = [
        't_seconds_bucket{le="0.1"} 1',
        't_seconds_bucket{le="1"} 2',
        't_seconds_bucket{le="+Inf"} 3',
        "t_seconds_sum 5.55",
        "t_seconds_count 3",
    ]
    testbase.assert_equal([line for line in expected if line not in text], [])
    return


def test_label_values_are_escaped():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: quotes, backslashes and newlines in label values are
    escaped in the exposition.**
    """
    testbase.assert_equal(
        prometheus.format_labels([("a", 'x"y\\z\nw')]),
        '{a="x\\"y\\\\z\\nw"}',
    )
    return


# ---------------------------------------------------------------------------
# System-health summary
# ---------------------------------------------------------------------------


def test_anonymous_monitor_gets_the_overall_health_status():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: /api/v1/system/health without a principal answers 200
    with the overall status and no subsystem details (it was 401).**
    """
    class _Request:
        path = "/api/v1/system/health"
        db_session = object()
        auth_principal = None

    response = system_health_routes.handle_system_health(_Request())
    body = _body(response)
    testbase.assert_equal(
        (response.status_code, body.get("details"), "subsystems" in body),
        (200, "restricted", False),
    )
    return


def test_system_health_is_on_the_anonymous_allowlist():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: the session middleware lets an anonymous GET of
    /api/v1/system/health through (and still refuses other methods).**
    """
    testbase.assert_equal(
        (
            is_anonymous_request_permitted("GET", "/api/v1/system/health"),
            is_anonymous_request_permitted("POST", "/api/v1/system/health"),
        ),
        (True, False),
    )
    return


# ---------------------------------------------------------------------------
# Registration, inventory, setup gate
# ---------------------------------------------------------------------------


def test_operations_routes_are_registered():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: register_operations_routes attaches GET for /livez,
    /__health/live, /readyz, /healthz, /__health/ready and /metrics.**
    """
    app = _FakeApp()
    operations_routes.register_operations_routes(app=app)
    attached = sorted(path for path, methods, _ in app.calls if methods == ("GET",))
    testbase.assert_equal(attached, sorted(operations.OPERATIONS_PATHS))
    return


def test_service_bootstrap_registers_the_operations_routes():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: register_service_extensions in app_pychestrate_main
    calls register_operations_routes.**
    """
    here = os.path.dirname(os.path.abspath(__file__))
    main_path = os.path.normpath(os.path.join(
        here, "..", "..", "..", "..", "..", "..", "..", "..", "source", "site", "app_pychestrate_main.py",
    ))
    with open(main_path, "r", encoding="utf-8") as handle:
        text = handle.read()
    section = text[text.index("def register_service_extensions"):text.index("def pychestrate_website_main")]
    testbase.assert_true("register_operations_routes(app=app)" in section)
    return


def test_every_operations_endpoint_is_in_the_anonymous_inventory_with_a_reason():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: each operations path matches exactly one GET entry of
    ANONYMOUS_OPERATIONS_ENDPOINTS, and every entry states a reason.**
    """
    problems: List[str] = []
    for path in operations.OPERATIONS_PATHS:
        matches = [entry for entry in ANONYMOUS_OPERATIONS_ENDPOINTS
                   if entry.method == "GET" and entry.pattern.match(path)]
        if len(matches) != 1 or len(matches[0].reason.strip()) == 0:
            problems.append(path)
    testbase.assert_equal(problems, [])
    return


def test_probes_pass_the_setup_gate_while_setup_is_pending():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: before the setup wizard completes, the gate lets every
    operations endpoint through instead of redirecting it.**
    """
    gate = PychestrateSetupGateMiddleware(is_complete=lambda: False, build_redirect=lambda target: "redirect")
    redirected = [
        path for path in operations.OPERATIONS_PATHS
        if gate(_FakeRequest(path=path), lambda request: "handled") != "handled"
    ]
    testbase.assert_equal(redirected, [])
    return


# ---------------------------------------------------------------------------
# Log rotation
# ---------------------------------------------------------------------------


def test_deploy_installs_log_rotation_for_the_unit_logs():
    """
    **Feature: operator monitoring (ORG-F17)**
    **Property: the logrotate template rotates server.log and backup.log
    with copytruncate (systemd keeps its append descriptor), and the
    deploy installs it as /etc/logrotate.d/pychestrate.**
    """
    root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "..", "..", "..", "..", "..", "..", ".."))
    with open(os.path.join(root, "deployment", "pychestrate.logrotate.template"), "r", encoding="utf-8") as handle:
        policy = handle.read()
    with open(os.path.join(root, "deployment", "deploy-alpha-to-host.sh"), "r", encoding="utf-8") as handle:
        script = handle.read()
    testbase.assert_equal(
        (
            "/home/@USER@/.pychestrate/server.log" in policy,
            "/home/@USER@/.pychestrate/backup.log" in policy,
            re.search(r"^\s*copytruncate\s*$", policy, re.MULTILINE) is not None,
            "/etc/logrotate.d/pychestrate" in script,
        ),
        (True, True, True, True),
    )
    return
