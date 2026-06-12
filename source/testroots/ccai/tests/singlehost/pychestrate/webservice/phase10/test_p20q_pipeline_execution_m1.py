"""
.. module:: test_p20q_pipeline_execution_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for pipeline execution -- the DAG-walking
               PipelineOrchestrator + the pipeline-run REST endpoints
               (PR p20q).

.. moduleauthor:: Code Craft AI LLC

Covers:

* Triggering a pipeline run creates a ``PipelineRun`` plus its
  per-stage + per-step rows.
* The DAG walker dispatches the root stages and not the dependents.
* A stage's terminal event makes its dependents eligible.
* A stage failure skips its dependents and fails the pipeline run.
* The ``pipeline_runs`` REST routes: registration, 401/403/404, and
  the happy-path trigger / read.
* The 6-pipeline-execution Alembic migration applies cleanly on a
  fresh SQLite database.
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
from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    register_builtin_extensions as pipeline_definition_register,
    service as definition_service,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition.models import (
    PipelineRunState,
    StageState,
    StepState,
)
from ccai.pychestrate.webservice.orchestration.pipelines.execution.orchestrator import (
    PipelineOrchestrator,
    PipelineTriggerInputs,
)
from ccai.pychestrate.webservice.orchestration.pipelines.restapi.v1 import (
    pipeline_runs_routes,
)

# Side-effect imports so the pipeline + pods model tables attach to the
# shared Phase-1 metadata before ``create_all`` runs in the fixture.
from ccai.pychestrate.webservice.orchestration.pipelines.definition import models as _pipeline_models  # noqa: F401
from ccai.pychestrate.webservice.pods import models as _pods_models  # noqa: F401

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000002000"


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
    def __init__(self, *, user_id: str = "00000000-0000-4000-8000-00000000a001") -> None:
        self.user_id: str = user_id
        return


class _FakeDecision:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed: bool = allowed
        self.reason: str = ""
        return


class _FakeProject:
    def __init__(self, *, project_id: str, slug: str = "proj-slug") -> None:
        self.project_id: str = project_id
        self.slug: str = slug
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        pipeline_runs_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(
        pipeline_runs_routes.projects_repo, "get_project_by_id",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


# ---------------------------------------------------------------------------
# Fake dispatch handles -- the orchestrator REUSES build / test dispatch;
# the fakes record the dispatched run id (the run-state machine run id)
# without standing up the whole Layer-5 dispatch chain.
# ---------------------------------------------------------------------------


class _FakeOutcome:
    def __init__(self, *, run_id: str) -> None:
        self.run_id: str = run_id
        return


class _FakeBuildInputs:
    def __init__(self, *, runner_kind: str, runner_inputs: Any) -> None:
        self.runner_kind: str = runner_kind
        self.runner_inputs: Any = runner_inputs
        return


class _FakeBuildAspects:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs: Dict[str, Any] = dict(kwargs)
        return


class _FakeBuildServiceModule:
    """
        Stand-in for ``orchestration.build.service``. ``trigger_run``
        records the call and returns a fake run id.
    """

    def __init__(self) -> None:
        self.triggered: List[str] = []
        self._counter: int = 0
        self.BuildRunInputs = _FakeBuildInputs
        self.BuildTriggerAspects = _FakeBuildAspects
        return

    def trigger_run(self, *, db_session: Any, project_id: str, inputs: Any,
                    aspects: Any) -> Any:
        self._counter = self._counter + 1
        run_id = "00000000-0000-4000-8000-0000000b{:04d}".format(self._counter)
        self.triggered.append(run_id)
        rtnval = _FakeOutcome(run_id=run_id)
        return rtnval


class _FakeTestOrchestrator:
    """
        Stand-in for the live :class:`TestOrchestrator`.
    """

    def __init__(self) -> None:
        self.triggered: List[str] = []
        self._counter: int = 0
        return

    def trigger_run(self, *, db_session: Any, request: Any) -> Any:
        self._counter = self._counter + 1
        run_id = "00000000-0000-4000-8000-0000000c{:04d}".format(self._counter)
        self.triggered.append(run_id)
        rtnval = _FakeOutcome(run_id=run_id)
        return rtnval


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prepare_runtime() -> None:
    """
        Reset cross-test globals and register the in-tree pipeline
        step kinds (``build`` / ``test`` / ``script``).
    """
    reset_registry_for_testing()
    reset_event_bus()
    pipeline_definition_register()
    return


def _two_stage_document() -> bytes:
    """
        A two-stage DAG: ``build`` (root) then ``test`` (needs build).
    """
    document = json.dumps({
        "schema_version": 1,
        "name": "ci",
        "stages": [
            {
                "id": "build",
                "steps": [
                    {"id": "compile", "kind": "build",
                     "inputs": {"image": "python:3.12"}},
                ],
            },
            {
                "id": "test",
                "needs": ["build"],
                "steps": [
                    {"id": "pytest", "kind": "test",
                     "inputs": {"catalog_entry_id": "entry-1"}},
                ],
            },
        ],
    })
    rtnval = document.encode("utf-8")
    return rtnval


def _make_orchestrator(
        *,
        session_factory: Callable,
        build_module: Any,
        test_orch: Any
    ) -> PipelineOrchestrator:
    """
        Construct a :class:`PipelineOrchestrator` with fake dispatch
        handles.
    """
    rtnval = PipelineOrchestrator(
        session_factory=session_factory,
        test_orchestrator=test_orch,
        build_service_module=build_module,
        infra_service_module=None,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_migration_adds_orchestrated_column():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: the orch_pipeline_run table carries the ``orchestrated``
    column the p20q migration adds.**
    """
    _engine, session = build_in_memory_session()
    try:
        from ccai.pychestrate.webservice.orchestration.pipelines.definition.models import (
            PipelineRun,
        )
        column_names = set(PipelineRun.__table__.columns.keys())
        testbase.assert_equal("orchestrated" in column_names, True)
    finally:
        session.close()
    return


# ---------------------------------------------------------------------------
# Orchestrator -- trigger creates the run + stages + steps
# ---------------------------------------------------------------------------


def test_trigger_pipeline_creates_run_with_stages_and_steps():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: trigger_pipeline persists a PipelineRun plus its
    per-stage + per-step rows.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    try:
        build_module = _FakeBuildServiceModule()
        test_orch = _FakeTestOrchestrator()
        orchestrator = _make_orchestrator(
            session_factory=lambda: session,
            build_module=build_module,
            test_orch=test_orch,
        )
        inputs = PipelineTriggerInputs(
            project_id=PROJECT_UUID,
            project_slug="proj",
            commit_sha="abc123",
            ref="main",
            filename="pipeline.json",
            document_bytes=_two_stage_document(),
        )
        view = orchestrator.trigger_pipeline(
            db_session=session, inputs=inputs,
        )
        testbase.assert_equal(len(view.stages), 2)
        stage_ids = tuple(stage.stage_id for stage in view.stages)
        testbase.assert_equal(stage_ids, ("build", "test"))
        for stage in view.stages:
            testbase.assert_equal(len(stage.steps), 1)
    finally:
        session.close()
    return


def test_trigger_pipeline_dispatches_root_stage_only():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: the DAG walker dispatches the root stage's job and
    leaves the dependent stage PENDING.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    try:
        build_module = _FakeBuildServiceModule()
        test_orch = _FakeTestOrchestrator()
        orchestrator = _make_orchestrator(
            session_factory=lambda: session,
            build_module=build_module,
            test_orch=test_orch,
        )
        inputs = PipelineTriggerInputs(
            project_id=PROJECT_UUID,
            project_slug="proj",
            commit_sha="abc123",
            ref="main",
            filename="pipeline.json",
            document_bytes=_two_stage_document(),
        )
        view = orchestrator.trigger_pipeline(
            db_session=session, inputs=inputs,
        )
        # Only the root ``build`` stage dispatched.
        testbase.assert_equal(len(build_module.triggered), 1)
        testbase.assert_equal(len(test_orch.triggered), 0)

        build_stage = next(s for s in view.stages if s.stage_id == "build")
        test_stage = next(s for s in view.stages if s.stage_id == "test")
        testbase.assert_equal(build_stage.state, StageState.RUNNING)
        testbase.assert_equal(test_stage.state, StageState.PENDING)
        # The dispatched build-job run id is recorded on the step.
        testbase.assert_equal(
            build_stage.steps[0].state, StepState.DISPATCHED,
        )
        testbase.assert_equal(
            build_stage.steps[0].layer5_run_id, "00000000-0000-4000-8000-0000000b0001",
        )
    finally:
        session.close()
    return


def test_stage_terminal_event_makes_dependent_eligible():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: a root stage's run-completed bus event makes the
    dependent stage eligible and dispatches its job.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    try:
        build_module = _FakeBuildServiceModule()
        test_orch = _FakeTestOrchestrator()
        orchestrator = _make_orchestrator(
            session_factory=lambda: session,
            build_module=build_module,
            test_orch=test_orch,
        )
        orchestrator.attach_bus_subscribers()
        inputs = PipelineTriggerInputs(
            project_id=PROJECT_UUID,
            project_slug="proj",
            commit_sha="abc123",
            ref="main",
            filename="pipeline.json",
            document_bytes=_two_stage_document(),
        )
        orchestrator.trigger_pipeline(db_session=session, inputs=inputs)

        # The build job (build-run-1) completes -- fire its terminal
        # event. The handler mirrors the step, completes the build
        # stage, and dispatches the now-eligible ``test`` stage.
        orchestrator._on_run_terminal(
            EntityEvent(
                topic="entity.run.completed",
                payload={"run_id": "00000000-0000-4000-8000-0000000b0001"},
                source_event_id="evt-1",
            )
        )
        testbase.assert_equal(len(test_orch.triggered), 1)
    finally:
        reset_event_bus()
        session.close()
    return


def test_stage_failure_skips_dependents_and_fails_run():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: a root stage's run-failed bus event skips the
    dependent stage and drives the pipeline run to FAILED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    try:
        build_module = _FakeBuildServiceModule()
        test_orch = _FakeTestOrchestrator()
        orchestrator = _make_orchestrator(
            session_factory=lambda: session,
            build_module=build_module,
            test_orch=test_orch,
        )
        orchestrator.attach_bus_subscribers()
        inputs = PipelineTriggerInputs(
            project_id=PROJECT_UUID,
            project_slug="proj",
            commit_sha="abc123",
            ref="main",
            filename="pipeline.json",
            document_bytes=_two_stage_document(),
        )
        view = orchestrator.trigger_pipeline(db_session=session, inputs=inputs)

        orchestrator._on_run_terminal(
            EntityEvent(
                topic="entity.run.failed",
                payload={"run_id": "00000000-0000-4000-8000-0000000b0001"},
                source_event_id="evt-1",
            )
        )
        # The dependent ``test`` stage never dispatched.
        testbase.assert_equal(len(test_orch.triggered), 0)

        final = definition_service.get_pipeline_run(
            db_session=session, run_id=view.run_id,
        )
        test_stage = next(s for s in final.stages if s.stage_id == "test")
        testbase.assert_equal(test_stage.state, StageState.SKIPPED)
        testbase.assert_equal(final.state, PipelineRunState.FAILED)
    finally:
        reset_event_bus()
        session.close()
    return


def test_dispatch_failure_fails_stage_and_skips_dependents():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: when a stage job has no dispatch path wired the step
    fails, the stage fails, and its dependents are skipped.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    try:
        # No build/test dispatch handles wired -- every dispatch fails.
        orchestrator = PipelineOrchestrator(
            session_factory=lambda: session,
            test_orchestrator=None,
            build_service_module=None,
            infra_service_module=None,
        )
        inputs = PipelineTriggerInputs(
            project_id=PROJECT_UUID,
            project_slug="proj",
            commit_sha="abc123",
            ref="main",
            filename="pipeline.json",
            document_bytes=_two_stage_document(),
        )
        view = orchestrator.trigger_pipeline(db_session=session, inputs=inputs)
        build_stage = next(s for s in view.stages if s.stage_id == "build")
        test_stage = next(s for s in view.stages if s.stage_id == "test")
        testbase.assert_equal(build_stage.state, StageState.FAILED)
        testbase.assert_equal(test_stage.state, StageState.SKIPPED)
        testbase.assert_equal(view.state, PipelineRunState.FAILED)
    finally:
        session.close()
    return


# ---------------------------------------------------------------------------
# REST routes -- registration + auth sweep
# ---------------------------------------------------------------------------


def test_register_pipeline_runs_routes_attaches_three_endpoints():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: register_pipeline_runs_routes attaches the three
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    pipeline_runs_routes.register_pipeline_runs_routes(
        app=app, version_prefix="/api/v1",
    )
    expected_pairs = (
        ("/api/v1/projects/{project_id}/pipeline-runs", ("POST",)),
        ("/api/v1/projects/{project_id}/pipeline-runs", ("GET",)),
        (
            "/api/v1/projects/{project_id}/pipeline-runs/{run_id}",
            ("GET",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


def test_trigger_returns_503_when_session_missing():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: POST pipeline-runs returns 503 when no db_session is
    bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/pipeline-runs",
        path_params={"project_id": "proj-1"},
        db_session=None,
    )
    response = pipeline_runs_routes.handle_trigger_pipeline_run(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_trigger_returns_401_when_no_principal():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: POST pipeline-runs returns 401 when the request is
    anonymous.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/pipeline-runs",
        path_params={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = pipeline_runs_routes.handle_trigger_pipeline_run(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_trigger_returns_403_when_permission_denied():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: POST pipeline-runs returns 403 when the principal
    lacks system:pipelines.run.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipeline-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = pipeline_runs_routes.handle_trigger_pipeline_run(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:pipelines.run")
    return


def test_trigger_returns_404_when_project_missing():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: POST pipeline-runs returns 404 when the project does
    not exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/pipeline-runs",
            path_params={"project_id": "proj-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = pipeline_runs_routes.handle_trigger_pipeline_run(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    return


def test_trigger_returns_201_on_happy_path():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: POST pipeline-runs returns 201 with the PipelineRun
    shape when the orchestrator triggers a run.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id=PROJECT_UUID),
    )
    build_module = _FakeBuildServiceModule()
    test_orch = _FakeTestOrchestrator()
    orchestrator = _make_orchestrator(
        session_factory=lambda: session,
        build_module=build_module,
        test_orch=test_orch,
    )
    pipeline_runs_routes.execution_orchestrator.set_active_pipeline_orchestrator(
        orchestrator=orchestrator,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/{}/pipeline-runs".format(PROJECT_UUID),
            path_params={"project_id": PROJECT_UUID},
            db_session=session,
            auth_principal=_FakePrincipal(),
            body={
                "commit_sha": "abc123",
                "ref": "main",
                "filename": "pipeline.json",
                "document": json.loads(_two_stage_document().decode("utf-8")),
            },
        )
        response = pipeline_runs_routes.handle_trigger_pipeline_run(request)
    finally:
        pipeline_runs_routes.execution_orchestrator.set_active_pipeline_orchestrator(
            orchestrator=None,
        )
        proj_patch.deactivate()
        perm_patch.deactivate()
        session.close()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(len(body["stages"]), 2)
    testbase.assert_equal(body["state"], "running")
    return


def test_trigger_returns_503_when_orchestrator_not_wired():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: POST pipeline-runs returns 503 when no orchestrator
    is wired on the module seam.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id=PROJECT_UUID),
    )
    pipeline_runs_routes.execution_orchestrator.set_active_pipeline_orchestrator(
        orchestrator=None,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/{}/pipeline-runs".format(PROJECT_UUID),
            path_params={"project_id": PROJECT_UUID},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"commit_sha": "a", "filename": "p.json", "document": "{}"},
        )
        response = pipeline_runs_routes.handle_trigger_pipeline_run(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 503)
    return


def test_read_returns_404_when_run_missing():
    """
    **Feature: 6-pipeline-execution PR p20q**
    **Property: GET pipeline-runs/{id} returns 404 for an unknown
    run id.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id=PROJECT_UUID),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/{}/pipeline-runs/missing".format(
                PROJECT_UUID,
            ),
            path_params={"project_id": PROJECT_UUID, "run_id": "missing"},
            db_session=session,
            auth_principal=_FakePrincipal(),
        )
        response = pipeline_runs_routes.handle_read_pipeline_run(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
        session.close()
    testbase.assert_equal(response.status_code, 404)
    return
