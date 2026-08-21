"""
.. module:: test_p19c_runs_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the runs read endpoints (GET /api/v1/runs and GET /api/v1/runs/{id}).

.. moduleauthor:: Code Craft AI LLC

Covers the operator-facing surface added in PR p19c:

* GET /api/v1/runs -- list with pagination.
* GET /api/v1/runs/{run_id} -- single fetch.
* 401 when no auth principal is bound.
* 503 when no db session is bound.
* 404 problem when the run is unknown.

Also covers the run-serializer enrichment: dispatch / envelope
fields, progress_summary from the ingest tables, and the timing
fields derived from the state-audit trail.
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
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
)
from ccai.pychestrate.webservice.jobs.run.state.enums import RunState
from ccai.pychestrate.webservice.jobs.run.state.errors import RunNotFoundError
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes


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
        mtls_client_cn: Optional[str] = None,
        environ: Optional[Dict[str, str]] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        if mtls_client_cn is not None:
            self.mtls_client_cn: str = mtls_client_cn
        if environ is not None:
            self.environ: Dict[str, str] = environ
        return

    def json(self) -> Any:
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


class _FakePrincipal:
    def __init__(self, *, user_id: str = "user-1") -> None:
        self.user_id: str = user_id
        return


class _FakeRun:
    def __init__(
        self,
        *,
        run_id: str = "run-1",
        project_id: str = "proj-1",
        job_type: str = "test",
        state: RunState = RunState.PENDING,
        terminal_outcome: Optional[Any] = None,
        entered_state_at: Optional[Any] = None,
    ) -> None:
        from datetime import datetime, timezone
        self.run_id: str = run_id
        self.project_id: str = project_id
        self.job_type: str = job_type
        self.state: RunState = state
        self.terminal_outcome: Optional[Any] = terminal_outcome
        self.entered_state_at: Any = (
            entered_state_at
            if entered_state_at is not None
            else datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
        )
        return


class _FakeQuery:
    """
        Minimal SQLAlchemy query stand-in. Captures the filter
        kwargs the route applies (for assertions) but is otherwise
        a no-op.
    """

    def __init__(self, *, rows: List[Any], total: Optional[int] = None) -> None:
        self._rows: List[Any] = rows
        self._total: int = total if total is not None else len(rows)
        self.filters_applied: int = 0
        return

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        self.filters_applied += 1
        rtnval = self
        return rtnval

    def order_by(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        rtnval = self
        return rtnval

    def offset(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        rtnval = self
        return rtnval

    def limit(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        rtnval = self
        return rtnval

    def all(self) -> List[Any]:
        rtnval = list(self._rows)
        return rtnval

    def count(self) -> int:
        rtnval = self._total
        return rtnval


class _FakeSession:
    def __init__(self, *, query_result: Any) -> None:
        self._query_result: Any = query_result
        return

    def query(self, *args: Any, **kwargs: Any) -> Any:
        rtnval = self._query_result
        return rtnval


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
    """
        Patch ``runs_routes.rbac_evaluator.check_permission`` to
        return a fake decision.
    """
    patch = create_module_patch(runs_routes.rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


class _FakeAttempt:
    def __init__(
        self,
        *,
        attempt_id: str = "attempt-1",
        pod_id: str = "pod-1",
        client_id: str = "client-1",
        envelope_id: str = "env-1",
    ) -> None:
        self.attempt_id: str = attempt_id
        self.pod_id: str = pod_id
        self.client_id: str = client_id
        self.envelope_id: str = envelope_id
        return


class _FakeEnvelopeRecord:
    def __init__(
        self,
        *,
        job_id: str = "job-1",
        job_name: str = "nightly-regression",
    ) -> None:
        self.job_id: str = job_id
        self.canonical_payload_text: str = json.dumps(
            {"job_id": job_id, "job_name": job_name},
        )
        return


class _FakeAudit:
    def __init__(
        self,
        *,
        to_state: RunState,
        transitioned_at: datetime,
    ) -> None:
        self.to_state: RunState = to_state
        self.transitioned_at: datetime = transitioned_at
        return


class _FakeProgressSummary:
    def __init__(self) -> None:
        self.run_id: str = "run-1"
        self.client_id: str = "client-1"
        self.format_tag: str = "testbase"
        self.tests_total: Optional[int] = 100
        self.tests_passed: int = 40
        self.tests_failed: int = 2
        self.tests_skipped: int = 1
        self.tests_errored: int = 0
        self.percent_complete: Optional[float] = 43.0
        self.notes: Optional[str] = None
        self.recorded_at: datetime = datetime(
            2026, 5, 17, 12, 30, 0, tzinfo=timezone.utc,
        )
        return


class _FakeProgressFrame:
    def __init__(self) -> None:
        self.run_id: str = "run-1"
        self.client_id: str = "client-1"
        self.frame_kind: str = "build"
        self.phase: Optional[str] = "compiling"
        self.status: Optional[str] = "running"
        self.percent_complete: Optional[float] = 61.5
        self.notes: Optional[str] = None
        self.recorded_at: datetime = datetime(
            2026, 5, 17, 12, 31, 0, tzinfo=timezone.utc,
        )
        return


def _patch_seam(*, module: Any, name: str, result: Any) -> Any:
    """
        Patch one serializer-enrichment seam to return a fixed
        result (or, for callables, the callable's outcome).
    """
    patch = create_module_patch(module, name)
    mock = patch.activate()
    if callable(result) and not isinstance(result, (list, dict)):
        mock.configure(side_effect=result)
    else:
        mock.configure(side_effect=lambda **kwargs: result)
    return patch


def _patch_enrichment(
    *,
    attempts: Optional[List[Any]] = None,
    envelope: Optional[Any] = None,
    audits: Optional[List[Any]] = None,
    summary: Optional[Any] = None,
    frame: Optional[Any] = None,
    manifest_outbox_row: Optional[Any] = None,
) -> List[Any]:
    """
        Patch every feature-table seam the run serializer joins in.
        Defaults model a run with no dispatch / progress / audit
        history so the pre-enrichment assertions keep holding.
    """
    patches: List[Any] = []
    patches.append(
        _patch_seam(
            module=runs_routes.run_repo,
            name="find_latest_outbox_row_for_topic",
            result=manifest_outbox_row,
        )
    )
    patches.append(
        _patch_seam(
            module=runs_routes.dispatch_repo,
            name="list_attempts_for_run",
            result=attempts if attempts is not None else [],
        )
    )
    patches.append(
        _patch_seam(
            module=runs_routes.envelope_repo,
            name="get_envelope",
            result=envelope,
        )
    )
    patches.append(
        _patch_seam(
            module=runs_routes.run_repo,
            name="list_state_audits",
            result=audits if audits is not None else [],
        )
    )
    patches.append(
        _patch_seam(
            module=runs_routes.progress_service,
            name="get_summary",
            result=summary,
        )
    )
    patches.append(
        _patch_seam(
            module=runs_routes.progress_service,
            name="get_latest_frame",
            result=frame,
        )
    )
    return patches


def _deactivate_all(patches: List[Any]) -> None:
    for patch in reversed(patches):
        patch.deactivate()
    return


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_runs_routes_attaches_six_endpoints():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: register_runs_routes attaches the six planned
    method+path pairs from the OpenAPI spec (the five read/ingest
    endpoints plus the operator cancel endpoint).**
    """
    app = _FakeApp()
    runs_routes.register_runs_routes(app=app, version_prefix="/api/v1")
    expected_pairs = (
        ("/api/v1/runs", ("GET",)),
        ("/api/v1/runs/{run_id}", ("GET",)),
        ("/api/v1/runs/{run_id}/dispatch-ack", ("POST",)),
        ("/api/v1/runs/{run_id}/progress", ("POST",)),
        ("/api/v1/runs/{run_id}/results/complete", ("POST",)),
        ("/api/v1/runs/{run_id}/cancel", ("POST",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# 503 / 401 sweep
# ---------------------------------------------------------------------------


def test_handle_list_runs_returns_503_when_session_missing():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: GET /api/v1/runs returns 503 problem when the
    request-scoped db session is not bound.**
    """
    request = _FakeRequest(path="/api/v1/runs", db_session=None)
    response = runs_routes.handle_list_runs(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_list_runs_returns_401_when_no_principal():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: GET /api/v1/runs returns 401 when no
    AuthPrincipal has been bound by the session middleware.**
    """
    request = _FakeRequest(
        path="/api/v1/runs",
        db_session=object(),
        auth_principal=None,
    )
    response = runs_routes.handle_list_runs(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_handle_read_run_returns_503_when_session_missing():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: GET /api/v1/runs/{id} returns 503 problem when
    the request-scoped db session is not bound.**
    """
    request = _FakeRequest(
        path="/api/v1/runs/run-1",
        path_params={"run_id": "run-1"},
        db_session=None,
    )
    response = runs_routes.handle_read_run(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_read_run_returns_401_when_no_principal():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: GET /api/v1/runs/{id} returns 401 when no
    AuthPrincipal is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/runs/run-1",
        path_params={"run_id": "run-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = runs_routes.handle_read_run(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_handle_list_runs_returns_403_when_permission_denied():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: GET /api/v1/runs returns 403 when the principal
    does not hold system:runs.read.**
    """
    patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/runs",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = runs_routes.handle_list_runs(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:runs.read")
    return


# ---------------------------------------------------------------------------
# GET /api/v1/runs -- happy path / pagination
# ---------------------------------------------------------------------------


def test_handle_list_runs_returns_page_envelope_with_default_pagination():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: With an authenticated principal holding
    system:runs.read, GET /api/v1/runs returns a
    ``{items, meta}`` page envelope shaped per the OpenAPI
    ``RunPage`` schema -- defaults to page=1, per_page=50.**
    """
    rows = [_FakeRun(run_id="run-1"), _FakeRun(run_id="run-2")]
    session = _FakeSession(query_result=_FakeQuery(rows=rows, total=2))

    patch = _patch_check_permission(allowed=True)
    enrichment = _patch_enrichment()
    try:
        request = _FakeRequest(
            path="/api/v1/runs",
            db_session=session,
            auth_principal=_FakePrincipal(),
        )
        response = runs_routes.handle_list_runs(request)
    finally:
        _deactivate_all(enrichment)
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 2)
    testbase.assert_equal(body["items"][0]["run_id"], "run-1")
    testbase.assert_equal(body["meta"]["page"], 1)
    testbase.assert_equal(body["meta"]["per_page"], 50)
    testbase.assert_equal(body["meta"]["total"], 2)
    return


def test_handle_list_runs_honors_explicit_pagination_query():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: explicit page / per_page query params propagate
    through into the ``meta`` envelope.**
    """
    session = _FakeSession(query_result=_FakeQuery(rows=[], total=120))
    patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/runs",
            db_session=session,
            auth_principal=_FakePrincipal(),
            query={"page": "3", "per_page": "25"},
        )
        response = runs_routes.handle_list_runs(request)
    finally:
        patch.deactivate()
    body = _decode_body(response)
    testbase.assert_equal(body["meta"]["page"], 3)
    testbase.assert_equal(body["meta"]["per_page"], 25)
    testbase.assert_equal(body["meta"]["total"], 120)
    return


def test_handle_list_runs_returns_400_on_non_integer_page():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: A non-integer page query value is rejected with
    400 problem+json carrying the offending raw value.**
    """
    patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/runs",
            db_session=_FakeSession(query_result=_FakeQuery(rows=[])),
            auth_principal=_FakePrincipal(),
            query={"page": "garbage"},
        )
        response = runs_routes.handle_list_runs(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["raw_value"], "garbage")
    return


# ---------------------------------------------------------------------------
# GET /api/v1/runs/{id}
# ---------------------------------------------------------------------------


def test_handle_read_run_returns_run_dict_on_match():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: GET /api/v1/runs/{id} returns 200 with a Run
    dict matching the OpenAPI Run schema's required fields.**
    """
    row = _FakeRun(run_id="run-7", project_id="proj-9", state=RunState.RUNNING)

    perm_patch = _patch_check_permission(allowed=True)
    enrichment = _patch_enrichment()
    repo_patch = create_module_patch(runs_routes.run_repo, "get_run")
    repo_mock = repo_patch.activate()
    repo_mock.configure(side_effect=lambda **kwargs: row)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-7",
            path_params={"run_id": "run-7"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = runs_routes.handle_read_run(request)
    finally:
        repo_patch.deactivate()
        _deactivate_all(enrichment)
        perm_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "run-7")
    testbase.assert_equal(body["project_id"], "proj-9")
    testbase.assert_equal(body["state"], "running")
    testbase.assert_equal(body["job_type"], "test")
    return


def test_handle_read_run_returns_404_on_unknown_run():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: RunNotFoundError raised by the repository is
    mapped to 404 problem+json carrying the run_id.**
    """
    def raise_missing(**kwargs: Any) -> Any:
        raise RunNotFoundError("missing run")

    perm_patch = _patch_check_permission(allowed=True)
    repo_patch = create_module_patch(runs_routes.run_repo, "get_run")
    repo_mock = repo_patch.activate()
    repo_mock.configure(side_effect=raise_missing)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-missing",
            path_params={"run_id": "run-missing"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = runs_routes.handle_read_run(request)
    finally:
        repo_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["run_id"], "run-missing")
    return


# ---------------------------------------------------------------------------
# Run serializer enrichment
# ---------------------------------------------------------------------------


def test_run_dict_populates_dispatch_progress_and_timing_fields():
    """
    **Feature: run-detail data path**
    **Property: the Run serializer joins pod / client / attempt
    ids from the latest dispatch attempt, job identity from the
    archived envelope, progress_summary from the latest ingested
    summary, and the timing fields from the state-audit trail.**
    """
    created = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
    dispatched = datetime(2026, 5, 17, 12, 0, 5, tzinfo=timezone.utc)
    started = datetime(2026, 5, 17, 12, 0, 9, tzinfo=timezone.utc)
    completed = datetime(2026, 5, 17, 12, 45, 0, tzinfo=timezone.utc)
    audits = [
        _FakeAudit(to_state=RunState.DISPATCHING, transitioned_at=created),
        _FakeAudit(to_state=RunState.DISPATCHED, transitioned_at=dispatched),
        _FakeAudit(to_state=RunState.RUNNING, transitioned_at=started),
        _FakeAudit(to_state=RunState.COMPLETED, transitioned_at=completed),
    ]

    row = _FakeRun(
        run_id="run-1",
        state=RunState.COMPLETED,
        entered_state_at=completed,
    )

    enrichment = _patch_enrichment(
        attempts=[_FakeAttempt()],
        envelope=_FakeEnvelopeRecord(),
        audits=audits,
        summary=_FakeProgressSummary(),
    )
    try:
        body = runs_routes._run_to_dict(row=row, db_session=object())
    finally:
        _deactivate_all(enrichment)

    testbase.assert_equal(body["pod_id"], "pod-1")
    testbase.assert_equal(body["client_id"], "client-1")
    testbase.assert_equal(body["current_dispatch_attempt_id"], "attempt-1")
    testbase.assert_equal(body["job_id"], "job-1")
    testbase.assert_equal(body["job_name"], "nightly-regression")

    testbase.assert_equal(body["created_at"], created.isoformat())
    testbase.assert_equal(body["dispatched_at"], dispatched.isoformat())
    testbase.assert_equal(body["started_at"], started.isoformat())
    testbase.assert_equal(body["completed_at"], completed.isoformat())

    summary = body["progress_summary"]
    testbase.assert_true(summary is not None)
    testbase.assert_equal(summary["format_tag"], "testbase")
    testbase.assert_equal(summary["tests_total"], 100)
    testbase.assert_equal(summary["tests_passed"], 40)
    testbase.assert_equal(summary["tests_failed"], 2)
    testbase.assert_equal(summary["percent_complete"], 43.0)
    return


def test_run_dict_created_at_is_stable_across_state_changes():
    """
    **Feature: run-detail data path**
    **Property: created_at comes from the first state-audit row,
    not from the mutable entered_state_at -- so the "Created"
    column no longer moves on every transition.**
    """
    created = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
    later = datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)
    audits = [
        _FakeAudit(to_state=RunState.DISPATCHING, transitioned_at=created),
        _FakeAudit(to_state=RunState.DISPATCHED, transitioned_at=later),
    ]
    row = _FakeRun(
        run_id="run-1",
        state=RunState.DISPATCHED,
        entered_state_at=later,
    )

    enrichment = _patch_enrichment(audits=audits)
    try:
        body = runs_routes._run_to_dict(row=row, db_session=object())
    finally:
        _deactivate_all(enrichment)

    testbase.assert_equal(body["created_at"], created.isoformat())
    testbase.assert_equal(body["completed_at"], None)
    return


def test_run_dict_progress_summary_falls_back_to_build_frame():
    """
    **Feature: run-detail data path**
    **Property: a build / provision run with no test summary maps
    its latest generalized progress frame into progress_summary,
    carrying frame_kind / phase / status / percent_complete.**
    """
    row = _FakeRun(run_id="run-1", state=RunState.RUNNING)

    enrichment = _patch_enrichment(frame=_FakeProgressFrame())
    try:
        body = runs_routes._run_to_dict(row=row, db_session=object())
    finally:
        _deactivate_all(enrichment)

    summary = body["progress_summary"]
    testbase.assert_true(summary is not None)
    testbase.assert_equal(summary["format_tag"], "build")
    testbase.assert_equal(summary["frame_kind"], "build")
    testbase.assert_equal(summary["phase"], "compiling")
    testbase.assert_equal(summary["status"], "running")
    testbase.assert_equal(summary["percent_complete"], 61.5)
    testbase.assert_equal(summary["tests_passed"], 0)
    return


def test_run_dict_emits_nulls_for_undispatched_run():
    """
    **Feature: run-detail data path**
    **Property: a never-dispatched run with no progress serializes
    null dispatch / job / progress fields and created_at falls
    back to entered_state_at.**
    """
    row = _FakeRun(run_id="run-1", state=RunState.PENDING)

    enrichment = _patch_enrichment()
    try:
        body = runs_routes._run_to_dict(row=row, db_session=object())
    finally:
        _deactivate_all(enrichment)

    testbase.assert_equal(body["pod_id"], None)
    testbase.assert_equal(body["client_id"], None)
    testbase.assert_equal(body["job_id"], None)
    testbase.assert_equal(body["job_name"], None)
    testbase.assert_equal(body["current_dispatch_attempt_id"], None)
    testbase.assert_equal(body["progress_summary"], None)
    testbase.assert_equal(body["result_manifest"], None)
    testbase.assert_equal(body["created_at"], row.entered_state_at.isoformat())
    testbase.assert_equal(body["dispatched_at"], None)
    testbase.assert_equal(body["started_at"], None)
    testbase.assert_equal(body["completed_at"], None)
    return


class _FakeManifestOutboxRow:
    def __init__(self) -> None:
        self.payload: Dict[str, Any] = {
            "run_id": "run-1",
            "project_id": "proj-1",
            "terminal_outcome": "success",
            "manifest": {
                "run_id": "run-1",
                "format_tag": "testbase",
                "terminal_outcome": "success",
                "summary_artifact_path": "testrun_summary.json",
                "results_stream_artifact_path": "testrun_results_stream.jsos",
                "results_artifact_path": "testrun_results.json",
                "html_summary_artifact_path": "testsummary.html",
                "tests_passed": 40,
                "tests_failed": 2,
                "artifact_count": 3,
                "files": [],
            },
        }
        return


def test_read_run_includes_recorded_result_manifest():
    """
    **Feature: run-detail data path**
    **Property: GET /api/v1/runs/{id} recalls the latest recorded
    result-manifest block from the durable outbox and serves it
    under the `result_manifest` key, so a run-detail page opened
    on an already-completed run renders its artifacts pane on
    load.**
    """
    row = _FakeRun(run_id="run-1", state=RunState.COMPLETED)

    perm_patch = _patch_check_permission(allowed=True)
    enrichment = _patch_enrichment(
        manifest_outbox_row=_FakeManifestOutboxRow(),
    )
    repo_patch = create_module_patch(runs_routes.run_repo, "get_run")
    repo_mock = repo_patch.activate()
    repo_mock.configure(side_effect=lambda **kwargs: row)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1",
            path_params={"run_id": "run-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = runs_routes.handle_read_run(request)
    finally:
        repo_patch.deactivate()
        _deactivate_all(enrichment)
        perm_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    manifest = body["result_manifest"]
    testbase.assert_true(manifest is not None)
    testbase.assert_equal(
        manifest["html_summary_artifact_path"], "testsummary.html",
    )
    testbase.assert_equal(manifest["tests_passed"], 40)
    testbase.assert_equal(manifest["tests_failed"], 2)
    testbase.assert_equal(manifest["terminal_outcome"], "success")
    return


def test_list_runs_leaves_result_manifest_null():
    """
    **Feature: run-detail data path**
    **Property: list pages never load the recorded manifest --
    `result_manifest` is null in list items even when the outbox
    holds one, keeping large pages lean.**
    """
    rows = [_FakeRun(run_id="run-1", state=RunState.COMPLETED)]
    session = _FakeSession(query_result=_FakeQuery(rows=rows, total=1))

    perm_patch = _patch_check_permission(allowed=True)
    enrichment = _patch_enrichment(
        manifest_outbox_row=_FakeManifestOutboxRow(),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/runs",
            db_session=session,
            auth_principal=_FakePrincipal(),
        )
        response = runs_routes.handle_list_runs(request)
    finally:
        _deactivate_all(enrichment)
        perm_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["items"][0]["result_manifest"], None)
    return
