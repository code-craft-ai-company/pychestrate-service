"""
.. module:: orchestration.test.orchestrator
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: TestOrchestrator.trigger_run — the user-visible launcher.

.. moduleauthor:: Automation Mojo LLC

The orchestrator is where every Phase-3 sub-feature comes
together. ``trigger_run`` does:

1. Snapshot the catalog entry.
2. Resolve the registered :class:`TestRunnerKindProtocol`.
3. Validate inputs + render envelope params.
4. Allocate a result-tree prefix on the shared backend.
5. Create a ``runs_run`` row + flip to ``DISPATCHING`` via the
   run state machine.
6. Build the :class:`DispatchRequestInputs` and call
   :meth:`JobDispatcher.dispatch`.
7. Persist a :class:`TestRun` row tying the trigger to the
   resulting dispatch attempt.

The whole flow lives in one method so the integration test
exercises the entire Phase-3 chain in a single call.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import ConfigurationError, SemanticError

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.jobs.dispatch import (
    DispatchOutcome,
    DispatchRequestInputs,
    JobDispatcher,
)
from automojo.pychestrate.webservice.jobs.dispatch.errors import (
    DispatchError,
)
from automojo.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from automojo.pychestrate.webservice.jobs.envelope import (
    JobDeadline,
    JobForwardingInfo,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
)
from automojo.pychestrate.webservice.jobs.results import (
    SharedResultsBackend,
)
from automojo.pychestrate.webservice.jobs.run.state import (
    RunEvent,
    create_run as create_run_state,
    transition,
)
from automojo.pychestrate.webservice.orchestration.test import repository
from automojo.pychestrate.webservice.orchestration.test.catalog import (
    snapshot_for_dispatch,
)
from automojo.pychestrate.webservice.orchestration.test.catalog.payloads import (
    TestCatalogEntrySnapshot,
)
from automojo.pychestrate.webservice.orchestration.test.errors import (
    CapabilityMismatchError,
    DispatchFailedError,
    TestOrchestrationError,
)
from automojo.pychestrate.webservice.orchestration.test.factories.runner_protocol import (
    TestRunnerKindProtocol,
)
from automojo.pychestrate.webservice.orchestration.test.models import (
    TestRunState,
)


TEST_RUNNER_PROTOCOL: str = "test_runner_kind"


@dataclass(frozen=True)
class TriggerRunRequest:
    """
        Caller-supplied trigger payload.

        :param project_id: Owning project UUID.
        :param project_slug: Project slug (sanitized into the
                             results-backend prefix).
        :param catalog_entry_id: Target catalog entry UUID.
        :param triggered_by: Authenticated actor UUID.
        :param inputs: Runner-specific input dict (e.g.
                       ``{"includes": [...], "root": "..."}``).
        :param candidates: Eligible candidates the dispatcher
                           picks from. M1 takes them directly; M2
                           wires the registry-driven filter.
        :param issuer: Service DNS-name + release string.
        :param soft_deadline_seconds / hard_deadline_seconds:
                           run deadlines (relative to trigger).
        :param results_backend: Optional override for the shared
                           backend; defaults to a local-test
                           backend when ``None``.
    """
    project_id: str
    project_slug: str
    catalog_entry_id: str
    triggered_by: Optional[str]
    inputs: Mapping[str, Any]
    candidates: Sequence[DispatchCandidate]
    issuer: str = "pychestrate.example.com/0.6.0"
    soft_deadline_seconds: int = 1800
    hard_deadline_seconds: int = 3600
    results_backend: Optional[SharedResultsBackend] = None


@dataclass(frozen=True)
class TriggerRunOutcome:
    """
        Returned to the caller after a successful trigger.
    """
    run_id: str
    test_run_state: TestRunState
    dispatch: DispatchOutcome
    catalog_entry_id: str
    catalog_digest: str


class TestOrchestrator:
    """
        Facade for the test-orchestration trigger flow.
    """

    def __init__(
            self,
            *,
            dispatcher: JobDispatcher,
            results_backend: Optional[SharedResultsBackend] = None
        ) -> None:
        self._dispatcher: JobDispatcher = dispatcher
        if results_backend is None:
            self._default_backend: SharedResultsBackend = SharedResultsBackend(
                backend_driver="local-test",
            )
        else:
            self._default_backend = results_backend
        return

    def trigger_run(
            self,
            *,
            db_session: DbSession,
            request: TriggerRunRequest
        ) -> TriggerRunOutcome:
        """
            Run the full Phase-3 trigger chain.

            :param db_session: Active SQLAlchemy session.
            :param request: Caller-supplied trigger payload.

            :returns: :class:`TriggerRunOutcome`.
            :raises: TestOrchestrationError, CapabilityMismatchError,
                     DispatchFailedError, SemanticError.
        """
        snapshot = snapshot_for_dispatch(
            db_session=db_session,
            entry_id=request.catalog_entry_id,
        )

        runner = self._resolve_runner(runner_kind=snapshot.runner_kind)
        params = runner.build_envelope_params(
            snapshot=snapshot,
            inputs=request.inputs,
        )

        eligible = self._filter_capability_matches(
            candidates=request.candidates,
            required_tags=snapshot.required_capability_tags,
        )
        if len(eligible) == 0:
            err_lines = ["No candidate pod satisfies the catalog entry's required capabilities."]
            err_lines.append("ENTRY_ID: {}".format(snapshot.entry_id))
            err_lines.append("REQUIRED: {}".format(list(snapshot.required_capability_tags)))
            err_lines.append("CANDIDATES_INSPECTED: {}".format(len(request.candidates)))
            err_msg = os.linesep.join(err_lines)
            raise CapabilityMismatchError(err_msg) from None

        run_id = new_uuid()
        backend = request.results_backend or self._default_backend
        allocation = backend.allocate(
            db_session=db_session,
            run_id=run_id,
            project_id=request.project_id,
            project_slug=request.project_slug,
            job_type=snapshot.runner_kind,
        )

        triggered_at = utc_now()
        repository.insert_run(
            db_session=db_session,
            run_id=run_id,
            project_id=request.project_id,
            catalog_entry_id=snapshot.entry_id,
            runner_kind=snapshot.runner_kind,
            triggered_by=request.triggered_by,
            triggered_at=triggered_at,
            inputs_json=dict(request.inputs),
        )
        db_session.commit()

        # Run-state-machine: create + advance to DISPATCHING. Done
        # before the dispatcher's own commit so the audit trail
        # reflects the trigger phase distinctly.
        create_run_state(
            db_session=db_session,
            run_id=run_id,
            project_id=request.project_id,
            job_type=snapshot.runner_kind,
        )
        transition(
            db_session=db_session,
            run_id=run_id,
            event=RunEvent.DISPATCH_STARTED,
            actor="system:test-orchestrator",
            reason="catalog_entry={}".format(snapshot.entry_id),
        )

        dispatch_inputs = self._build_dispatch_inputs(
            run_id=run_id,
            request=request,
            snapshot=snapshot,
            params=params,
            allocation=allocation,
            eligible=eligible,
            triggered_at=triggered_at,
        )

        try:
            dispatch_outcome = self._dispatcher.dispatch(
                db_session=db_session,
                inputs=dispatch_inputs,
            )
        except DispatchError as xcpt:
            # Persist the dispatch failure on the orchestration row.
            test_run = repository.get_run(db_session=db_session, run_id=run_id)
            if test_run is not None:
                repository.update_state(
                    db_session=db_session,
                    run=test_run,
                    new_state=TestRunState.DISPATCH_FAILED,
                    failure_reason=str(xcpt),
                    finished_at=utc_now(),
                )
                db_session.commit()
            err_lines = ["TestOrchestrator dispatch failed."]
            err_lines.append("RUN_ID: {}".format(run_id))
            err_lines.append("REASON: {}".format(str(xcpt)))
            err_msg = os.linesep.join(err_lines)
            raise DispatchFailedError(err_msg) from xcpt

        # Happy path: orchestration row flips to DISPATCHED.
        test_run = repository.get_run(db_session=db_session, run_id=run_id)
        repository.update_state(
            db_session=db_session,
            run=test_run,
            new_state=TestRunState.DISPATCHED,
            dispatch_attempt_id=dispatch_outcome.attempt_id,
        )
        db_session.commit()

        rtnval = TriggerRunOutcome(
            run_id=run_id,
            test_run_state=TestRunState.DISPATCHED,
            dispatch=dispatch_outcome,
            catalog_entry_id=snapshot.entry_id,
            catalog_digest=snapshot.canonical_digest,
        )
        return rtnval

    def _resolve_runner(self, *, runner_kind: str):
        """
            Find the registered :class:`TestRunnerKindProtocol`
            whose ``runner_kind`` matches the snapshot.
        """
        candidates = list_factory_implementations(
            factory_protocol_name=TEST_RUNNER_PROTOCOL,
        )
        for impl in candidates:
            try:
                if impl.runner_kind() == runner_kind:
                    return impl
            except NotImplementedError:
                continue
        err_lines = ["No test_runner_kind registered for catalog entry's runner."]
        err_lines.append("RUNNER_KIND: {}".format(runner_kind))
        err_lines.append("REGISTERED: ({})".format(len(candidates)))
        err_msg = os.linesep.join(err_lines)
        raise TestOrchestrationError(err_msg) from None

    def _filter_capability_matches(
            self,
            *,
            candidates: Sequence[DispatchCandidate],
            required_tags: Tuple[str, ...]
        ):
        """
            Return only candidates whose ``capability_tags``
            superset includes every required tag. M1 keeps the
            check inline; M2 swaps in the live registry view.
        """
        if required_tags is None or len(required_tags) == 0:
            return list(candidates)
        eligible = []
        for cand in candidates:
            cand_tags = set(cand.capability_tags or ())
            if all(tag in cand_tags for tag in required_tags):
                eligible.append(cand)
        return eligible

    def _build_dispatch_inputs(
            self,
            *,
            run_id: str,
            request: TriggerRunRequest,
            snapshot: TestCatalogEntrySnapshot,
            params: Mapping[str, Any],
            allocation,
            eligible,
            triggered_at: datetime
        ) -> DispatchRequestInputs:
        """
            Assemble the :class:`DispatchRequestInputs` from the
            trigger request + snapshot + allocated results.
        """
        soft_deadline = triggered_at + timedelta(seconds=request.soft_deadline_seconds)
        hard_deadline = triggered_at + timedelta(seconds=request.hard_deadline_seconds)
        rtnval = DispatchRequestInputs(
            run_id=run_id,
            project_id=request.project_id,
            job_id=snapshot.entry_id,
            job_name=snapshot.raw_metadata.get("display_name", snapshot.entry_id) or snapshot.entry_id,
            job_type=snapshot.runner_kind,
            issuer=request.issuer,
            refs=JobRefs(
                branch=str(snapshot.raw_metadata.get("branch", "main")),
                build=str(snapshot.raw_metadata.get("build", "")),
                flavor=str(snapshot.raw_metadata.get("flavor", "")),
                release=str(snapshot.raw_metadata.get("release", "")),
                commit_sha=str(snapshot.raw_metadata.get("commit_sha", "0" * 40)),
            ),
            params=dict(params),
            scoped_secrets=tuple(),
            results=JobResultsLocator(
                backend_key_prefix=allocation.backend_key_prefix,
                backend_driver=allocation.backend_driver,
            ),
            forwarding=JobForwardingInfo(
                progress_url="https://pychestrate.example.com/api/v1/runs/{}/progress".format(run_id),
                summary_url="https://pychestrate.example.com/api/v1/runs/{}/summary".format(run_id),
                auth_method="bearer",
            ),
            deadline=JobDeadline(
                soft_deadline_at=soft_deadline,
                hard_deadline_at=hard_deadline,
            ),
            pipeline=JobPipelineRef(
                pipeline_id=str(snapshot.raw_metadata.get("pipeline_id", "ad-hoc")),
                instance_id=run_id,
            ),
            extension_claims={},
            candidates=tuple(eligible),
        )
        return rtnval
