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
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

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


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_runs_routes_attaches_five_endpoints():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: register_runs_routes attaches the five planned
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    runs_routes.register_runs_routes(app=app, version_prefix="/api/v1")
    expected_pairs = (
        ("/api/v1/runs", ("GET",)),
        ("/api/v1/runs/{run_id}", ("GET",)),
        ("/api/v1/runs/{run_id}/dispatch-ack", ("POST",)),
        ("/api/v1/runs/{run_id}/progress", ("POST",)),
        ("/api/v1/runs/{run_id}/results/complete", ("POST",)),
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
    try:
        request = _FakeRequest(
            path="/api/v1/runs",
            db_session=session,
            auth_principal=_FakePrincipal(),
        )
        response = runs_routes.handle_list_runs(request)
    finally:
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
