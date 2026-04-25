"""
.. module:: orchestration.build.service
    :synopsis: Build-orchestration facade — trigger / mirror / read.

M1 ships:

* :func:`trigger_run` — resolve runner kind → validate inputs
  → compute repro digest → persist BuildRun + toolchain
  snapshots → emit ``entity.build.run_triggered``. M2 wires
  the actual Layer-5 dispatch handoff.
* :func:`apply_run_terminal` — mirror a Layer-5 outcome onto
  the BuildRun (``layer5_run_id``, ``finished_at``,
  ``state``); emits STATE_CHANGED + COMPLETED / FAILED /
  CANCELLED as appropriate.
* :func:`get_build_run` / :func:`list_build_runs_for_project`.
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
from automojo.pychestrate.webservice.orchestration.build import repository
from automojo.pychestrate.webservice.orchestration.build.errors import (
    BuildInputsInvalidError,
    BuildRunNotFoundError,
    BuildRunnerKindUnknownError,
)
from automojo.pychestrate.webservice.orchestration.build.events import (
    BuildEventTopics,
)
from automojo.pychestrate.webservice.orchestration.build.factories.runner_protocol import (
    BuildRunnerKindProtocol,
)
from automojo.pychestrate.webservice.orchestration.build.models import (
    BuildRun,
    BuildRunState,
    BuildToolchainSnapshot,
)
from automojo.pychestrate.webservice.orchestration.build.repro_snapshot import (
    BuildToolchainEntry,
    ReproSnapshot,
    compute_repro_digest,
)


BUILD_RUNNER_KIND_PROTOCOL: str = "build_runner_kind"
LIST_BUILD_RUNS_DEFAULT_LIMIT: int = 50
TERMINAL_STATES: Tuple[BuildRunState, ...] = (
    BuildRunState.COMPLETED,
    BuildRunState.FAILED,
    BuildRunState.CANCELLED,
)


@dataclass(frozen=True)
class BuildRunInputs:
    """
        Caller-supplied build-run inputs.

        :param runner_kind: Stable runner-kind identifier
                            (``"makefile"`` for the M1
                            reference).
        :param runner_inputs: Free-form input dict consumed by
                              the runner kind.
        :param input_files: ``{path: content_sha256}`` —
                            material in the repro digest.
        :param toolchain: Tuple of :class:`BuildToolchainEntry`.
        :param env: ``{key: value}`` — material in the repro
                    digest.
        :param annotations: Free-form metadata persisted on
                            the BuildRun.
    """
    runner_kind: str
    runner_inputs: Mapping[str, Any] = field(default_factory=dict)
    input_files: Mapping[str, str] = field(default_factory=dict)
    toolchain: Tuple[BuildToolchainEntry, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    annotations: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildTriggerAspects:
    """
        Caller-tunable trigger knobs.

        :param actor_id: Optional actor UUID persisted on the
                         row.
        :param pipeline_run_id: Optional pipeline-run id when
                                the trigger came from
                                6-pipeline-definition.
        :param pipeline_step_run_id: Optional pipeline-step-run
                                     id (peer to the above).
    """
    actor_id: Optional[str] = None
    pipeline_run_id: Optional[str] = None
    pipeline_step_run_id: Optional[str] = None


@dataclass(frozen=True)
class BuildToolchainSnapshotView:
    """
        Caller-facing toolchain row.
    """
    toolchain_key: str
    version: str
    fingerprint_sha256: str


@dataclass(frozen=True)
class BuildRunView:
    """
        Caller-facing read-model.
    """
    run_id: str
    project_id: str
    runner_kind: str
    repro_digest_sha256: str
    state: BuildRunState
    layer5_run_id: Optional[str]
    pipeline_run_id: Optional[str]
    pipeline_step_run_id: Optional[str]
    actor_id: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    final_state_reason: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    annotations: Mapping[str, Any] = field(default_factory=dict)
    toolchain: Tuple[BuildToolchainSnapshotView, ...] = ()


def trigger_run(
        *,
        db_session: DbSession,
        project_id: str,
        inputs: BuildRunInputs,
        aspects: Optional[BuildTriggerAspects] = None
    ) -> BuildRunView:
    """
        Resolve the runner kind, validate inputs, compute the
        repro digest, and persist a BuildRun + toolchain
        snapshots in PENDING. Emits
        :data:`BuildEventTopics.TRIGGERED`.

        :raises: BuildRunnerKindUnknownError when ``runner_kind``
                 has no registered factory.
        :raises: BuildInputsInvalidError when the runner kind's
                 ``validate_inputs`` rejects the payload.
    """
    if inputs.runner_kind is None or len(inputs.runner_kind) == 0:
        err_lines = ["BuildRunInputs.runner_kind must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise BuildInputsInvalidError(err_msg) from None

    runner_cls = _resolve_runner(runner_kind=inputs.runner_kind)
    ok, issues = runner_cls.validate_inputs(inputs=inputs.runner_inputs)
    if ok is False:
        err_lines = [
            "Build runner '{}' rejected inputs: {} issue(s).".format(
                inputs.runner_kind, len(issues),
            ),
        ]
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        err_msg = os.linesep.join(err_lines)
        raise BuildInputsInvalidError(err_msg) from None

    snapshot = ReproSnapshot(
        input_files=dict(inputs.input_files),
        toolchain=tuple(inputs.toolchain),
        env=dict(inputs.env),
    )
    digest = compute_repro_digest(snapshot=snapshot)

    effective = aspects or BuildTriggerAspects()
    now = utc_now()

    run_row = repository.insert_build_run(
        db_session=db_session,
        project_id=project_id,
        runner_kind=inputs.runner_kind,
        repro_digest_sha256=digest,
        actor_id=effective.actor_id,
        pipeline_run_id=effective.pipeline_run_id,
        pipeline_step_run_id=effective.pipeline_step_run_id,
        inputs=dict(inputs.runner_inputs),
        annotations=dict(inputs.annotations),
        started_at=now,
    )
    for entry in inputs.toolchain:
        repository.insert_toolchain_snapshot_row(
            db_session=db_session,
            run_id=str(run_row.run_id),
            toolchain_key=entry.key,
            version=entry.version,
            fingerprint_sha256=entry.fingerprint_sha256,
        )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=BuildEventTopics.TRIGGERED,
            payload={
                "run_id": str(run_row.run_id),
                "project_id": project_id,
                "runner_kind": inputs.runner_kind,
                "repro_digest_sha256": digest,
                "pipeline_run_id": effective.pipeline_run_id,
                "pipeline_step_run_id": effective.pipeline_step_run_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_build_run(
        db_session=db_session, run_id=str(run_row.run_id),
    )
    return rtnval


def apply_run_terminal(
        *,
        db_session: DbSession,
        run_id: str,
        final_state: BuildRunState,
        layer5_run_id: Optional[str] = None,
        reason: str = ""
    ) -> BuildRunView:
    """
        Mirror a Layer-5 outcome onto a build run. Idempotent
        on already-terminal rows. Emits STATE_CHANGED on every
        call and the kind-specific COMPLETED / FAILED /
        CANCELLED topic.

        :raises: BuildRunNotFoundError on miss.
        :raises: BuildInputsInvalidError when ``final_state``
                 is not in the M1 terminal set.
    """
    if final_state not in TERMINAL_STATES:
        err_lines = ["apply_run_terminal requires a terminal build state."]
        err_lines.append("RECEIVED: {}".format(final_state.value))
        err_msg = os.linesep.join(err_lines)
        raise BuildInputsInvalidError(err_msg) from None

    row = repository.find_run_by_id(db_session=db_session, run_id=run_id)
    if row is None:
        err_lines = ["Build run not found."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise BuildRunNotFoundError(err_msg) from None

    if row.state in TERMINAL_STATES:
        rtnval = get_build_run(db_session=db_session, run_id=run_id)
        return rtnval

    now = utc_now()
    row.state = final_state
    if layer5_run_id is not None:
        row.layer5_run_id = layer5_run_id
    row.finished_at = now
    row.final_state_reason = reason
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=BuildEventTopics.STATE_CHANGED,
            payload={
                "run_id": str(row.run_id),
                "project_id": str(row.project_id),
                "state": final_state.value,
                "layer5_run_id": layer5_run_id,
            },
            source_event_id=new_uuid(),
        ),
    )

    final_topic = BuildEventTopics.COMPLETED
    if final_state == BuildRunState.FAILED:
        final_topic = BuildEventTopics.FAILED
    elif final_state == BuildRunState.CANCELLED:
        final_topic = BuildEventTopics.CANCELLED
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=final_topic,
            payload={
                "run_id": str(row.run_id),
                "project_id": str(row.project_id),
                "state": final_state.value,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_build_run(db_session=db_session, run_id=run_id)
    return rtnval


def get_build_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> BuildRunView:
    """
        Read a build run + its toolchain rows.

        :raises: BuildRunNotFoundError on miss.
    """
    row = repository.find_run_by_id(db_session=db_session, run_id=run_id)
    if row is None:
        err_lines = ["Build run not found."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise BuildRunNotFoundError(err_msg) from None
    toolchain_rows = repository.list_toolchain_for_run(
        db_session=db_session, run_id=run_id,
    )
    rtnval = _to_view(row=row, toolchain_rows=toolchain_rows)
    return rtnval


def list_build_runs_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        limit: int = LIST_BUILD_RUNS_DEFAULT_LIMIT
    ) -> List[BuildRunView]:
    """
        Recent build runs for a project, newest-first.
    """
    rows = repository.list_runs_for_project(
        db_session=db_session, project_id=project_id, limit=limit,
    )
    rtnval: List[BuildRunView] = []
    for row in rows:
        toolchain_rows = repository.list_toolchain_for_run(
            db_session=db_session, run_id=str(row.run_id),
        )
        rtnval.append(_to_view(row=row, toolchain_rows=toolchain_rows))
    return rtnval


def _resolve_runner(*, runner_kind: str) -> Type[BuildRunnerKindProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=BUILD_RUNNER_KIND_PROTOCOL,
    )
    for impl in candidates:
        if impl.runner_kind() == runner_kind:
            return impl
    err_lines = ["No registered build_runner_kind for name."]
    err_lines.append("RUNNER_KIND: {}".format(runner_kind))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.runner_kind() for impl in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise BuildRunnerKindUnknownError(err_msg) from None


def _to_view(
        *,
        row: BuildRun,
        toolchain_rows: List[BuildToolchainSnapshot]
    ) -> BuildRunView:
    toolchain = tuple(
        BuildToolchainSnapshotView(
            toolchain_key=t.toolchain_key,
            version=t.version,
            fingerprint_sha256=t.fingerprint_sha256,
        )
        for t in toolchain_rows
    )
    rtnval = BuildRunView(
        run_id=str(row.run_id),
        project_id=str(row.project_id),
        runner_kind=row.runner_kind,
        repro_digest_sha256=row.repro_digest_sha256,
        state=row.state,
        layer5_run_id=(
            str(row.layer5_run_id) if row.layer5_run_id is not None else None
        ),
        pipeline_run_id=(
            str(row.pipeline_run_id)
            if row.pipeline_run_id is not None else None
        ),
        pipeline_step_run_id=(
            str(row.pipeline_step_run_id)
            if row.pipeline_step_run_id is not None else None
        ),
        actor_id=(
            str(row.actor_id) if row.actor_id is not None else None
        ),
        started_at=row.started_at,
        finished_at=row.finished_at,
        final_state_reason=row.final_state_reason,
        inputs=dict(row.inputs or {}),
        annotations=dict(row.annotations or {}),
        toolchain=toolchain,
    )
    return rtnval
