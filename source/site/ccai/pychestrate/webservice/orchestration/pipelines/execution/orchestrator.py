"""
.. module:: orchestration.pipelines.execution.orchestrator
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: PipelineOrchestrator -- the DAG-walking stage-job coordinator.

.. moduleauthor:: Code Craft AI LLC

A pipeline definition is a DAG of stages; each stage references one
or more steps, and each step translates (via its registered
``pipeline_step_kind``) into a build / test / provision job. Running
a pipeline means walking that DAG in topological order: a stage
becomes *eligible* when every stage it ``needs`` has completed
successfully, and an eligible stage's steps dispatch through the
EXISTING build / test / provision dispatch paths.

The orchestrator is a straightforward in-process coordinator -- not
a distributed scheduler. It:

1. Reuses :func:`definition.service.trigger_run` to parse + DAG-check
   the document and persist a :class:`PipelineRun` + per-stage +
   per-step rows in ``PENDING``.
2. Dispatches the root stages (no ``needs``) immediately.
3. Subscribes to the run-state machine's terminal bus topics
   (``entity.run.completed`` / ``.failed`` / ``.cancelled``). When a
   dispatched stage-job run reaches a terminal state, the orchestrator
   mirrors the step outcome onto the :class:`PipelineStepRun`, then
   re-evaluates the DAG: newly-eligible stages dispatch, and the
   dependents of a failed stage are skipped.

Stage-job dispatch is NOT re-implemented here. ``build`` steps go
through :func:`build.service.trigger_run`; ``test`` steps go through
:meth:`TestOrchestrator.trigger_run`; ``infra`` / ``provision`` steps
go through :func:`infra.runs.service.trigger_run`.

A step is never reported successful for work that did not happen
(audit ORG-F15):

* ``script`` steps have no execution path -- no pod executor runs
  them -- so they resolve immediately as ``FAILED`` with
  :data:`SCRIPT_STEP_NOT_EXECUTED_REASON`, which fails their stage
  and the run instead of letting it go green.
* ``build`` steps build the commit the pipeline was triggered at:
  the run's ``commit_sha`` (and branch, from ``ref``) are passed to
  the build unless the step pins its own.
* A trigger that asks for matrix dimensions is refused
  (:class:`PipelineMatrixUnsupportedError`): a run executes each
  stage once, so it could not honour the matrix.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    subscribe,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    repository as definition_repository,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    service as definition_service,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition.models import (
    PipelineRunState,
    StageState,
    StepState,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition.service import (
    PipelineRunView,
    TriggerAspects,
)
from ccai.pychestrate.webservice.orchestration.pipelines.execution.errors import (
    PipelineMatrixUnsupportedError,
    PipelineRunConflictError,
)


_LOGGER = logging.getLogger("pychestrate.pipelines.orchestrator")


SessionFactory = Callable[[], DbSession]


# Run-state machine terminal bus topics. The orchestrator subscribes
# to all three so a dispatched stage job reaching any terminal state
# re-drives the DAG walk.
RUN_TERMINAL_TOPICS: Tuple[str, ...] = (
    "entity.run.completed",
    "entity.run.failed",
    "entity.run.cancelled",
)


# Pipeline step ``job_kind`` values that have a Layer-5 dispatch path.
JOB_KIND_BUILD: str = "build"
JOB_KIND_TEST: str = "test"
JOB_KIND_INFRA: str = "infra"
JOB_KIND_PROVISION: str = "provision"
JOB_KIND_RPA: str = "rpa"
JOB_KIND_SCRIPT: str = "script"


#: Recorded on a ``script`` step, which is marked FAILED because nothing
#: can run it: pods execute build, test, provision and rpa jobs only.
SCRIPT_STEP_NOT_EXECUTED_REASON: str = (
    "not executed: script steps have no execution path in this release"
    " (pods run build, test, provision and rpa jobs only)"
)

#: Prefix stripped from a git ref to obtain the branch name handed to
#: build steps.
GIT_BRANCH_REF_PREFIX: str = "refs/heads/"


@dataclass(frozen=True)
class SourceRevision:
    """
        The revision a pipeline run was triggered at, handed to the
        steps that build source.

        :param commit_sha: The run's commit.
        :param ref: The run's git ref (branch / tag), possibly empty.
    """
    commit_sha: str
    ref: str


@dataclass(frozen=True)
class PipelineTriggerInputs:
    """
        Caller-supplied inputs for :meth:`PipelineOrchestrator.trigger_pipeline`.

        :param project_id: Owning project UUID.
        :param project_slug: Project slug (sanitized into the
                             results-backend prefix used by the
                             reused build / test / provision dispatch).
        :param commit_sha: Commit the pipeline document was read at.
        :param ref: Git ref (branch / tag) the run targets.
        :param filename: Pipeline-document filename (selects parser).
        :param document_bytes: Raw pipeline-document bytes.
        :param actor_id: Optional UUID of the triggering actor.
        :param candidates: Eligible dispatch candidates the reused
                           build / test / provision dispatch picks the
                           target client/pod from. An empty tuple means
                           "no eligible pod" -- the affected stage job
                           fails and its dependents are skipped.
        :param matrix_params: Optional matrix-expansion dimensions.
                              Must be empty: a run executes each
                              stage exactly once, so
                              :meth:`PipelineOrchestrator.trigger_pipeline`
                              refuses a non-empty matrix rather than
                              ignore it.
    """
    project_id: str
    project_slug: str
    commit_sha: str
    ref: str
    filename: str
    document_bytes: bytes
    actor_id: Optional[str] = None
    candidates: Tuple[DispatchCandidate, ...] = ()
    matrix_params: Mapping[str, Any] = field(default_factory=dict)


class PipelineOrchestrator:
    """
        In-process DAG-walking coordinator for pipeline runs.

        The orchestrator holds the build / test / provision dispatch
        handles the rest of Layer 6 already uses. It does not own a
        thread or a queue -- the DAG walk is driven synchronously by
        :meth:`trigger_pipeline` (root stages) and by the run-terminal
        bus events its subscriber handles.
    """

    def __init__(
            self,
            *,
            session_factory: SessionFactory,
            test_orchestrator: Optional[Any] = None,
            build_service_module: Optional[Any] = None,
            infra_service_module: Optional[Any] = None,
            rpa_service_module: Optional[Any] = None
        ) -> None:
        """
            :param session_factory: Factory yielding a fresh
                                    SQLAlchemy session. The bus
                                    subscriber needs its own session
                                    because bus events fire outside a
                                    request scope.
            :param test_orchestrator: The live :class:`TestOrchestrator`
                                      whose ``trigger_run`` dispatches
                                      ``test`` stage jobs.
            :param build_service_module: The ``build.service`` module
                                         whose ``trigger_run`` dispatches
                                         ``build`` stage jobs.
            :param infra_service_module: The ``infra.runs.service``
                                         module whose ``trigger_run``
                                         dispatches ``infra`` /
                                         ``provision`` stage jobs.
        """
        self._session_factory: SessionFactory = session_factory
        self._test_orchestrator: Optional[Any] = test_orchestrator
        self._build_service: Optional[Any] = build_service_module
        self._infra_service: Optional[Any] = infra_service_module
        self._rpa_service: Optional[Any] = rpa_service_module
        self._subscribed: bool = False
        return

    def attach_bus_subscribers(self) -> None:
        """
            Subscribe the DAG-walk re-evaluation handler to the
            run-state machine's terminal bus topics. Idempotent: a
            second call is a no-op so re-running the bootstrap does
            not double-subscribe.

            :returns: None.
        """
        if self._subscribed is True:
            return
        for topic in RUN_TERMINAL_TOPICS:
            subscribe(topic=topic, subscriber=self._on_run_terminal)
        self._subscribed = True
        _LOGGER.info(
            "pychestrate.pipelines.orchestrator.bus_subscribers_attached"
            " topics=%s",
            ",".join(RUN_TERMINAL_TOPICS),
        )
        return

    def trigger_pipeline(
            self,
            *,
            db_session: DbSession,
            inputs: PipelineTriggerInputs
        ) -> PipelineRunView:
        """
            Trigger a pipeline run.

            Parses + DAG-checks the document, persists a
            :class:`PipelineRun` + per-stage + per-step rows in
            ``PENDING`` (via the reused
            :func:`definition.service.trigger_run`), then dispatches
            every root stage (a stage with no ``needs``).

            :param db_session: Active request-scoped session.
            :param inputs: Caller-supplied :class:`PipelineTriggerInputs`.

            :returns: The :class:`PipelineRunView` after the root
                      stages have been dispatched.
            :raises: PipelineDocumentInvalidError, PipelineDagCycleError,
                     PipelineStepKindUnknownError, PipelineRunConflictError,
                     PipelineMatrixUnsupportedError.
        """
        if inputs.matrix_params is not None and len(inputs.matrix_params) > 0:
            err_lines = ["Matrix execution is not supported: a pipeline run executes each stage once."]
            err_lines.append(
                "Trigger without 'matrix'; preview shards with"
                " POST /api/v1/projects/{project_id}/pipelines:expand-matrix."
            )
            err_lines.append("DIMENSIONS: {}".format(
                ", ".join(sorted(str(key) for key in inputs.matrix_params.keys())),
            ))
            err_msg = os.linesep.join(err_lines)
            raise PipelineMatrixUnsupportedError(err_msg) from None

        run_view = definition_service.trigger_run(
            db_session=db_session,
            project_id=inputs.project_id,
            commit_sha=inputs.commit_sha,
            ref=inputs.ref,
            filename=inputs.filename,
            document_bytes=inputs.document_bytes,
            aspects=TriggerAspects(actor_id=inputs.actor_id),
        )

        # Stamp the run as orchestrator-driven so reads can tell a
        # DAG-walked run apart from an M1 definition-only trigger.
        run_row = definition_repository.find_run_by_id(
            db_session=db_session, run_id=run_view.run_id,
        )
        if run_row is not None:
            run_row.orchestrated = True
            db_session.flush()

        # The reused trigger_run leaves the PipelineRun at RUNNING with
        # every stage + step PENDING. Walk the DAG once now to dispatch
        # the root stages.
        self._dispatch_eligible_stages(
            db_session=db_session,
            run_id=run_view.run_id,
            project_id=inputs.project_id,
            project_slug=inputs.project_slug,
            candidates=inputs.candidates,
            actor_id=inputs.actor_id,
        )
        db_session.commit()

        rtnval = definition_service.get_pipeline_run(
            db_session=db_session, run_id=run_view.run_id,
        )
        return rtnval

    # -----------------------------------------------------------------
    # DAG walk
    # -----------------------------------------------------------------

    def _dispatch_eligible_stages(
            self,
            *,
            db_session: DbSession,
            run_id: str,
            project_id: str,
            project_slug: str,
            candidates: Tuple[DispatchCandidate, ...],
            actor_id: Optional[str]
        ) -> None:
        """
            Evaluate every PENDING stage of the run. A stage is
            *eligible* when each stage it ``needs`` has reached
            ``COMPLETED``; it is *blocked* (skipped) when any stage it
            ``needs`` reached ``FAILED`` / ``SKIPPED`` / ``CANCELLED``.

            Eligible stages dispatch their steps; blocked stages flip
            to ``SKIPPED`` (cascading their own dependents).

            :returns: None.
        """
        revision = self._source_revision_for_run(
            db_session=db_session, run_id=run_id,
        )
        stage_rows = definition_repository.list_stages_for_run(
            db_session=db_session, run_id=run_id,
        )
        state_by_id: Dict[str, StageState] = {}
        needs_by_id: Dict[str, Tuple[str, ...]] = {}
        for stage in stage_rows:
            state_by_id[stage.stage_id] = stage.state
            needs_by_id[stage.stage_id] = self._parse_needs(
                needs_csv=stage.needs_csv,
            )

        # Iterate until no PENDING stage changes -- a skip can unblock
        # the next round of skips. Bounded by the stage count.
        changed = True
        rounds = 0
        max_rounds = len(stage_rows) + 1
        while changed is True and rounds <= max_rounds:
            changed = False
            rounds = rounds + 1
            for stage in stage_rows:
                if state_by_id[stage.stage_id] != StageState.PENDING:
                    continue
                disposition = self._stage_disposition(
                    needs=needs_by_id[stage.stage_id],
                    state_by_id=state_by_id,
                )
                if disposition == "eligible":
                    self._dispatch_stage(
                        db_session=db_session,
                        stage_row=stage,
                        project_id=project_id,
                        project_slug=project_slug,
                        candidates=candidates,
                        actor_id=actor_id,
                        revision=revision,
                    )
                    # Re-read the post-dispatch state -- a fully
                    # synchronous (script-only or dispatch-failed)
                    # stage resolves immediately.
                    refreshed = definition_repository.find_stage_run_by_id(
                        db_session=db_session,
                        stage_run_id=str(stage.stage_run_id),
                    )
                    if refreshed is not None:
                        state_by_id[stage.stage_id] = refreshed.state
                    changed = True
                elif disposition == "blocked":
                    self._skip_stage(
                        db_session=db_session,
                        stage_run_id=str(stage.stage_run_id),
                        reason="dependency_failed",
                    )
                    state_by_id[stage.stage_id] = StageState.SKIPPED
                    changed = True
                # "waiting": dependencies still PENDING/RUNNING -- leave.

        self._maybe_finalize_pipeline(db_session=db_session, run_id=run_id)
        return

    def _stage_disposition(
            self,
            *,
            needs: Tuple[str, ...],
            state_by_id: Dict[str, StageState]
        ) -> str:
        """
            Classify a PENDING stage against its dependency states.

            :returns: ``"eligible"`` when every dependency COMPLETED,
                      ``"blocked"`` when any dependency FAILED /
                      SKIPPED / CANCELLED, ``"waiting"`` otherwise.
        """
        blocking = (
            StageState.FAILED, StageState.SKIPPED, StageState.CANCELLED,
        )
        has_blocking = False
        all_complete = True
        for need in needs:
            dep_state = state_by_id.get(need, None)
            if dep_state in blocking:
                has_blocking = True
            if dep_state != StageState.COMPLETED:
                all_complete = False
        if has_blocking is True:
            rtnval = "blocked"
            return rtnval
        if all_complete is True:
            rtnval = "eligible"
            return rtnval
        rtnval = "waiting"
        return rtnval

    def _dispatch_stage(
            self,
            *,
            db_session: DbSession,
            stage_row: Any,
            project_id: str,
            project_slug: str,
            candidates: Tuple[DispatchCandidate, ...],
            actor_id: Optional[str],
            revision: SourceRevision
        ) -> None:
        """
            Mark a stage ``RUNNING`` and dispatch each of its steps
            through the reused build / test / provision dispatch.

            :param revision: The run's commit + ref, for build steps.

            :returns: None.
        """
        from ccai.pychestrate.core.defaults import utc_now

        stage_row.state = StageState.RUNNING
        stage_row.started_at = utc_now()
        db_session.flush()

        step_rows = definition_repository.list_steps_for_stage(
            db_session=db_session,
            stage_run_id=str(stage_row.stage_run_id),
        )
        for step_row in step_rows:
            self._dispatch_step(
                db_session=db_session,
                step_row=step_row,
                project_id=project_id,
                project_slug=project_slug,
                candidates=candidates,
                actor_id=actor_id,
                revision=revision,
            )
        return

    def _dispatch_step(
            self,
            *,
            db_session: DbSession,
            step_row: Any,
            project_id: str,
            project_slug: str,
            candidates: Tuple[DispatchCandidate, ...],
            actor_id: Optional[str],
            revision: SourceRevision
        ) -> None:
        """
            Dispatch a single step's job. ``build`` / ``test`` /
            ``infra`` / ``provision`` / ``rpa`` route through the
            reused Layer-6 dispatch paths. ``script`` steps have no
            execution path, so they are marked ``FAILED`` with
            :data:`SCRIPT_STEP_NOT_EXECUTED_REASON` -- never
            ``COMPLETED``.

            The dispatched orchestration run id is recorded on
            :attr:`PipelineStepRun.layer5_run_id` so the run-terminal
            bus subscriber can correlate the terminal event back to
            this step.

            :param revision: The run's commit + ref, for build steps.

            :returns: None.
        """
        job_kind = step_row.job_kind
        if job_kind == JOB_KIND_SCRIPT:
            # Nothing can execute a script step: no pod executor runs
            # them. Report the step FAILED with the reason instead of
            # pretending it ran -- a COMPLETED here was a false green
            # (audit ORG-F15). The failure fails the stage, skips its
            # dependents, and fails the run.
            _LOGGER.warning(
                "pychestrate.pipelines.orchestrator.script_step_not_executed"
                " step_run_id=%s",
                str(step_row.step_run_id),
            )
            self._mirror_step_terminal(
                db_session=db_session,
                step_run_id=str(step_row.step_run_id),
                final_state=StepState.FAILED,
                layer5_run_id=None,
                reason=SCRIPT_STEP_NOT_EXECUTED_REASON,
            )
            return

        try:
            layer5_run_id = self._dispatch_layer5_job(
                db_session=db_session,
                job_kind=job_kind,
                step_row=step_row,
                project_id=project_id,
                project_slug=project_slug,
                candidates=candidates,
                actor_id=actor_id,
                revision=revision,
            )
        except Exception as dispatch_err:  # noqa: BLE001 -- see below
            # A dispatch failure is a legitimate stage outcome: the
            # step fails, the stage fails, and the DAG walk skips its
            # dependents. We capture the reason on the row rather than
            # letting the exception abort the whole pipeline trigger.
            _LOGGER.warning(
                "pychestrate.pipelines.orchestrator.step_dispatch_failed"
                " step_run_id=%s job_kind=%s error=%s",
                str(step_row.step_run_id), job_kind, dispatch_err,
            )
            reason = "dispatch failed: {}".format(dispatch_err)
            self._mirror_step_terminal(
                db_session=db_session,
                step_run_id=str(step_row.step_run_id),
                final_state=StepState.FAILED,
                layer5_run_id=None,
                reason=reason,
            )
            return

        step_row.state = StepState.DISPATCHED
        step_row.layer5_run_id = layer5_run_id
        db_session.flush()
        return

    def _dispatch_layer5_job(
            self,
            *,
            db_session: DbSession,
            job_kind: str,
            step_row: Any,
            project_id: str,
            project_slug: str,
            candidates: Tuple[DispatchCandidate, ...],
            actor_id: Optional[str],
            revision: SourceRevision
        ) -> str:
        """
            Route a step to the reused Layer-6 dispatch path matching
            its ``job_kind`` and return the dispatched orchestration
            run id.

            :param revision: The run's commit + ref, for build steps.

            :raises: Exception -- any dispatch error bubbles to the
                     caller, which records it as a step failure.
        """
        inputs = dict(step_row.inputs or {})

        if job_kind == JOB_KIND_BUILD:
            run_id = self._dispatch_build_job(
                db_session=db_session,
                inputs=inputs,
                project_id=project_id,
                project_slug=project_slug,
                candidates=candidates,
                actor_id=actor_id,
                revision=revision,
            )
            return run_id

        if job_kind == JOB_KIND_TEST:
            run_id = self._dispatch_test_job(
                db_session=db_session,
                inputs=inputs,
                project_id=project_id,
                project_slug=project_slug,
                candidates=candidates,
                actor_id=actor_id,
            )
            return run_id

        if job_kind == JOB_KIND_RPA:
            run_id = self._dispatch_rpa_job(
                db_session=db_session,
                inputs=inputs,
                project_id=project_id,
                project_slug=project_slug,
                candidates=candidates,
                actor_id=actor_id,
            )
            return run_id

        if job_kind in (JOB_KIND_INFRA, JOB_KIND_PROVISION):
            run_id = self._dispatch_infra_job(
                db_session=db_session,
                inputs=inputs,
                project_id=project_id,
                project_slug=project_slug,
                actor_id=actor_id,
            )
            return run_id

        err_lines = ["No Layer-5 dispatch path for pipeline step job_kind."]
        err_lines.append("JOB_KIND: {}".format(job_kind))
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    def _dispatch_build_job(
            self,
            *,
            db_session: DbSession,
            inputs: Dict[str, Any],
            project_id: str,
            project_slug: str,
            candidates: Tuple[DispatchCandidate, ...],
            actor_id: Optional[str],
            revision: SourceRevision
        ) -> str:
        """
            Dispatch a ``build`` step via the reused build service.

            The build targets the pipeline run's commit: unless the
            step pins its own ``commit_sha`` / ``branch``, the run's
            ``commit_sha`` and the branch named by its ``ref`` are
            added to the runner inputs the build envelope reads them
            from. Without them the envelope carried the all-zero
            placeholder commit, so a green build said nothing about
            the commit the pipeline ran for.

            :param revision: The run's commit + ref.
        """
        if self._build_service is None:
            raise RuntimeError("build dispatch not wired") from None

        runner_kind = inputs.get("runner_kind", "makefile")
        runner_inputs = dict(inputs)
        if "commit_sha" not in runner_inputs and len(revision.commit_sha) > 0:
            runner_inputs["commit_sha"] = revision.commit_sha
        branch = self._branch_from_ref(ref=revision.ref)
        if "branch" not in runner_inputs and len(branch) > 0:
            runner_inputs["branch"] = branch
        build_inputs = self._build_service.BuildRunInputs(
            runner_kind=runner_kind,
            runner_inputs=runner_inputs,
        )
        aspects = self._build_service.BuildTriggerAspects(
            actor_id=actor_id,
            candidates=tuple(candidates),
            project_slug=project_slug,
        )
        view = self._build_service.trigger_run(
            db_session=db_session,
            project_id=project_id,
            inputs=build_inputs,
            aspects=aspects,
        )
        rtnval = str(view.run_id)
        return rtnval

    def _dispatch_rpa_job(
            self,
            *,
            db_session: DbSession,
            inputs: Dict[str, Any],
            project_id: str,
            project_slug: str,
            candidates: Tuple[DispatchCandidate, ...],
            actor_id: Optional[str]
        ) -> str:
        """
            Dispatch an ``rpa`` step via the reused RPA service: the
            step's ``spec_id`` names the specification and
            ``work_packet`` the packet merged over its defaults.
        """
        if self._rpa_service is None:
            raise RuntimeError("rpa dispatch not wired") from None

        spec_id = str(inputs.get("spec_id", "") or "")
        work_packet = inputs.get("work_packet", {}) or {}
        if not isinstance(work_packet, dict):
            work_packet = {}
        aspects = self._rpa_service.RpaTriggerAspects(
            actor_id=actor_id,
            candidates=tuple(candidates),
            project_slug=project_slug,
            trigger_cause={"kind": "pipeline"},
            idempotency_window_seconds=0,
        )
        view = self._rpa_service.trigger_job(
            db_session=db_session,
            project_id=project_id,
            spec_id=spec_id,
            work_packet=work_packet,
            aspects=aspects,
        )
        rtnval = str(view.job_id)
        return rtnval

    def _dispatch_test_job(
            self,
            *,
            db_session: DbSession,
            inputs: Dict[str, Any],
            project_id: str,
            project_slug: str,
            candidates: Tuple[DispatchCandidate, ...],
            actor_id: Optional[str]
        ) -> str:
        """
            Dispatch a ``test`` step via the reused
            :class:`TestOrchestrator`.
        """
        if self._test_orchestrator is None:
            raise RuntimeError("test dispatch not wired") from None

        catalog_entry_id = inputs.get("catalog_entry_id", "")
        from ccai.pychestrate.webservice.orchestration.test.orchestrator import (
            TriggerRunRequest,
        )
        request = TriggerRunRequest(
            project_id=project_id,
            project_slug=project_slug,
            catalog_entry_id=catalog_entry_id,
            triggered_by=actor_id,
            inputs=dict(inputs),
            candidates=tuple(candidates),
        )
        outcome = self._test_orchestrator.trigger_run(
            db_session=db_session, request=request,
        )
        rtnval = str(outcome.run_id)
        return rtnval

    def _dispatch_infra_job(
            self,
            *,
            db_session: DbSession,
            inputs: Dict[str, Any],
            project_id: str,
            project_slug: str,
            actor_id: Optional[str]
        ) -> str:
        """
            Dispatch an ``infra`` / ``provision`` step via the reused
            infra-runs service.
        """
        if self._infra_service is None:
            raise RuntimeError("provision dispatch not wired") from None

        environment_id = inputs.get("environment_id", "")
        driver_name = inputs.get("driver_name", "terraform")
        action_raw = inputs.get("action", "plan")
        action = self._infra_service.InfraAction(action_raw)
        infra_inputs = self._infra_service.InfraRunInputs(
            environment_id=environment_id,
            driver_name=driver_name,
            action=action,
            driver_inputs=dict(inputs.get("driver_inputs", {})),
        )
        aspects = self._infra_service.InfraTriggerAspects(
            actor_id=actor_id,
            project_slug=project_slug,
        )
        view = self._infra_service.trigger_run(
            db_session=db_session,
            project_id=project_id,
            inputs=infra_inputs,
            aspects=aspects,
        )
        rtnval = str(view.run_id)
        return rtnval

    # -----------------------------------------------------------------
    # Run-terminal bus subscriber
    # -----------------------------------------------------------------

    def _on_run_terminal(self, event: EntityEvent) -> None:
        """
            Run-state-machine terminal-event handler. Correlates the
            terminal run id back to a :class:`PipelineStepRun`, mirrors
            the outcome, and re-drives the DAG walk for the owning
            pipeline run.

            Bus subscribers run outside a request scope, so this opens
            its own session via the injected factory.

            :param event: The published ``entity.run.*`` event.

            :returns: None.
        """
        payload = event.payload or {}
        run_id = payload.get("run_id", None)
        if run_id is None:
            return

        session = self._session_factory()
        try:
            step_row = self._find_step_by_layer5_run(
                db_session=session, layer5_run_id=str(run_id),
            )
            if step_row is None:
                # Not a pipeline-dispatched run -- ignore.
                return

            final_state = self._step_state_for_topic(topic=event.topic)
            stage_run_id = str(step_row.stage_run_id)
            stage_row = definition_repository.find_stage_run_by_id(
                db_session=session, stage_run_id=stage_run_id,
            )
            if stage_row is None:
                return
            pipeline_run_id = str(stage_row.run_id)

            project_id = self._project_id_for_run(
                db_session=session, run_id=pipeline_run_id,
            )
            followup_candidates = self._eligible_candidates_for_project(
                db_session=session, project_id=project_id,
            )

            self._mirror_step_terminal(
                db_session=session,
                step_run_id=str(step_row.step_run_id),
                final_state=final_state,
                layer5_run_id=str(run_id),
                reason="run-state terminal: {}".format(event.topic),
            )
            session.commit()

            # Re-evaluate the DAG: dispatch any newly-eligible stage,
            # skip the dependents of a failed one. Candidates are
            # rebuilt from the project's currently-enrolled, REGISTERED
            # pods -- the same capability-based selection the trigger
            # path uses.
            self._dispatch_eligible_stages(
                db_session=session,
                run_id=pipeline_run_id,
                project_id=project_id,
                project_slug="",
                candidates=followup_candidates,
                actor_id=None,
            )
            session.commit()
        finally:
            session.close()
        return

    def _project_id_for_run(
            self, *, db_session: DbSession, run_id: str
        ) -> str:
        """
            Resolve the owning project id for a pipeline run.
        """
        run_row = definition_repository.find_run_by_id(
            db_session=db_session, run_id=run_id,
        )
        if run_row is None:
            rtnval = ""
            return rtnval
        rtnval = str(run_row.project_id)
        return rtnval

    def _source_revision_for_run(
            self, *, db_session: DbSession, run_id: str
        ) -> SourceRevision:
        """
            Read the commit + ref a pipeline run was triggered at.

            :param db_session: Active SQLAlchemy session.
            :param run_id: Pipeline run id.

            :returns: :class:`SourceRevision` (empty strings when the
                      run row is missing).
        """
        run_row = definition_repository.find_run_by_id(
            db_session=db_session, run_id=run_id,
        )
        if run_row is None:
            rtnval = SourceRevision(commit_sha="", ref="")
            return rtnval
        rtnval = SourceRevision(
            commit_sha=str(run_row.commit_sha or ""),
            ref=str(run_row.ref or ""),
        )
        return rtnval

    @staticmethod
    def _branch_from_ref(*, ref: str) -> str:
        """
            The branch a git ref names: ``refs/heads/main`` and ``main``
            both give ``main``; other ``refs/*`` (tags, pull refs) name
            no branch.

            :param ref: Git ref, possibly empty.

            :returns: Branch name, or an empty string.
        """
        if ref is None or len(ref) == 0:
            rtnval = ""
            return rtnval
        if ref.startswith(GIT_BRANCH_REF_PREFIX):
            rtnval = ref[len(GIT_BRANCH_REF_PREFIX):]
            return rtnval
        if ref.startswith("refs/"):
            rtnval = ""
            return rtnval
        rtnval = ref
        return rtnval

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _find_step_by_layer5_run(
            self, *, db_session: DbSession, layer5_run_id: str
        ) -> Optional[Any]:
        """
            Locate the :class:`PipelineStepRun` whose dispatched
            orchestration run matches ``layer5_run_id``.
        """
        from ccai.pychestrate.webservice.orchestration.pipelines.definition.models import (
            PipelineStepRun,
        )
        rtnval = (
            db_session.query(PipelineStepRun)
            .filter(PipelineStepRun.layer5_run_id == layer5_run_id)
            .first()
        )
        return rtnval

    def _mirror_step_terminal(
            self,
            *,
            db_session: DbSession,
            step_run_id: str,
            final_state: StepState,
            layer5_run_id: Optional[str],
            reason: str
        ) -> None:
        """
            Mirror a terminal outcome onto a step via the reused
            :func:`definition.service.apply_step_terminal`, which
            cascades stage + pipeline bookkeeping.
        """
        definition_service.apply_step_terminal(
            db_session=db_session,
            step_run_id=step_run_id,
            final_state=final_state,
            layer5_run_id=layer5_run_id,
            reason=reason,
        )
        return

    def _skip_stage(
            self,
            *,
            db_session: DbSession,
            stage_run_id: str,
            reason: str
        ) -> None:
        """
            Flip a blocked stage and all of its steps to ``SKIPPED``.
            The step terminal mirror cascades the stage + pipeline
            state.
        """
        step_rows = definition_repository.list_steps_for_stage(
            db_session=db_session, stage_run_id=stage_run_id,
        )
        if len(step_rows) == 0:
            # A stage with no steps cannot cascade through the step
            # mirror -- mark the stage row directly.
            from ccai.pychestrate.core.defaults import utc_now
            stage_row = definition_repository.find_stage_run_by_id(
                db_session=db_session, stage_run_id=stage_run_id,
            )
            if stage_row is not None:
                stage_row.state = StageState.SKIPPED
                stage_row.finished_at = utc_now()
                stage_row.final_state_reason = reason
                db_session.flush()
            return
        for step_row in step_rows:
            if step_row.state in (
                StepState.PENDING, StepState.DISPATCHED, StepState.RUNNING,
            ):
                self._mirror_step_terminal(
                    db_session=db_session,
                    step_run_id=str(step_row.step_run_id),
                    final_state=StepState.SKIPPED,
                    layer5_run_id=None,
                    reason=reason,
                )
        # The reused step-terminal cascade aggregates an all-SKIPPED
        # stage to COMPLETED (it has no failed step). A blocked stage
        # is SKIPPED, not COMPLETED -- correct the stage row directly
        # so its own dependents skip rather than dispatch.
        from ccai.pychestrate.core.defaults import utc_now
        stage_row = definition_repository.find_stage_run_by_id(
            db_session=db_session, stage_run_id=stage_run_id,
        )
        if stage_row is not None:
            stage_row.state = StageState.SKIPPED
            if stage_row.finished_at is None:
                stage_row.finished_at = utc_now()
            stage_row.final_state_reason = reason
            db_session.flush()
        return

    def _maybe_finalize_pipeline(
            self, *, db_session: DbSession, run_id: str
        ) -> None:
        """
            Finalize the pipeline run when every stage has resolved
            and the reused step-terminal cascade has not already done
            so (it only fires on the last *step* terminal -- a run
            whose tail stages were all skipped needs an explicit
            finalize).

            :returns: None.
        """
        from ccai.pychestrate.core.defaults import utc_now

        run_row = definition_repository.find_run_by_id(
            db_session=db_session, run_id=run_id,
        )
        if run_row is None:
            return
        if run_row.state in (
            PipelineRunState.COMPLETED,
            PipelineRunState.FAILED,
            PipelineRunState.CANCELLED,
            PipelineRunState.REJECTED,
        ):
            return

        stage_rows = definition_repository.list_stages_for_run(
            db_session=db_session, run_id=run_id,
        )
        if len(stage_rows) == 0:
            return

        non_terminal = (StageState.PENDING, StageState.RUNNING)
        for stage in stage_rows:
            if stage.state in non_terminal:
                # Still work in flight -- a later terminal event
                # finalizes the run.
                return

        has_failure = False
        for stage in stage_rows:
            if stage.state in (
                StageState.FAILED, StageState.SKIPPED, StageState.CANCELLED,
            ):
                has_failure = True

        if has_failure is True:
            run_row.state = PipelineRunState.FAILED
            run_row.final_state_reason = "stage_failure"
        else:
            run_row.state = PipelineRunState.COMPLETED
            run_row.final_state_reason = ""
        run_row.finished_at = utc_now()
        db_session.flush()
        return

    @staticmethod
    def _eligible_candidates_for_project(
            *, db_session: DbSession, project_id: str
        ) -> Tuple[DispatchCandidate, ...]:
        """
            Build the :class:`DispatchCandidate` tuple from every pod
            enrolled in the project carrying at least one REGISTERED
            client registration -- the same capability-based selection
            the build / test / provision REST routes use. May be empty;
            an empty tuple yields a "no eligible pod" dispatch failure
            which the DAG walk treats as a stage failure.

            :returns: Tuple of dispatch candidates (possibly empty).
        """
        from ccai.pychestrate.webservice.pods.models import (
            PodDefinition,
            PodRegistration,
            RegistrationState,
        )

        pod_rows = (
            db_session.query(PodDefinition)
            .filter(PodDefinition.project_id == project_id)
            .all()
        )
        candidates: List[DispatchCandidate] = []
        for pod_row in pod_rows:
            pod_id = str(pod_row.pod_id)
            registrations = (
                db_session.query(PodRegistration)
                .filter(PodRegistration.pod_id == pod_id)
                .filter(PodRegistration.state == RegistrationState.REGISTERED)
                .all()
            )
            for reg in registrations:
                if reg.client_id is None:
                    continue
                candidates.append(
                    DispatchCandidate(
                        client_id=str(reg.client_id),
                        pod_id=pod_id,
                        capability_tags=tuple(),
                        inflight_dispatch_count=0,
                        last_dispatched_at_iso="",
                    )
                )
        rtnval = tuple(candidates)
        return rtnval

    @staticmethod
    def _parse_needs(*, needs_csv: Optional[str]) -> Tuple[str, ...]:
        """
            Split the persisted ``needs`` CSV into a tuple.
        """
        if needs_csv is None or len(needs_csv) == 0:
            rtnval: Tuple[str, ...] = ()
            return rtnval
        parts = [p for p in needs_csv.split(",") if len(p) > 0]
        rtnval = tuple(parts)
        return rtnval

    @staticmethod
    def _step_state_for_topic(*, topic: str) -> StepState:
        """
            Map a run-state terminal bus topic to the matching
            :class:`StepState`.
        """
        if topic == "entity.run.completed":
            rtnval = StepState.COMPLETED
            return rtnval
        if topic == "entity.run.cancelled":
            rtnval = StepState.CANCELLED
            return rtnval
        rtnval = StepState.FAILED
        return rtnval


# Module-level seam: the REST route resolves the live orchestrator
# here. ``bootstrap_phase6_runtime`` publishes it via
# :func:`set_active_pipeline_orchestrator`.
ACTIVE_PIPELINE_ORCHESTRATOR: Optional[PipelineOrchestrator] = None


def set_active_pipeline_orchestrator(
        *, orchestrator: Optional[PipelineOrchestrator]
    ) -> None:
    """
        Publish the live :class:`PipelineOrchestrator` on the module
        seam the pipeline-run REST routes resolve.

        :param orchestrator: The constructed orchestrator, or ``None``
                             to clear the seam (used by tests).

        :returns: None.
    """
    global ACTIVE_PIPELINE_ORCHESTRATOR
    ACTIVE_PIPELINE_ORCHESTRATOR = orchestrator
    return


def get_active_pipeline_orchestrator() -> Optional[PipelineOrchestrator]:
    """
        Resolve the live :class:`PipelineOrchestrator` published on the
        module seam, or ``None`` when the bootstrap has not wired it.

        :returns: The active orchestrator or None.
    """
    rtnval = ACTIVE_PIPELINE_ORCHESTRATOR
    return rtnval


__all__ = [
    "PipelineOrchestrator",
    "PipelineTriggerInputs",
    "PipelineRunConflictError",
    "PipelineMatrixUnsupportedError",
    "SCRIPT_STEP_NOT_EXECUTED_REASON",
    "SourceRevision",
    "set_active_pipeline_orchestrator",
    "get_active_pipeline_orchestrator",
    "RUN_TERMINAL_TOPICS",
]
