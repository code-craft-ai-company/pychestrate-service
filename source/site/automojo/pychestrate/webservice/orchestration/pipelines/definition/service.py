"""
.. module:: orchestration.pipelines.definition.service
    :synopsis: Pipeline-definition facade — load / trigger / read / mirror.

M1 ships a synchronous surface:

* :func:`load_from_source` — parse + validate + DAG-check +
  cache the document. Pure (no run created).
* :func:`trigger_run` — runs ``load_from_source`` against the
  caller-supplied bytes, persists a PipelineRun + StageRuns +
  StepRuns in PENDING, emits ``entity.pipeline.defined`` and
  ``entity.pipeline.run_started``. Returns a fully-populated
  :class:`PipelineRunView`.
* :func:`apply_step_terminal` — mirrors a Layer-5 terminal
  outcome onto a step row; the stage / pipeline cascade
  bookkeeping uses the M1 sequential-walk algorithm (no
  ``when:`` evaluation yet — every stage transitions to
  COMPLETED on success and FAILED on any step failure).
* :func:`get_pipeline_run` — read-side helper.

The real Layer-5 dispatcher wiring + variable resolution + RBAC
+ cancellation + event mirror cascade land in M2.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.orchestration.pipelines.definition import (
    repository,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.canonicalization import (
    canonicalize_document,
    compute_pipeline_digest,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.dag import (
    build_dag,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.errors import (
    PipelineDocumentInvalidError,
    PipelineRunNotFoundError,
    PipelineStepKindUnknownError,
    PipelineStepRunNotFoundError,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.events import (
    PipelineEventTopics,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.factories.step_kind_protocol import (
    PipelineStepKindProtocol,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.models import (
    PipelineRun,
    PipelineRunState,
    PipelineStageRun,
    PipelineStepRun,
    StageState,
    StepState,
    TriggerCause,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.parser import (
    PipelineDocument,
    parse_document,
)


PIPELINE_STEP_KIND_PROTOCOL: str = "pipeline_step_kind"


@dataclass(frozen=True)
class TriggerAspects:
    """
        Caller-tunable knobs for :func:`trigger_run`. M1 honors
        ``trigger_cause`` and ``actor_id`` only; the M2 variable
        bundle and the RBAC scope land here.

        :param trigger_cause: How the run was triggered. Persisted
                              on the row.
        :param actor_id: Optional UUID of the human / service
                         account that triggered the run.
    """
    trigger_cause: TriggerCause = TriggerCause.MANUAL
    actor_id: Optional[str] = None


@dataclass(frozen=True)
class PipelineStepRunView:
    """
        Caller-facing read-model for a single step.
    """
    step_run_id: str
    stage_run_id: str
    step_id: str
    step_index: int
    kind_name: str
    job_kind: str
    layer5_run_id: Optional[str]
    state: StepState
    attempt: int
    inputs: Mapping[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    final_state_reason: str = ""


@dataclass(frozen=True)
class PipelineStageRunView:
    """
        Caller-facing read-model for a single stage.
    """
    stage_run_id: str
    run_id: str
    stage_id: str
    stage_index: int
    state: StageState
    when_clause: str
    needs: Tuple[str, ...] = ()
    steps: Tuple[PipelineStepRunView, ...] = ()
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    final_state_reason: str = ""


@dataclass(frozen=True)
class PipelineRunView:
    """
        Caller-facing read-model for a pipeline run.
    """
    run_id: str
    project_id: str
    commit_sha: str
    ref: str
    filename: str
    pipeline_digest_sha256: str
    state: PipelineRunState
    trigger_cause: TriggerCause
    actor_id: Optional[str]
    stages: Tuple[PipelineStageRunView, ...] = ()
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    final_state_reason: str = ""


def load_from_source(
        *,
        db_session: DbSession,
        project_id: str,
        commit_sha: str,
        filename: str,
        document_bytes: bytes
    ) -> PipelineDocument:
    """
        Parse + validate ``document_bytes``, run DAG cycle
        detection, validate every step's kind exists, cache the
        canonicalized document, emit
        :data:`PipelineEventTopics.DEFINED`.

        Pure with respect to pipeline runs — no PipelineRun row
        is created here.

        :raises: PipelineDocumentInvalidError on any parse,
                 schema, or DAG violation.
        :raises: PipelineStepKindUnknownError when a step
                 references an unregistered kind.
    """
    document = parse_document(
        document_bytes=document_bytes, filename=filename,
    )
    build_dag(document=document)
    _validate_step_kinds(document=document)

    canonical = canonicalize_document(document=document)
    digest = compute_pipeline_digest(document=document)
    now = utc_now()
    repository.upsert_document_cache(
        db_session=db_session,
        project_id=project_id,
        commit_sha=commit_sha,
        filename=filename,
        pipeline_digest_sha256=digest,
        canonical_json=canonical,
        cached_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PipelineEventTopics.DEFINED,
            payload={
                "project_id": project_id,
                "commit_sha": commit_sha,
                "filename": filename,
                "pipeline_digest_sha256": digest,
                "stage_count": len(document.stages),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return document


def trigger_run(
        *,
        db_session: DbSession,
        project_id: str,
        commit_sha: str,
        ref: str,
        filename: str,
        document_bytes: bytes,
        aspects: Optional[TriggerAspects] = None
    ) -> PipelineRunView:
    """
        Run :func:`load_from_source`, then create a PipelineRun
        + StageRuns + StepRuns in PENDING. M1 records the
        ``job_kind`` from each step's primary
        :class:`JobProduction` so the M2 dispatcher can route
        on the column without re-running the kind. Emits
        :data:`PipelineEventTopics.RUN_STARTED`.

        :raises: PipelineDocumentInvalidError, PipelineDagCycleError,
                 PipelineStepKindUnknownError.
    """
    effective = aspects or TriggerAspects()
    document = load_from_source(
        db_session=db_session,
        project_id=project_id,
        commit_sha=commit_sha,
        filename=filename,
        document_bytes=document_bytes,
    )

    digest = compute_pipeline_digest(document=document)
    now = utc_now()

    pipeline_row = repository.insert_pipeline_run(
        db_session=db_session,
        project_id=project_id,
        commit_sha=commit_sha,
        ref=ref,
        filename=filename,
        pipeline_digest_sha256=digest,
        trigger_cause=effective.trigger_cause,
        actor_id=effective.actor_id,
        started_at=now,
    )
    pipeline_row.state = PipelineRunState.RUNNING
    db_session.flush()

    for stage_index, stage in enumerate(document.stages):
        needs_csv = ",".join(stage.needs)
        stage_row = repository.insert_stage_run(
            db_session=db_session,
            run_id=str(pipeline_row.run_id),
            stage_id=stage.stage_id,
            stage_index=stage_index,
            when_clause=stage.when,
            needs_csv=needs_csv,
        )
        for step_index, step in enumerate(stage.steps):
            kind_cls = _resolve_step_kind(kind_name=step.kind_name)
            ok, kind_issues = kind_cls.validate_inputs(inputs=step.inputs)
            if ok is False:
                err_lines = [
                    "Step '{}' inputs failed validation: {} issue(s).".format(
                        step.step_id, len(kind_issues),
                    ),
                ]
                err_lines.append("STAGE_ID: {}".format(stage.stage_id))
                err_lines.append("KIND: {}".format(step.kind_name))
                for issue_index, issue in enumerate(kind_issues):
                    err_lines.append(
                        "  [{}] {}".format(issue_index + 1, issue),
                    )
                err_msg = os.linesep.join(err_lines)
                raise PipelineDocumentInvalidError(err_msg) from None
            productions = kind_cls.produce_jobs(
                project_id=project_id,
                run_id=str(pipeline_row.run_id),
                stage_id=stage.stage_id,
                step_id=step.step_id,
                inputs=step.inputs,
            )
            primary_job_kind = (
                productions[0].job_kind
                if len(productions) > 0
                else step.kind_name
            )
            repository.insert_step_run(
                db_session=db_session,
                stage_run_id=str(stage_row.stage_run_id),
                step_id=step.step_id,
                step_index=step_index,
                kind_name=step.kind_name,
                job_kind=primary_job_kind,
                inputs=dict(step.inputs),
            )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PipelineEventTopics.RUN_STARTED,
            payload={
                "run_id": str(pipeline_row.run_id),
                "project_id": project_id,
                "commit_sha": commit_sha,
                "ref": ref,
                "filename": filename,
                "trigger_cause": effective.trigger_cause.value,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_pipeline_run(
        db_session=db_session, run_id=str(pipeline_row.run_id),
    )
    return rtnval


def apply_step_terminal(
        *,
        db_session: DbSession,
        step_run_id: str,
        final_state: StepState,
        layer5_run_id: Optional[str] = None,
        reason: str = ""
    ) -> PipelineStepRunView:
    """
        Mirror a Layer-5 terminal outcome onto a step row.
        M1 cascade is sequential — once every step in a stage
        is terminal, the stage transitions; once every stage
        is terminal, the pipeline transitions. ``when:``
        evaluation lands in M2.

        Emits :data:`PipelineEventTopics.STEP_COMPLETED` per
        step and :data:`PipelineEventTopics.STAGE_COMPLETED` /
        ``RUN_COMPLETED`` as appropriate.

        :raises: PipelineStepRunNotFoundError on miss.
    """
    if final_state not in (
        StepState.COMPLETED,
        StepState.FAILED,
        StepState.CANCELLED,
        StepState.SKIPPED,
    ):
        err_lines = [
            "apply_step_terminal requires a terminal step state.",
        ]
        err_lines.append("RECEIVED: {}".format(final_state.value))
        err_msg = os.linesep.join(err_lines)
        raise PipelineDocumentInvalidError(err_msg) from None

    row = repository.find_step_run_by_id(
        db_session=db_session, step_run_id=step_run_id,
    )
    if row is None:
        err_lines = ["Pipeline step run not found."]
        err_lines.append("STEP_RUN_ID: {}".format(step_run_id))
        err_msg = os.linesep.join(err_lines)
        raise PipelineStepRunNotFoundError(err_msg) from None

    now = utc_now()
    row.state = final_state
    row.layer5_run_id = layer5_run_id
    row.finished_at = now
    row.final_state_reason = reason
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PipelineEventTopics.STEP_COMPLETED,
            payload={
                "step_run_id": str(row.step_run_id),
                "stage_run_id": str(row.stage_run_id),
                "state": final_state.value,
                "layer5_run_id": layer5_run_id,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )

    _maybe_complete_stage(
        db_session=db_session, stage_run_id=str(row.stage_run_id), now=now,
    )
    db_session.commit()
    rtnval = _step_to_view(row=row)
    return rtnval


def get_pipeline_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> PipelineRunView:
    """
        Read a pipeline run + its stages + steps.

        :raises: PipelineRunNotFoundError on miss.
    """
    pipeline = repository.find_run_by_id(
        db_session=db_session, run_id=run_id,
    )
    if pipeline is None:
        err_lines = ["Pipeline run not found."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise PipelineRunNotFoundError(err_msg) from None

    stages = repository.list_stages_for_run(
        db_session=db_session, run_id=run_id,
    )
    stage_views: List[PipelineStageRunView] = []
    for stage in stages:
        steps = repository.list_steps_for_stage(
            db_session=db_session, stage_run_id=str(stage.stage_run_id),
        )
        step_views = tuple(_step_to_view(row=s) for s in steps)
        needs_tuple: Tuple[str, ...] = tuple()
        if stage.needs_csv is not None and len(stage.needs_csv) > 0:
            needs_tuple = tuple(
                part for part in stage.needs_csv.split(",")
                if len(part) > 0
            )
        stage_views.append(
            PipelineStageRunView(
                stage_run_id=str(stage.stage_run_id),
                run_id=str(stage.run_id),
                stage_id=stage.stage_id,
                stage_index=stage.stage_index,
                state=stage.state,
                when_clause=stage.when_clause,
                needs=needs_tuple,
                steps=step_views,
                started_at=stage.started_at,
                finished_at=stage.finished_at,
                final_state_reason=stage.final_state_reason,
            )
        )

    rtnval = PipelineRunView(
        run_id=str(pipeline.run_id),
        project_id=str(pipeline.project_id),
        commit_sha=pipeline.commit_sha,
        ref=pipeline.ref,
        filename=pipeline.filename,
        pipeline_digest_sha256=pipeline.pipeline_digest_sha256,
        state=pipeline.state,
        trigger_cause=pipeline.trigger_cause,
        actor_id=(
            str(pipeline.actor_id) if pipeline.actor_id is not None else None
        ),
        stages=tuple(stage_views),
        started_at=pipeline.started_at,
        finished_at=pipeline.finished_at,
        final_state_reason=pipeline.final_state_reason,
    )
    return rtnval


def _maybe_complete_stage(
        *,
        db_session: DbSession,
        stage_run_id: str,
        now: datetime
    ) -> None:
    """
        Aggregate per-step terminal states onto the stage and
        cascade onto the pipeline when every stage has resolved.
    """
    stage_row = repository.find_stage_run_by_id(
        db_session=db_session, stage_run_id=stage_run_id,
    )
    if stage_row is None:
        return

    steps = repository.list_steps_for_stage(
        db_session=db_session, stage_run_id=stage_run_id,
    )
    if len(steps) == 0:
        return

    pending_states = (
        StepState.PENDING, StepState.DISPATCHED, StepState.RUNNING,
    )
    for step in steps:
        if step.state in pending_states:
            return

    has_failure = any(
        step.state in (StepState.FAILED, StepState.CANCELLED)
        for step in steps
    )
    if has_failure is True:
        new_stage_state = StageState.FAILED
    else:
        new_stage_state = StageState.COMPLETED

    if stage_row.state in (StageState.COMPLETED, StageState.FAILED, StageState.CANCELLED):
        return

    stage_row.state = new_stage_state
    stage_row.finished_at = now
    stage_row.when_clause_resolved = "succeeded" if new_stage_state == StageState.COMPLETED else "failed"
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PipelineEventTopics.STAGE_COMPLETED,
            payload={
                "stage_run_id": str(stage_row.stage_run_id),
                "run_id": str(stage_row.run_id),
                "stage_id": stage_row.stage_id,
                "state": new_stage_state.value,
            },
            source_event_id=new_uuid(),
        ),
    )

    _maybe_complete_pipeline(
        db_session=db_session, run_id=str(stage_row.run_id), now=now,
    )
    return


def _maybe_complete_pipeline(
        *,
        db_session: DbSession,
        run_id: str,
        now: datetime
    ) -> None:
    pipeline_row = repository.find_run_by_id(
        db_session=db_session, run_id=run_id,
    )
    if pipeline_row is None:
        return
    if pipeline_row.state in (
        PipelineRunState.COMPLETED,
        PipelineRunState.FAILED,
        PipelineRunState.CANCELLED,
        PipelineRunState.REJECTED,
    ):
        return

    stages = repository.list_stages_for_run(
        db_session=db_session, run_id=run_id,
    )
    if len(stages) == 0:
        return

    pending_states = (StageState.PENDING, StageState.RUNNING)
    for stage in stages:
        if stage.state in pending_states:
            return

    has_failure = any(
        stage.state in (StageState.FAILED, StageState.CANCELLED)
        for stage in stages
    )
    final_state = (
        PipelineRunState.FAILED if has_failure is True
        else PipelineRunState.COMPLETED
    )
    pipeline_row.state = final_state
    pipeline_row.finished_at = now
    pipeline_row.final_state_reason = (
        "stage_failure" if has_failure is True else ""
    )
    db_session.flush()

    duration_seconds = 0.0
    started_at = pipeline_row.started_at
    if started_at is not None:
        # SQLite returns tz-naive datetimes; normalize to UTC-aware
        # before subtracting so the test backend matches Postgres.
        if started_at.tzinfo is None:
            from datetime import timezone as _timezone
            started_at = started_at.replace(tzinfo=_timezone.utc)
        if now.tzinfo is None:
            from datetime import timezone as _timezone
            now = now.replace(tzinfo=_timezone.utc)
        duration_seconds = (now - started_at).total_seconds()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PipelineEventTopics.RUN_COMPLETED,
            payload={
                "run_id": str(pipeline_row.run_id),
                "project_id": str(pipeline_row.project_id),
                "final_state": final_state.value,
                "duration_seconds": duration_seconds,
            },
            source_event_id=new_uuid(),
        ),
    )
    return


def _validate_step_kinds(*, document: PipelineDocument) -> None:
    """
        Verify every step's ``kind_name`` resolves to a
        registered :class:`PipelineStepKindProtocol` impl.

        :raises: PipelineStepKindUnknownError listing every
                 unknown kind in a single multiline message.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=PIPELINE_STEP_KIND_PROTOCOL,
    )
    known: Dict[str, Type[PipelineStepKindProtocol]] = {}
    for impl in candidates:
        known[impl.kind_name()] = impl

    issues: List[str] = []
    for stage in document.stages:
        for step in stage.steps:
            if step.kind_name not in known:
                issues.append(
                    "stage '{}' step '{}' references unknown kind '{}'".format(
                        stage.stage_id, step.step_id, step.kind_name,
                    )
                )

    if len(issues) > 0:
        err_lines = [
            "Pipeline document references {} unknown step kind(s).".format(
                len(issues),
            ),
        ]
        err_lines.append("REGISTERED: {}".format(
            ", ".join(sorted(known.keys())),
        ))
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        err_msg = os.linesep.join(err_lines)
        raise PipelineStepKindUnknownError(err_msg) from None
    return


def _resolve_step_kind(
        *, kind_name: str
    ) -> Type[PipelineStepKindProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=PIPELINE_STEP_KIND_PROTOCOL,
    )
    for impl in candidates:
        if impl.kind_name() == kind_name:
            return impl
    err_lines = ["No registered pipeline_step_kind for name."]
    err_lines.append("KIND_NAME: {}".format(kind_name))
    err_msg = os.linesep.join(err_lines)
    raise PipelineStepKindUnknownError(err_msg) from None


def _step_to_view(*, row: PipelineStepRun) -> PipelineStepRunView:
    rtnval = PipelineStepRunView(
        step_run_id=str(row.step_run_id),
        stage_run_id=str(row.stage_run_id),
        step_id=row.step_id,
        step_index=row.step_index,
        kind_name=row.kind_name,
        job_kind=row.job_kind,
        layer5_run_id=(
            str(row.layer5_run_id) if row.layer5_run_id is not None else None
        ),
        state=row.state,
        attempt=row.attempt,
        inputs=dict(row.inputs or {}),
        started_at=row.started_at,
        finished_at=row.finished_at,
        final_state_reason=row.final_state_reason,
    )
    return rtnval
