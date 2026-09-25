"""
.. module:: test_p19d_test_runs_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the test-runs trigger REST endpoint (PR p19d).

.. moduleauthor:: Code Craft AI LLC

Covers the planned ``test_runs`` operation:

* POST /api/v1/projects/{project_id}/test-runs

Auth (401/403), session boundary (503), project/catalog/pod
not-found (404), no-eligible-pod (409), malformed body (422),
and 202-on-happy-path each get explicit coverage.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase

from ccai.errors.exceptions import SemanticError
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from ccai.pychestrate.webservice.jobs.dispatch.errors import (
    DispatchNoCandidatesError,
)
from ccai.pychestrate.webservice.orchestration.test.errors import (
    CapabilityMismatchError,
)
from ccai.pychestrate.webservice.orchestration.test.models import (
    TestRunState,
)
from ccai.pychestrate.webservice.orchestration.test.restapi.v1 import (
    test_runs_routes,
)
from ccai.pychestrate.webservice.pods.models import (
    PodDefinition,
    PodRegistration,
    RegistrationState,
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
            body: Any = None,
            db_session: Optional[Any] = None,
            auth_principal: Optional[Any] = None
        ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
        self.query_params: _FakeQueryParams = _FakeQueryParams()
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
        resolved_methods = tuple(methods if methods is not None else ["POST"])

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
    def __init__(self, *, project_id: str, slug: str = "proj-slug") -> None:
        self.project_id: str = project_id
        self.slug: str = slug
        return


class _FakeCatalogEntry:
    def __init__(
            self,
            *,
            entry_id: str = "ent-1",
            project_id: str = "proj-1",
            importer_tag: str = "testbase-project",
            entry_key: str = "tests.thing.test_x",
            display_name: str = "Thing X",
            raw_metadata: Optional[Dict[str, Any]] = None
        ) -> None:
        self.entry_id: str = entry_id
        self.project_id: str = project_id
        self.importer_tag: str = importer_tag
        self.entry_key: str = entry_key
        self.display_name: str = display_name
        self.raw_metadata: Dict[str, Any] = (
            raw_metadata if raw_metadata is not None else {"runner_kind": "testbase"}
        )
        return


class _FakePodDefinition:
    def __init__(self, *, pod_id: str, project_id: str) -> None:
        self.pod_id: str = pod_id
        self.project_id: str = project_id
        return


class _FakePodRegistration:
    def __init__(
            self,
            *,
            pod_id: str,
            client_id: str,
            state: RegistrationState = RegistrationState.REGISTERED
        ) -> None:
        self.pod_id: str = pod_id
        self.client_id: str = client_id
        self.state: RegistrationState = state
        return


class _FakeQuery:
    """
        Minimal SQLAlchemy query stand-in driven by per-model dicts
        kept on the surrounding session.
    """

    def __init__(self, *, rows: List[Any]) -> None:
        self._rows: List[Any] = rows
        return

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        rtnval = self
        return rtnval

    def first(self) -> Optional[Any]:
        rtnval: Optional[Any]
        if len(self._rows) == 0:
            rtnval = None
        else:
            rtnval = self._rows[0]
        return rtnval

    def all(self) -> List[Any]:
        rtnval = list(self._rows)
        return rtnval


class _FakeSession:
    def __init__(
            self,
            *,
            pods: Optional[List[Any]] = None,
            registrations: Optional[List[Any]] = None
        ) -> None:
        self._pods: List[Any] = pods if pods is not None else []
        self._registrations: List[Any] = registrations if registrations is not None else []
        return

    def query(self, model: Any) -> _FakeQuery:
        if model is PodDefinition:
            rtnval = _FakeQuery(rows=self._pods)
        elif model is PodRegistration:
            rtnval = _FakeQuery(rows=self._registrations)
        else:
            rtnval = _FakeQuery(rows=[])
        return rtnval


class _FakeDispatchOutcome:
    def __init__(self, *, attempt_id: str = "attempt-1") -> None:
        self.attempt_id: str = attempt_id
        return


class _FakeTriggerOutcome:
    def __init__(
            self,
            *,
            run_id: str = "run-1",
            test_run_state: TestRunState = TestRunState.DISPATCHED,
            attempt_id: str = "attempt-1",
            catalog_entry_id: str = "ent-1",
            catalog_digest: str = "deadbeef"
        ) -> None:
        self.run_id: str = run_id
        self.test_run_state: TestRunState = test_run_state
        self.dispatch: _FakeDispatchOutcome = _FakeDispatchOutcome(attempt_id=attempt_id)
        self.catalog_entry_id: str = catalog_entry_id
        self.catalog_digest: str = catalog_digest
        return


class _FakeOrchestrator:
    def __init__(self, *, outcome: Optional[Any] = None, raise_with: Optional[Exception] = None) -> None:
        self._outcome: Optional[Any] = outcome
        self._raise_with: Optional[Exception] = raise_with
        return

    def trigger_run(self, *, db_session: Any, request: Any) -> Any:
        if self._raise_with is not None:
            raise self._raise_with
        rtnval = self._outcome
        return rtnval


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(test_runs_routes.rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(test_runs_routes.projects_repo, "get_project_by_id")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _patch_catalog_find_by_id(*, row: Optional[Any]) -> Any:
    patch = create_module_patch(test_runs_routes.catalog_repo, "find_by_id")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: row)
    return patch


def _patch_catalog_find_entry(*, row: Optional[Any]) -> Any:
    patch = create_module_patch(test_runs_routes.catalog_repo, "find_entry")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: row)
    return patch


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_test_runs_routes_attaches_one_endpoint():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: register_test_runs_routes attaches POST
    /api/v1/projects/{project_id}/test-runs.**
    """
    app = _FakeApp()
    test_runs_routes.register_test_runs_routes(app=app, version_prefix="/api/v1")
    expected_pairs = (
        ("/api/v1/projects/{project_id}/test-runs", ("POST",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# Auth / session boundary
# ---------------------------------------------------------------------------


def test_trigger_returns_503_when_session_missing():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs returns 503 when no db_session is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/test-runs",
        path_params={"project_id": "proj-1"},
        db_session=None,
    )
    response = test_runs_routes.handle_trigger_test_run(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_trigger_returns_401_when_no_principal():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs returns 401 when no AuthPrincipal is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/test-runs",
        path_params={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = test_runs_routes.handle_trigger_test_run(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_trigger_returns_403_when_permission_denied():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs returns 403 when principal lacks
    system:test_runs.create.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"pod_id": "pod-1", "catalog_entry_id": "ent-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:test_runs.create")
    return


# ---------------------------------------------------------------------------
# Body validation
# ---------------------------------------------------------------------------


def test_trigger_returns_422_on_empty_body():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs returns 422 problem when body is
    missing entirely.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_trigger_returns_409_when_pod_id_omitted_and_no_eligible_pod():
    """
    **Feature: 6-test-orchestration PR p19q**
    **Property: POST test-runs returns 409 with an actionable
    no-eligible-pod message when 'pod_id' is omitted and the
    project has no enrolled pod.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cat_patch = _patch_catalog_find_by_id(row=_FakeCatalogEntry(entry_id="ent-1", project_id="proj-1"))
    try:
        session = _FakeSession(pods=[], registrations=[])
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=session,
            auth_principal=_FakePrincipal(),
            body={"catalog_entry_id": "ent-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        cat_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(body["reason"], "no_eligible_pod")
    testbase.assert_equal("enroll a client/pod first" in body["detail"], True)
    return


def test_trigger_returns_422_when_pod_id_is_empty_string():
    """
    **Feature: 6-test-orchestration PR p19q**
    **Property: POST test-runs returns 422 when 'pod_id' is present
    but an empty string.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"catalog_entry_id": "ent-1", "pod_id": ""},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_trigger_returns_422_when_catalog_identification_missing():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs returns 422 when neither
    catalog_entry_id nor (importer_tag, entry_key) is supplied.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"pod_id": "pod-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    return


def test_trigger_returns_404_when_project_missing():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs returns 404 when the project does
    not exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/test-runs",
            path_params={"project_id": "proj-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"pod_id": "pod-1", "catalog_entry_id": "ent-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    return


def test_trigger_returns_404_when_catalog_entry_missing():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs returns 404 with the catalog_entry_id
    in the extension when the entry is unknown.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cat_patch = _patch_catalog_find_by_id(row=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"pod_id": "pod-1", "catalog_entry_id": "ent-missing"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        cat_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["catalog_entry_id"], "ent-missing")
    return


def test_trigger_returns_404_when_pod_missing():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs returns 404 when the pod_id does
    not resolve.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cat_patch = _patch_catalog_find_by_id(row=_FakeCatalogEntry(entry_id="ent-1", project_id="proj-1"))
    try:
        session = _FakeSession(pods=[], registrations=[])
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=session,
            auth_principal=_FakePrincipal(),
            body={"pod_id": "pod-missing", "catalog_entry_id": "ent-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        cat_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["pod_id"], "pod-missing")
    return


def test_trigger_returns_409_when_no_active_registration():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs returns 409 when the pod exists but
    no active client registration is present.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cat_patch = _patch_catalog_find_by_id(row=_FakeCatalogEntry(entry_id="ent-1", project_id="proj-1"))
    try:
        session = _FakeSession(
            pods=[_FakePodDefinition(pod_id="pod-1", project_id="proj-1")],
            registrations=[],
        )
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=session,
            auth_principal=_FakePrincipal(),
            body={"pod_id": "pod-1", "catalog_entry_id": "ent-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        cat_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(body["pod_id"], "pod-1")
    return


# ---------------------------------------------------------------------------
# Orchestrator delegation
# ---------------------------------------------------------------------------


def test_trigger_returns_202_on_happy_path():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs returns 202 with a Run envelope
    carrying the run_id from the orchestrator outcome.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cat_patch = _patch_catalog_find_by_id(row=_FakeCatalogEntry(entry_id="ent-1", project_id="proj-1"))
    saved = test_runs_routes.ACTIVE_TEST_ORCHESTRATOR
    test_runs_routes.set_active_test_orchestrator(
        orchestrator=_FakeOrchestrator(outcome=_FakeTriggerOutcome(run_id="run-42")),
    )
    try:
        session = _FakeSession(
            pods=[_FakePodDefinition(pod_id="pod-1", project_id="proj-1")],
            registrations=[
                _FakePodRegistration(pod_id="pod-1", client_id="client-1"),
            ],
        )
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=session,
            auth_principal=_FakePrincipal(),
            body={"pod_id": "pod-1", "catalog_entry_id": "ent-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        test_runs_routes.set_active_test_orchestrator(orchestrator=saved)
        cat_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "run-42")
    testbase.assert_equal(body["project_id"], "proj-1")
    testbase.assert_equal(body["pod_id"], "pod-1")
    testbase.assert_equal(body["catalog_entry_id"], "ent-1")
    return


def test_trigger_returns_202_when_pod_id_omitted_and_orchestrator_selects():
    """
    **Feature: 6-test-orchestration PR p19q**
    **Property: POST test-runs without 'pod_id' returns 202 when an
    enrolled pod is available; the orchestrator picks the pod.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cat_patch = _patch_catalog_find_by_id(row=_FakeCatalogEntry(entry_id="ent-1", project_id="proj-1"))
    saved = test_runs_routes.ACTIVE_TEST_ORCHESTRATOR
    test_runs_routes.set_active_test_orchestrator(
        orchestrator=_FakeOrchestrator(outcome=_FakeTriggerOutcome(run_id="run-99")),
    )
    try:
        session = _FakeSession(
            pods=[_FakePodDefinition(pod_id="pod-1", project_id="proj-1")],
            registrations=[
                _FakePodRegistration(pod_id="pod-1", client_id="client-1"),
            ],
        )
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=session,
            auth_principal=_FakePrincipal(),
            body={"catalog_entry_id": "ent-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        test_runs_routes.set_active_test_orchestrator(orchestrator=saved)
        cat_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "run-99")
    return


def test_trigger_returns_409_when_orchestrator_raises_capability_mismatch():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs maps CapabilityMismatchError from
    the orchestrator to a 409 conflict problem.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cat_patch = _patch_catalog_find_by_id(row=_FakeCatalogEntry(entry_id="ent-1", project_id="proj-1"))
    saved = test_runs_routes.ACTIVE_TEST_ORCHESTRATOR
    test_runs_routes.set_active_test_orchestrator(
        orchestrator=_FakeOrchestrator(
            raise_with=CapabilityMismatchError("required cap missing"),
        ),
    )
    try:
        session = _FakeSession(
            pods=[_FakePodDefinition(pod_id="pod-1", project_id="proj-1")],
            registrations=[
                _FakePodRegistration(pod_id="pod-1", client_id="client-1"),
            ],
        )
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=session,
            auth_principal=_FakePrincipal(),
            body={"pod_id": "pod-1", "catalog_entry_id": "ent-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        test_runs_routes.set_active_test_orchestrator(orchestrator=saved)
        cat_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["reason"], "capability_mismatch")
    return


def test_trigger_returns_409_when_orchestrator_raises_no_candidates():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs maps DispatchNoCandidatesError
    from the dispatcher to a 409 conflict problem.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cat_patch = _patch_catalog_find_by_id(row=_FakeCatalogEntry(entry_id="ent-1", project_id="proj-1"))
    saved = test_runs_routes.ACTIVE_TEST_ORCHESTRATOR
    test_runs_routes.set_active_test_orchestrator(
        orchestrator=_FakeOrchestrator(
            raise_with=DispatchNoCandidatesError("no eligible"),
        ),
    )
    try:
        session = _FakeSession(
            pods=[_FakePodDefinition(pod_id="pod-1", project_id="proj-1")],
            registrations=[
                _FakePodRegistration(pod_id="pod-1", client_id="client-1"),
            ],
        )
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=session,
            auth_principal=_FakePrincipal(),
            body={"pod_id": "pod-1", "catalog_entry_id": "ent-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        test_runs_routes.set_active_test_orchestrator(orchestrator=saved)
        cat_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["reason"], "no_eligible_candidate")
    return


def test_trigger_returns_503_when_orchestrator_unconfigured():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-runs returns 503 when no orchestrator is
    bound on the module-level seam.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cat_patch = _patch_catalog_find_by_id(row=_FakeCatalogEntry(entry_id="ent-1", project_id="proj-1"))
    saved = test_runs_routes.ACTIVE_TEST_ORCHESTRATOR
    test_runs_routes.set_active_test_orchestrator(orchestrator=None)
    try:
        session = _FakeSession(
            pods=[_FakePodDefinition(pod_id="pod-1", project_id="proj-1")],
            registrations=[
                _FakePodRegistration(pod_id="pod-1", client_id="client-1"),
            ],
        )
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=session,
            auth_principal=_FakePrincipal(),
            body={"pod_id": "pod-1", "catalog_entry_id": "ent-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        test_runs_routes.set_active_test_orchestrator(orchestrator=saved)
        cat_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 503)
    return


def test_trigger_returns_422_when_runner_rejects_inputs():
    """
    **Feature: test-run trigger (live E2E finding)**
    **Property: a SemanticError from the runner's input validation (for
    example no includes) answers 422 with its message -- it used to
    escape the route, and the request hung until the client timed out.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cat_patch = _patch_catalog_find_by_id(row=_FakeCatalogEntry(entry_id="ent-1", project_id="proj-1"))
    saved = test_runs_routes.ACTIVE_TEST_ORCHESTRATOR
    test_runs_routes.set_active_test_orchestrator(
        orchestrator=_FakeOrchestrator(
            raise_with=SemanticError("Invalid testbase runner inputs."),
        ),
    )
    try:
        session = _FakeSession(
            pods=[_FakePodDefinition(pod_id="pod-1", project_id="proj-1")],
            registrations=[
                _FakePodRegistration(pod_id="pod-1", client_id="client-1"),
            ],
        )
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-runs",
            path_params={"project_id": "proj-1"},
            db_session=session,
            auth_principal=_FakePrincipal(),
            body={"pod_id": "pod-1", "catalog_entry_id": "ent-1"},
        )
        response = test_runs_routes.handle_trigger_test_run(request)
    finally:
        test_runs_routes.set_active_test_orchestrator(orchestrator=saved)
        cat_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    testbase.assert_equal(_decode_body(response)["reason"], "invalid_runner_inputs")
    return
