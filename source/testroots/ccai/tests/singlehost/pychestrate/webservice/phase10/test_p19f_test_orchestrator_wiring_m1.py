"""
.. module:: test_p19f_test_orchestrator_wiring_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Smoke tests for the Phase-6 TestOrchestrator bootstrap
               wiring delivered by PR p19f.

.. moduleauthor:: Code Craft AI LLC

PR p19d introduced the ``ACTIVE_TEST_ORCHESTRATOR`` module-level
seam on ``test_runs_routes`` and answered 503 when it was unset.
PR p19f populates that seam during ``bootstrap_phase6_runtime`` so
``POST /api/v1/projects/{project_id}/test-runs`` no longer returns
the 503 "Test orchestrator not configured" problem.

The smoke tests exercise the wiring surface only:

* :func:`bootstrap_phase6_runtime` constructs a
  :class:`TestOrchestrator` and publishes it on
  ``test_runs_routes.ACTIVE_TEST_ORCHESTRATOR``.
* When ``config.session_factory is None`` the bootstrap stays in
  register-only mode and does not touch the seam.
* A ``POST /test-runs`` request handled by ``handle_trigger_test_run``
  reaches the live orchestrator's ``trigger_run`` method (the
  test substitutes a recording orchestrator after the bootstrap so
  the in-memory dispatcher is not actually invoked).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.extensions.phase6_bootstrap import (
    Phase6BootstrapConfig,
    bootstrap_phase6_runtime,
)
from ccai.pychestrate.webservice.jobs.dispatch import JobDispatcher
from ccai.pychestrate.webservice.orchestration.test.orchestrator import (
    TestOrchestrator,
)
from ccai.pychestrate.webservice.orchestration.test.restapi.v1 import (
    test_runs_routes,
)
from ccai.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_in_memory_session_factory():
    """
        Build an in-memory sqlite engine + session factory so the
        Phase-6 bootstrap has something concrete to wire against.

        :returns: ``sessionmaker``-backed callable.
    """
    engine = create_engine("sqlite:///:memory:")
    PychestratePhase1Base.metadata.create_all(engine)
    rtnval = sessionmaker(bind=engine, expire_on_commit=False)
    return rtnval


def _snapshot_active_orchestrator() -> Any:
    """
        Capture the current :data:`ACTIVE_TEST_ORCHESTRATOR` so the
        test can restore the prior value in its ``finally`` block.

        :returns: Whatever was on the seam.
    """
    rtnval = test_runs_routes.ACTIVE_TEST_ORCHESTRATOR
    return rtnval


def _restore_active_orchestrator(*, prior: Any) -> None:
    """
        Put the prior :data:`ACTIVE_TEST_ORCHESTRATOR` back so
        cross-test pollution can't accumulate.

        :param prior: Prior seam value.

        :returns: None.
    """
    test_runs_routes.ACTIVE_TEST_ORCHESTRATOR = prior
    return


# ---------------------------------------------------------------------------
# Bootstrap smoke
# ---------------------------------------------------------------------------


def test_bootstrap_phase6_runtime_populates_active_test_orchestrator_seam():
    """
    **Feature: phase-6 wiring p19f**
    **Property: bootstrap_phase6_runtime constructs a TestOrchestrator
    and publishes it on ``test_runs_routes.ACTIVE_TEST_ORCHESTRATOR``.
    Without this, the trigger-run REST endpoint short-circuits to 503
    on every request.**
    """
    prior = _snapshot_active_orchestrator()
    test_runs_routes.ACTIVE_TEST_ORCHESTRATOR = None
    factory = _build_in_memory_session_factory()
    try:
        config = Phase6BootstrapConfig(session_factory=factory)
        result = bootstrap_phase6_runtime(config=config)

        testbase.assert_equal(result.orchestrator is not None, True)
        testbase.assert_equal(
            isinstance(result.orchestrator, TestOrchestrator), True,
        )
        testbase.assert_equal(
            isinstance(result.dispatcher, JobDispatcher), True,
        )
        testbase.assert_equal(result.transport is not None, True)

        active = test_runs_routes.ACTIVE_TEST_ORCHESTRATOR
        testbase.assert_equal(active is result.orchestrator, True)
    finally:
        _restore_active_orchestrator(prior=prior)
    return


def test_bootstrap_phase6_runtime_register_only_when_no_session_factory():
    """
    **Feature: phase-6 wiring p19f**
    **Property: When config.session_factory is None, the bootstrap
    runs the extension-registration path only -- the orchestrator is
    not constructed and the route seam is left alone. This matches
    the register-only callsite used by app_pychestrate_main's
    register_service_extensions on every webworks startup.**
    """
    prior = _snapshot_active_orchestrator()
    sentinel: Any = object()
    test_runs_routes.ACTIVE_TEST_ORCHESTRATOR = sentinel
    try:
        config = Phase6BootstrapConfig(session_factory=None)
        result = bootstrap_phase6_runtime(config=config)

        testbase.assert_equal(result.orchestrator is None, True)
        testbase.assert_equal(result.dispatcher is None, True)
        testbase.assert_equal(result.transport is None, True)

        # Seam was NOT overwritten -- register-only path is inert
        # against the request layer.
        testbase.assert_equal(
            test_runs_routes.ACTIVE_TEST_ORCHESTRATOR is sentinel, True,
        )
    finally:
        _restore_active_orchestrator(prior=prior)
    return


# ---------------------------------------------------------------------------
# End-to-end: route handler reaches the live orchestrator after bootstrap
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
            path_params: Dict[str, Any],
            body: Any,
            db_session: Any,
            auth_principal: Any
        ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params
        self.query_params: _FakeQueryParams = _FakeQueryParams()
        self._body: Any = body
        self.db_session: Any = db_session
        self.auth_principal: Any = auth_principal
        return

    def json(self) -> Any:
        rtnval = self._body
        return rtnval


class _FakePrincipal:
    def __init__(self, *, user_id: str = "user-1") -> None:
        self.user_id: str = user_id
        return


class _FakeDecision:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed: bool = allowed
        self.reason: str = ""
        return


class _FakeProject:
    def __init__(self, *, project_id: str) -> None:
        self.project_id: str = project_id
        self.slug: str = "proj-slug"
        return


class _FakeCatalogEntry:
    def __init__(self, *, entry_id: str, project_id: str) -> None:
        self.entry_id: str = entry_id
        self.project_id: str = project_id
        self.importer_tag: str = "testbase-project"
        self.entry_key: str = "tests.thing.test_x"
        self.display_name: str = "Thing X"
        self.raw_metadata: Dict[str, Any] = {"runner_kind": "testbase"}
        return


class _FakePodDefinition:
    def __init__(self, *, pod_id: str, project_id: str) -> None:
        self.pod_id: str = pod_id
        self.project_id: str = project_id
        return


class _FakePodRegistration:
    def __init__(self, *, pod_id: str, client_id: str) -> None:
        from ccai.pychestrate.webservice.pods.models import (
            RegistrationState,
        )
        self.pod_id: str = pod_id
        self.client_id: str = client_id
        self.state: RegistrationState = RegistrationState.REGISTERED
        return


class _FakeQuery:
    def __init__(self, *, rows: List[Any]) -> None:
        self._rows: List[Any] = rows
        return

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        rtnval = self
        return rtnval

    def first(self) -> Optional[Any]:
        if len(self._rows) == 0:
            return None
        rtnval = self._rows[0]
        return rtnval

    def all(self) -> List[Any]:
        rtnval = list(self._rows)
        return rtnval


class _FakeSession:
    def __init__(
            self,
            *,
            pods: List[Any],
            registrations: List[Any]
        ) -> None:
        from ccai.pychestrate.webservice.pods.models import (
            PodDefinition,
            PodRegistration,
        )
        self._pods: List[Any] = pods
        self._registrations: List[Any] = registrations
        self._PodDefinition = PodDefinition
        self._PodRegistration = PodRegistration
        return

    def query(self, model: Any) -> _FakeQuery:
        if model is self._PodDefinition:
            rtnval = _FakeQuery(rows=self._pods)
        elif model is self._PodRegistration:
            rtnval = _FakeQuery(rows=self._registrations)
        else:
            rtnval = _FakeQuery(rows=[])
        return rtnval


class _RecordingOrchestrator:
    """
        Records ``trigger_run`` calls so the test can prove the
        route handler actually reached the orchestrator's seam.
    """

    def __init__(self) -> None:
        self.calls: List[Any] = []
        return

    def trigger_run(self, *, db_session: Any, request: Any) -> Any:
        self.calls.append(request)
        # Raise a known non-503 exception so the route emits a 409
        # problem -- proves the seam was bound and the handler did
        # NOT short-circuit on the 503 "not configured" path.
        from ccai.pychestrate.webservice.orchestration.test.errors import (
            TestOrchestrationError,
        )
        raise TestOrchestrationError("recording stub -- seam was reached")


def test_handle_trigger_test_run_reaches_orchestrator_after_bootstrap():
    """
    **Feature: phase-6 wiring p19f**
    **Property: After bootstrap_phase6_runtime runs, a POST
    /test-runs request through ``handle_trigger_test_run`` actually
    invokes the orchestrator's ``trigger_run`` method rather than
    short-circuiting on the 503 "Test orchestrator not configured"
    path. The bootstrap publishes a real TestOrchestrator on the
    seam; the test substitutes a recording stub after the bootstrap
    to keep the assertion focused on wire-up (not orchestrator
    domain logic).**
    """
    prior = _snapshot_active_orchestrator()
    factory = _build_in_memory_session_factory()
    perm_patch: Any = None
    proj_patch: Any = None
    cat_patch: Any = None
    try:
        # 1) Bootstrap publishes a real orchestrator on the seam.
        config = Phase6BootstrapConfig(session_factory=factory)
        result = bootstrap_phase6_runtime(config=config)
        testbase.assert_equal(
            test_runs_routes.ACTIVE_TEST_ORCHESTRATOR is result.orchestrator,
            True,
        )

        # 2) Swap in a recording orchestrator so we can prove the
        # route handler reached it (and avoid running the real
        # dispatcher path which needs catalog rows + factories).
        recording = _RecordingOrchestrator()
        test_runs_routes.set_active_test_orchestrator(orchestrator=recording)

        # 3) Patch the rbac / project / catalog lookups so the
        # handler reaches the orchestrator step.
        project_id = "00000000-0000-0000-0000-000000000001"
        pod_id = "00000000-0000-0000-0000-000000000002"
        entry_id = "00000000-0000-0000-0000-000000000003"
        client_id = "00000000-0000-0000-0000-000000000004"

        perm_patch = create_module_patch(
            test_runs_routes.rbac_evaluator, "check_permission",
        )
        perm_patch.activate().configure(
            side_effect=lambda **kwargs: _FakeDecision(allowed=True),
        )

        proj_patch = create_module_patch(
            test_runs_routes.projects_repo, "get_project_by_id",
        )
        proj_patch.activate().configure(
            side_effect=lambda **kwargs: _FakeProject(project_id=project_id),
        )

        cat_patch = create_module_patch(
            test_runs_routes.catalog_repo, "find_by_id",
        )
        cat_patch.activate().configure(
            side_effect=lambda **kwargs: _FakeCatalogEntry(
                entry_id=entry_id, project_id=project_id,
            ),
        )

        session = _FakeSession(
            pods=[_FakePodDefinition(pod_id=pod_id, project_id=project_id)],
            registrations=[
                _FakePodRegistration(pod_id=pod_id, client_id=client_id),
            ],
        )
        request = _FakeRequest(
            path="/api/v1/projects/{}/test-runs".format(project_id),
            path_params={"project_id": project_id},
            body={"pod_id": pod_id, "catalog_entry_id": entry_id},
            db_session=session,
            auth_principal=_FakePrincipal(),
        )

        response = test_runs_routes.handle_trigger_test_run(request)

        # The recording stub raises TestOrchestrationError -> 409.
        # The critical assertion is: not 503, the seam was reached.
        testbase.assert_equal(response.status_code, 409)
        testbase.assert_equal(len(recording.calls) >= 1, True)
        triggered = recording.calls[0]
        testbase.assert_equal(triggered.project_id, project_id)
        testbase.assert_equal(triggered.catalog_entry_id, entry_id)

        body = json.loads(response.body.decode("utf-8"))
        # Sanity: this should NOT be the "Test orchestrator not
        # configured" 503 detail.
        testbase.assert_equal("not configured" in body.get("detail", ""), False)
    finally:
        if perm_patch is not None:
            perm_patch.deactivate()
        if proj_patch is not None:
            proj_patch.deactivate()
        if cat_patch is not None:
            cat_patch.deactivate()
        _restore_active_orchestrator(prior=prior)
    return
