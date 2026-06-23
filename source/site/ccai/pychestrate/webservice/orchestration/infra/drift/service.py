"""
.. module:: orchestration.infra.drift.service
    :synopsis: Drift-detection facade — schedule / dispatch / ingest / read.

M1 ships:

* :func:`set_schedule` — upsert (project, environment) →
  checker + cron + enabled. Validates checker registration +
  env-kind support + non-empty cron.
* :func:`disable_schedule` — disables but leaves the row in
  place so cron history remains observable.
* :func:`run_now` — synchronous PENDING-row creation; the
  caller wires the Layer-5 dispatch in M2. Records the
  exactly-once tick ledger so a manual run inside a
  scheduled tick window does not double-fire.
* :func:`record_tick` — idempotent ledger insert keyed on
  ``(project, env, scheduled_for)`` with a
  :class:`DriftTickAlreadyRecordedError` on conflict.
* :func:`ingest_report` — stamps drift counts + diff digest +
  blob key on the run + emits REPORT_INGESTED + DRIFT_DETECTED
  when ``drift_count > 0``.
* :func:`get_drift_run` /
  :func:`list_drift_runs_for_environment`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.orchestration.infra.drift import (
    repository,
)
from ccai.pychestrate.webservice.orchestration.infra.drift.errors import (
    DriftCheckerUnknownError,
    DriftRunNotFoundError,
    DriftScheduleInvalidError,
    DriftScheduleNotFoundError,
    DriftTickAlreadyRecordedError,
)
from ccai.pychestrate.webservice.orchestration.infra.drift.events import (
    DriftEventTopics,
)
from ccai.pychestrate.webservice.orchestration.infra.drift.factories.checker_protocol import (
    DriftCheckerProtocol,
)
from ccai.pychestrate.webservice.orchestration.infra.drift.models import (
    DriftRun,
    DriftRunState,
    DriftSchedule,
    DriftTickLedger,
    DriftTriggerKind,
)
from ccai.pychestrate.webservice.orchestration.infra.environment import (
    repository as env_repository,
)


DRIFT_CHECKER_PROTOCOL: str = "drift_checker"
LIST_DRIFT_RUNS_DEFAULT_LIMIT: int = 50


@dataclass(frozen=True)
class DriftScheduleView:
    """
        Caller-facing schedule read-model.
    """
    project_id: str
    environment_id: str
    checker_name: str
    cron_expression: str
    enabled: bool
    updated_by: Optional[str]
    updated_at: datetime


@dataclass(frozen=True)
class DriftRunView:
    """
        Caller-facing drift-run read-model.
    """
    run_id: str
    project_id: str
    environment_id: str
    checker_name: str
    state: DriftRunState
    trigger_kind: DriftTriggerKind
    layer5_run_id: Optional[str]
    scheduled_for: datetime
    ran_at: Optional[datetime]
    drift_count: Optional[int]
    added: Optional[int]
    changed: Optional[int]
    destroyed: Optional[int]
    diff_digest_sha256: str
    report_blob_key: Optional[str]
    final_state_reason: str
    report_payload: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class DriftReport:
    """
        Caller-supplied ingest payload.

        :param drift_count: Total resources drifted.
        :param added: Count of resources added vs declared.
        :param changed: Count of resources changed vs declared.
        :param destroyed: Count of resources destroyed vs
                          declared.
        :param diff_digest_sha256: 64-char hex digest of the
                                   normalized diff.
        :param report_blob_key: Optional object-store key.
        :param payload: Free-form structured report consumed
                        by UIs.
    """
    drift_count: int
    added: int
    changed: int
    destroyed: int
    diff_digest_sha256: str = ""
    report_blob_key: Optional[str] = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DriftTickResult:
    """
        Outcome of :func:`record_tick`.
    """
    run_id: str
    is_new: bool


def set_schedule(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        checker_name: str,
        cron_expression: str,
        enabled: bool = True,
        actor_id: Optional[str] = None
    ) -> DriftScheduleView:
    """
        Upsert the per-environment drift schedule.

        :raises: DriftCheckerUnknownError when ``checker_name``
                 has no registered factory.
        :raises: DriftScheduleInvalidError on an empty
                 cron_expression or an environment kind not
                 supported by the checker.
    """
    if cron_expression is None or len(cron_expression) == 0:
        err_lines = ["cron_expression must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise DriftScheduleInvalidError(err_msg) from None

    checker_cls = _resolve_checker(checker_name=checker_name)
    env = env_repository.find_by_id(
        db_session=db_session, environment_id=environment_id,
    )
    if env is None:
        err_lines = ["Environment not found."]
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_msg = os.linesep.join(err_lines)
        raise DriftScheduleInvalidError(err_msg) from None

    if str(env.project_id) != project_id:
        err_lines = ["Environment project mismatch."]
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_lines.append("EXPECTED_PROJECT: {}".format(project_id))
        err_lines.append("ACTUAL_PROJECT: {}".format(env.project_id))
        err_msg = os.linesep.join(err_lines)
        raise DriftScheduleInvalidError(err_msg) from None

    supported = checker_cls.supported_environment_kinds()
    if env.kind_name not in supported:
        err_lines = ["Drift checker does not support env kind."]
        err_lines.append("CHECKER: {}".format(checker_name))
        err_lines.append("ENVIRONMENT_KIND: {}".format(env.kind_name))
        err_lines.append("SUPPORTED: {}".format(", ".join(supported)))
        err_msg = os.linesep.join(err_lines)
        raise DriftScheduleInvalidError(err_msg) from None

    now = utc_now()
    row = repository.upsert_schedule(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
        checker_name=checker_name,
        cron_expression=cron_expression,
        enabled=enabled,
        updated_by=actor_id,
        updated_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DriftEventTopics.SCHEDULE_SET,
            payload={
                "project_id": project_id,
                "environment_id": environment_id,
                "checker_name": checker_name,
                "cron_expression": cron_expression,
                "enabled": enabled,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _schedule_to_view(row=row)
    return rtnval


def disable_schedule(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        actor_id: Optional[str] = None
    ) -> DriftScheduleView:
    """
        Mark a schedule disabled. Idempotent on already-disabled
        rows.

        :raises: DriftScheduleNotFoundError on miss.
    """
    row = repository.find_schedule(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
    )
    if row is None:
        err_lines = ["Drift schedule not found."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_msg = os.linesep.join(err_lines)
        raise DriftScheduleNotFoundError(err_msg) from None

    if row.enabled is False:
        rtnval = _schedule_to_view(row=row)
        return rtnval

    now = utc_now()
    row.enabled = False
    row.updated_by = actor_id
    row.updated_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DriftEventTopics.SCHEDULE_DISABLED,
            payload={
                "project_id": project_id,
                "environment_id": environment_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _schedule_to_view(row=row)
    return rtnval


def get_schedule(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str
    ) -> DriftScheduleView:
    """
        Read a schedule.

        :raises: DriftScheduleNotFoundError on miss.
    """
    row = repository.find_schedule(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
    )
    if row is None:
        err_lines = ["Drift schedule not found."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_msg = os.linesep.join(err_lines)
        raise DriftScheduleNotFoundError(err_msg) from None
    rtnval = _schedule_to_view(row=row)
    return rtnval


def run_now(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        actor_id: Optional[str] = None
    ) -> DriftRunView:
    """
        Insert a PENDING DriftRun with ``trigger_kind=manual``
        and emit RUN_TRIGGERED. The Layer-5 dispatch handoff
        lands in M2.

        :raises: DriftScheduleNotFoundError when the env has no
                 schedule (M1 caller contract — a manual run
                 borrows the schedule's checker_name).
    """
    schedule = repository.find_schedule(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
    )
    if schedule is None:
        err_lines = ["No drift schedule for environment."]
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_msg = os.linesep.join(err_lines)
        raise DriftScheduleNotFoundError(err_msg) from None

    now = utc_now()
    row = repository.insert_drift_run(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
        checker_name=schedule.checker_name,
        trigger_kind=DriftTriggerKind.MANUAL,
        scheduled_for=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DriftEventTopics.RUN_TRIGGERED,
            payload={
                "run_id": str(row.run_id),
                "project_id": project_id,
                "environment_id": environment_id,
                "checker_name": schedule.checker_name,
                "trigger_kind": DriftTriggerKind.MANUAL.value,
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _run_to_view(row=row)
    return rtnval


def record_tick(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        scheduled_for: datetime
    ) -> DriftTickResult:
    """
        Idempotent tick ledger insert. The first call for a
        ``(project, env, scheduled_for)`` tuple inserts a
        PENDING DriftRun + ledger row and emits RUN_TRIGGERED.
        Subsequent calls raise
        :class:`DriftTickAlreadyRecordedError` so the cron
        worker can skip duplicates.

        :raises: DriftScheduleNotFoundError when the env has no
                 schedule.
        :raises: DriftScheduleInvalidError when the schedule is
                 disabled.
        :raises: DriftTickAlreadyRecordedError on duplicate.
    """
    schedule = repository.find_schedule(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
    )
    if schedule is None:
        err_lines = ["No drift schedule for environment."]
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_msg = os.linesep.join(err_lines)
        raise DriftScheduleNotFoundError(err_msg) from None
    if schedule.enabled is False:
        err_lines = ["Drift schedule is disabled."]
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_msg = os.linesep.join(err_lines)
        raise DriftScheduleInvalidError(err_msg) from None

    existing = repository.find_tick_ledger(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
        scheduled_for=scheduled_for,
    )
    if existing is not None:
        err_lines = ["Drift tick already recorded for this slot."]
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_lines.append("SCHEDULED_FOR: {}".format(scheduled_for.isoformat()))
        err_msg = os.linesep.join(err_lines)
        raise DriftTickAlreadyRecordedError(err_msg) from None

    now = utc_now()
    run = repository.insert_drift_run(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
        checker_name=schedule.checker_name,
        trigger_kind=DriftTriggerKind.SCHEDULE,
        scheduled_for=scheduled_for,
    )
    repository.insert_tick_ledger(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
        scheduled_for=scheduled_for,
        run_id=str(run.run_id),
        recorded_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DriftEventTopics.RUN_TRIGGERED,
            payload={
                "run_id": str(run.run_id),
                "project_id": project_id,
                "environment_id": environment_id,
                "checker_name": schedule.checker_name,
                "trigger_kind": DriftTriggerKind.SCHEDULE.value,
                "scheduled_for": scheduled_for.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = DriftTickResult(run_id=str(run.run_id), is_new=True)
    return rtnval


def ingest_report(
        *,
        db_session: DbSession,
        run_id: str,
        report: DriftReport,
        layer5_run_id: Optional[str] = None
    ) -> DriftRunView:
    """
        Stamp drift counts + diff digest + blob key on the run.
        Emits REPORT_INGESTED + DRIFT_DETECTED when
        ``drift_count > 0``.

        :raises: DriftRunNotFoundError on miss.
    """
    row = repository.find_run_by_id(db_session=db_session, run_id=run_id)
    if row is None:
        err_lines = ["Drift run not found."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise DriftRunNotFoundError(err_msg) from None

    now = utc_now()
    row.state = DriftRunState.COMPLETED
    row.layer5_run_id = layer5_run_id
    row.ran_at = now
    row.drift_count = report.drift_count
    row.added = report.added
    row.changed = report.changed
    row.destroyed = report.destroyed
    row.diff_digest_sha256 = report.diff_digest_sha256
    row.report_blob_key = report.report_blob_key
    row.report_payload = dict(report.payload or {})
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DriftEventTopics.REPORT_INGESTED,
            payload={
                "run_id": str(row.run_id),
                "project_id": str(row.project_id),
                "environment_id": str(row.environment_id),
                "drift_count": report.drift_count,
                "added": report.added,
                "changed": report.changed,
                "destroyed": report.destroyed,
                "diff_digest_sha256": report.diff_digest_sha256,
            },
            source_event_id=new_uuid(),
        ),
    )
    if report.drift_count > 0:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=DriftEventTopics.DRIFT_DETECTED,
                payload={
                    "run_id": str(row.run_id),
                    "project_id": str(row.project_id),
                    "environment_id": str(row.environment_id),
                    "drift_count": report.drift_count,
                    "added": report.added,
                    "changed": report.changed,
                    "destroyed": report.destroyed,
                },
                source_event_id=new_uuid(),
            ),
        )
    db_session.commit()
    rtnval = _run_to_view(row=row)
    return rtnval


def get_drift_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> DriftRunView:
    """
        Read a drift run by id.

        :raises: DriftRunNotFoundError on miss.
    """
    row = repository.find_run_by_id(db_session=db_session, run_id=run_id)
    if row is None:
        err_lines = ["Drift run not found."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise DriftRunNotFoundError(err_msg) from None
    rtnval = _run_to_view(row=row)
    return rtnval


def list_drift_runs_for_environment(
        *,
        db_session: DbSession,
        environment_id: str,
        limit: int = LIST_DRIFT_RUNS_DEFAULT_LIMIT
    ) -> List[DriftRunView]:
    """
        Recent drift runs for an environment, scheduled-for
        descending.
    """
    rows = repository.list_runs_for_environment(
        db_session=db_session, environment_id=environment_id, limit=limit,
    )
    rtnval = [_run_to_view(row=r) for r in rows]
    return rtnval


def _resolve_checker(*, checker_name: str) -> Type[DriftCheckerProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=DRIFT_CHECKER_PROTOCOL,
    )
    for impl in candidates:
        if impl.checker_name() == checker_name:
            return impl
    err_lines = ["No registered drift_checker for name."]
    err_lines.append("CHECKER_NAME: {}".format(checker_name))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.checker_name() for impl in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise DriftCheckerUnknownError(err_msg) from None


def _schedule_to_view(*, row: DriftSchedule) -> DriftScheduleView:
    rtnval = DriftScheduleView(
        project_id=str(row.project_id),
        environment_id=str(row.environment_id),
        checker_name=row.checker_name,
        cron_expression=row.cron_expression,
        enabled=row.enabled,
        updated_by=str(row.updated_by) if row.updated_by is not None else None,
        updated_at=row.updated_at,
    )
    return rtnval


def _run_to_view(*, row: DriftRun) -> DriftRunView:
    payload = None
    if row.report_payload is not None:
        payload = dict(row.report_payload)
    rtnval = DriftRunView(
        run_id=str(row.run_id),
        project_id=str(row.project_id),
        environment_id=str(row.environment_id),
        checker_name=row.checker_name,
        state=row.state,
        trigger_kind=row.trigger_kind,
        layer5_run_id=(
            str(row.layer5_run_id) if row.layer5_run_id is not None else None
        ),
        scheduled_for=row.scheduled_for,
        ran_at=row.ran_at,
        drift_count=row.drift_count,
        added=row.added,
        changed=row.changed,
        destroyed=row.destroyed,
        diff_digest_sha256=row.diff_digest_sha256,
        report_blob_key=row.report_blob_key,
        final_state_reason=row.final_state_reason,
        report_payload=payload,
    )
    return rtnval
