"""
.. module:: resources.health.service
    :synopsis: Health facade — seed / record outcome / read.

M1 ships the persistence + accounting surface only:

* :func:`seed_health_record` is called on
  ``entity.resource.registered`` (M2 wires the subscriber);
* :func:`record_probe_outcome` updates rolling counters,
  ``last_outcome`` and ``next_probe_at``;
* :func:`drop_health_record` is called on
  ``entity.resource.retired``.

State transitions through the inventory module land in M2 once
the :func:`record_probe_outcome` outcome enters the M2
quarantine / heal state machine.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.resources.health import repository
from ccai.pychestrate.webservice.resources.health.errors import (
    HealthRecordConflictError,
    HealthRecordNotFoundError,
)
from ccai.pychestrate.webservice.resources.health.events import (
    HealthEventTopics,
)
from ccai.pychestrate.webservice.resources.health.models import (
    ProbeOutcome,
    ResourceHealth,
)


DEFAULT_PROBE_NAME: str = "device-ping"
DEFAULT_PROBE_PERIOD_SECONDS: int = 60
LIST_DUE_DEFAULT_LIMIT: int = 256


@dataclass(frozen=True)
class ProbeResult:
    """
        Outcome of one probe execution. M1 only consumes the
        ``outcome`` enum + the optional ``error`` /
        ``payload``; the M2 quarantine state machine adds a
        ``severity`` field.
    """
    outcome: ProbeOutcome
    error: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class HealthView:
    """
        Caller-facing read-model.
    """
    health_id: str
    resource_id: str
    project_id: str
    probe_name: str
    probe_period_seconds: int
    last_outcome: ProbeOutcome
    last_probe_at: Optional[datetime]
    last_pass_at: Optional[datetime]
    last_fail_at: Optional[datetime]
    next_probe_at: datetime
    pass_count: int
    fail_count: int
    consecutive_failures: int
    last_error: Optional[str]
    last_payload: Dict[str, Any] = field(default_factory=dict)


def seed_health_record(
        *,
        db_session: DbSession,
        resource_id: str,
        project_id: str,
        probe_name: str = DEFAULT_PROBE_NAME,
        probe_period_seconds: int = DEFAULT_PROBE_PERIOD_SECONDS
    ) -> HealthView:
    """
        Create the per-resource health row. Idempotent on a
        previously seeded resource — the existing view is
        returned with the current probe configuration intact.

        :raises: HealthRecordConflictError when the existing row
                 already declares a different ``probe_name``.
    """
    existing = repository.find_by_resource(
        db_session=db_session, resource_id=resource_id,
    )
    if existing is not None:
        if existing.probe_name != probe_name:
            err_lines = ["Health record already seeded with a different probe."]
            err_lines.append("RESOURCE_ID: {}".format(resource_id))
            err_lines.append("EXISTING_PROBE: {}".format(existing.probe_name))
            err_lines.append("REQUESTED_PROBE: {}".format(probe_name))
            err_msg = os.linesep.join(err_lines)
            raise HealthRecordConflictError(err_msg) from None
        rtnval = _to_view(row=existing)
        return rtnval

    now = utc_now()
    next_probe_at = now + timedelta(seconds=probe_period_seconds)
    row = repository.insert_health_record(
        db_session=db_session,
        resource_id=resource_id,
        project_id=project_id,
        probe_name=probe_name,
        probe_period_seconds=probe_period_seconds,
        next_probe_at=next_probe_at,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=HealthEventTopics.SEEDED,
            payload={
                "health_id": str(row.health_id),
                "resource_id": resource_id,
                "project_id": project_id,
                "probe_name": probe_name,
                "probe_period_seconds": probe_period_seconds,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def record_probe_outcome(
        *,
        db_session: DbSession,
        resource_id: str,
        result: ProbeResult
    ) -> HealthView:
    """
        Apply the outcome of a probe execution to the rolling
        counters, schedule the next probe, and emit
        :data:`HealthEventTopics.PROBED`.

        ``next_probe_at`` advances by ``probe_period_seconds``;
        the M2 exponential-backoff multiplier and the M2
        quarantine state-machine extend this method without
        breaking the M1 caller contract.

        :raises: HealthRecordNotFoundError when the resource was
                 never seeded.
    """
    row = repository.find_by_resource(
        db_session=db_session, resource_id=resource_id,
    )
    if row is None:
        err_lines = ["No health record for resource."]
        err_lines.append("RESOURCE_ID: {}".format(resource_id))
        err_msg = os.linesep.join(err_lines)
        raise HealthRecordNotFoundError(err_msg) from None

    now = utc_now()
    row.last_outcome = result.outcome
    row.last_probe_at = now
    row.last_payload = dict(result.payload or {})
    row.last_error = result.error

    if result.outcome == ProbeOutcome.PASS:
        row.pass_count = row.pass_count + 1
        row.consecutive_failures = 0
        row.last_pass_at = now
    elif result.outcome == ProbeOutcome.FAIL:
        row.fail_count = row.fail_count + 1
        row.consecutive_failures = row.consecutive_failures + 1
        row.last_fail_at = now
    else:
        # UNKNOWN — counters untouched, but next_probe_at still advances.
        pass

    row.next_probe_at = now + timedelta(seconds=row.probe_period_seconds)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=HealthEventTopics.PROBED,
            payload={
                "health_id": str(row.health_id),
                "resource_id": resource_id,
                "outcome": result.outcome.value,
                "consecutive_failures": row.consecutive_failures,
                "next_probe_at": row.next_probe_at.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def get_health_record(
        *,
        db_session: DbSession,
        resource_id: str
    ) -> HealthView:
    """
        Read a record by resource id.

        :raises: HealthRecordNotFoundError on miss.
    """
    row = repository.find_by_resource(
        db_session=db_session, resource_id=resource_id,
    )
    if row is None:
        err_lines = ["No health record for resource."]
        err_lines.append("RESOURCE_ID: {}".format(resource_id))
        err_msg = os.linesep.join(err_lines)
        raise HealthRecordNotFoundError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def list_due_for_probe(
        *,
        db_session: DbSession,
        when: Optional[datetime] = None,
        limit: int = LIST_DUE_DEFAULT_LIMIT
    ) -> List[HealthView]:
    """
        Return the records whose ``next_probe_at <= when``,
        ordered by ``next_probe_at`` ascending. ``limit`` caps
        the result size for the M2 dispatcher's bounded-batch
        behavior.
    """
    cutoff = when if when is not None else utc_now()
    rows = repository.list_due_for_probe(
        db_session=db_session, when=cutoff, limit=limit,
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def drop_health_record(
        *,
        db_session: DbSession,
        resource_id: str
    ) -> None:
    """
        Remove the health record for a resource. Idempotent on a
        missing row. Emits
        :data:`HealthEventTopics.DROPPED` when a row is actually
        deleted.
    """
    row = repository.find_by_resource(
        db_session=db_session, resource_id=resource_id,
    )
    if row is None:
        return

    repository.delete_health_record(db_session=db_session, row=row)
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=HealthEventTopics.DROPPED,
            payload={
                "resource_id": resource_id,
                "probe_name": row.probe_name,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def _to_view(*, row: ResourceHealth) -> HealthView:
    rtnval = HealthView(
        health_id=str(row.health_id),
        resource_id=str(row.resource_id),
        project_id=str(row.project_id),
        probe_name=row.probe_name,
        probe_period_seconds=row.probe_period_seconds,
        last_outcome=row.last_outcome,
        last_probe_at=row.last_probe_at,
        last_pass_at=row.last_pass_at,
        last_fail_at=row.last_fail_at,
        next_probe_at=row.next_probe_at,
        pass_count=row.pass_count,
        fail_count=row.fail_count,
        consecutive_failures=row.consecutive_failures,
        last_error=row.last_error,
        last_payload=dict(row.last_payload or {}),
    )
    return rtnval
