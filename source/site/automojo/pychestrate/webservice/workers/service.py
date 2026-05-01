"""
.. module:: workers.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Service-layer operations for the worker registry.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.workers.exceptions import (
    WorkerAlreadyRegisteredError,
    WorkerBusyError,
    WorkerNotFoundError,
    WorkerStateTransitionError,
)
from automojo.pychestrate.webservice.workers.models import (
    Worker,
    WorkerKind,
    WorkerStatus,
)


@dataclass(frozen=True)
class WorkerView:
    """
        Caller-facing snapshot of a :class:`Worker` row.
    """
    worker_id: str
    name: str
    kind: str
    project_id: Optional[str]
    client_id: Optional[str]
    status: str
    registered_at: str
    last_heartbeat_at: Optional[str]
    attributes: Dict[str, Any]
    lease_holder: Optional[str] = None
    lease_acquired_at: Optional[str] = None
    lease_expires_at: Optional[str] = None


def _to_view(*, row: Worker) -> WorkerView:
    if row.project_id is not None:
        project_field: Optional[str] = str(row.project_id)
    else:
        project_field = None
    if row.client_id is not None:
        client_field: Optional[str] = str(row.client_id)
    else:
        client_field = None
    if row.last_heartbeat_at is not None:
        heartbeat_field: Optional[str] = row.last_heartbeat_at.isoformat()
    else:
        heartbeat_field = None
    if row.attributes is not None:
        attrs = dict(row.attributes)
    else:
        attrs = {}
    if row.lease_acquired_at is not None:
        lease_acquired_field: Optional[str] = (
            row.lease_acquired_at.isoformat()
        )
    else:
        lease_acquired_field = None
    if row.lease_expires_at is not None:
        lease_expires_field: Optional[str] = (
            row.lease_expires_at.isoformat()
        )
    else:
        lease_expires_field = None
    rtnval = WorkerView(
        worker_id=str(row.worker_id),
        name=row.name,
        kind=row.kind,
        project_id=project_field,
        client_id=client_field,
        status=row.status,
        registered_at=row.registered_at.isoformat(),
        last_heartbeat_at=heartbeat_field,
        attributes=attrs,
        lease_holder=row.lease_holder,
        lease_acquired_at=lease_acquired_field,
        lease_expires_at=lease_expires_field,
    )
    return rtnval


def register_worker(
        *,
        db_session: DbSession,
        name: str,
        kind: WorkerKind,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> WorkerView:
    """
        Insert a :class:`Worker` row.

        :raises WorkerAlreadyRegisteredError: When (project_id, name)
                already exists.
    """
    now = datetime.now(timezone.utc)
    if attributes is None:
        attributes_value: Dict[str, Any] = {}
    else:
        attributes_value = dict(attributes)
    row = Worker(
        worker_id=new_uuid(),
        name=name,
        kind=kind.value,
        project_id=project_id,
        client_id=client_id,
        status=WorkerStatus.IDLE.value,
        registered_at=now,
        last_heartbeat_at=now,
        attributes=attributes_value,
    )
    db_session.add(row)
    try:
        db_session.commit()
    except IntegrityError as exc:
        db_session.rollback()
        err_lines = [
            "Worker name already registered for this project scope.",
            "PROJECT_ID: {}".format(project_id),
            "NAME: {}".format(name),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerAlreadyRegisteredError(err_msg) from exc
    rtnval = _to_view(row=row)
    return rtnval


def heartbeat_worker(
        *,
        db_session: DbSession,
        worker_id: str,
        status: Optional[WorkerStatus] = None,
    ) -> WorkerView:
    """
        Stamp ``last_heartbeat_at`` and optionally update status.

        :raises WorkerNotFoundError: When ``worker_id`` is unknown.
        :raises WorkerStateTransitionError: When the worker is in
                DRAINING and the caller tries to flip back to IDLE
                or RUNNING.
    """
    row = (
        db_session.query(Worker)
        .filter(Worker.worker_id == worker_id)
        .first()
    )
    if row is None:
        err_lines = [
            "Worker not registered.",
            "WORKER_ID: {}".format(worker_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerNotFoundError(err_msg) from None

    if status is not None:
        if row.status == WorkerStatus.DRAINING.value:
            if status != WorkerStatus.OFFLINE:
                err_lines = [
                    "Worker is draining; only OFFLINE is allowed.",
                    "WORKER_ID: {}".format(worker_id),
                    "REQUESTED: {}".format(status.value),
                ]
                err_msg = os.linesep.join(err_lines)
                raise WorkerStateTransitionError(err_msg) from None
        row.status = status.value

    row.last_heartbeat_at = datetime.now(timezone.utc)
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def drain_worker(
        *,
        db_session: DbSession,
        worker_id: str,
    ) -> WorkerView:
    """
        Mark the worker as DRAINING. The worker exits its loop after
        completing the current job.
    """
    row = (
        db_session.query(Worker)
        .filter(Worker.worker_id == worker_id)
        .first()
    )
    if row is None:
        err_lines = [
            "Worker not registered.",
            "WORKER_ID: {}".format(worker_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerNotFoundError(err_msg) from None
    row.status = WorkerStatus.DRAINING.value
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def deregister_worker(
        *,
        db_session: DbSession,
        worker_id: str,
    ) -> None:
    """
        Remove a worker row outright.
    """
    row = (
        db_session.query(Worker)
        .filter(Worker.worker_id == worker_id)
        .first()
    )
    if row is None:
        err_lines = [
            "Worker not registered.",
            "WORKER_ID: {}".format(worker_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerNotFoundError(err_msg) from None
    db_session.delete(row)
    db_session.commit()
    return


def list_workers(
        *,
        db_session: DbSession,
        kind: Optional[WorkerKind] = None,
        status: Optional[WorkerStatus] = None,
        project_id: Optional[str] = None,
    ) -> List[WorkerView]:
    """
        Return every worker matching the optional filters.
    """
    query = db_session.query(Worker)
    if kind is not None:
        query = query.filter(Worker.kind == kind.value)
    if status is not None:
        query = query.filter(Worker.status == status.value)
    if project_id is not None:
        query = query.filter(Worker.project_id == project_id)
    rows = query.order_by(Worker.registered_at.desc()).all()
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def read_worker(
        *,
        db_session: DbSession,
        worker_id: str,
    ) -> WorkerView:
    """
        Read one worker by id.
    """
    row = (
        db_session.query(Worker)
        .filter(Worker.worker_id == worker_id)
        .first()
    )
    if row is None:
        err_lines = [
            "Worker not registered.",
            "WORKER_ID: {}".format(worker_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerNotFoundError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def count_workers_by_status(
        *,
        db_session: DbSession,
    ) -> Dict[str, int]:
    """
        Count :class:`Worker` rows grouped by status. Every
        :class:`WorkerStatus` member appears in the result with
        at least ``0`` so the dashboard layer doesn't have to
        special-case empty buckets.
    """
    from sqlalchemy import func as sa_func
    rows = (
        db_session.query(Worker.status, sa_func.count().label("count"))
        .group_by(Worker.status)
        .all()
    )
    counts: Dict[str, int] = {}
    for member in WorkerStatus:
        counts[member.value] = 0
    for status_value, count_value in rows:
        counts[status_value] = int(count_value)
    rtnval = counts
    return rtnval


def _coerce_utc(*, value: datetime) -> datetime:
    """
        Attach UTC tzinfo to a naive datetime — SQLite drops tz
        on round-trip even when ``DateTime(timezone=True)`` is
        declared.
    """
    if value.tzinfo is not None:
        return value
    rtnval = value.replace(tzinfo=timezone.utc)
    return rtnval


def _try_audit_lease_event(
        *,
        db_session: DbSession,
        kind: str,
        worker_id: str,
        holder: str,
        ttl_seconds: Optional[int],
    ) -> None:
    """
        Best-effort capture of a lease-lifecycle event into the
        canonical audit chain. Mirrors the queue-service helper
        of the same shape — failures are swallowed so the lease
        write stays committed even when audit is degraded.
    """
    try:
        from automojo.pychestrate.webservice.audit import (
            audit_writer,
        )
    except Exception:
        return
    payload: Dict[str, Any] = {
        "worker_id": worker_id,
        "holder": holder,
    }
    if ttl_seconds is not None:
        payload["ttl_seconds"] = int(ttl_seconds)
    try:
        audit_writer.capture_event(
            db_session=db_session,
            source_event_id=new_uuid(),
            source_topic=kind.replace("audit.", "entity.", 1),
            kind=kind,
            actor_user_id=None,
            actor_service_identity=None,
            target_ref="worker:{0}".format(worker_id),
            payload=payload,
        )
        db_session.commit()
    except Exception:
        try:
            db_session.rollback()
        except Exception:
            pass
        return
    return


def is_lease_active(
        *,
        worker_row: Worker,
        now: Optional[datetime] = None,
    ) -> bool:
    """
        Return ``True`` when the worker currently holds a
        non-expired lease.
    """
    if worker_row.lease_holder is None:
        return False
    if worker_row.lease_expires_at is None:
        return True
    if now is None:
        now_value = datetime.now(timezone.utc)
    else:
        now_value = now
    expires = _coerce_utc(value=worker_row.lease_expires_at)
    rtnval = now_value < expires
    return rtnval


def acquire_lease(
        *,
        db_session: DbSession,
        worker_id: str,
        holder: str,
        ttl_seconds: int,
        now: Optional[datetime] = None,
    ) -> WorkerView:
    """
        Acquire (or extend) the lease on ``worker_id`` for
        ``holder``.

        :raises WorkerNotFoundError: When ``worker_id`` is unknown.
        :raises WorkerBusyError: When the worker currently holds an
                                 unexpired lease for a *different*
                                 holder.
        :returns: The updated :class:`WorkerView`.
    """
    if holder is None or len(holder) == 0:
        err_lines = [
            "Lease holder is required.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if ttl_seconds <= 0:
        err_lines = [
            "ttl_seconds must be > 0.",
            "REQUESTED: {}".format(ttl_seconds),
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    row = (
        db_session.query(Worker)
        .filter(Worker.worker_id == worker_id)
        .first()
    )
    if row is None:
        err_lines = [
            "Worker not registered.",
            "WORKER_ID: {}".format(worker_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerNotFoundError(err_msg) from None
    if now is None:
        now_value = datetime.now(timezone.utc)
    else:
        now_value = now
    if is_lease_active(worker_row=row, now=now_value) is True:
        if row.lease_holder != holder:
            err_lines = [
                "Worker already leased to a different holder.",
                "WORKER_ID: {}".format(worker_id),
                "HELD_BY: {}".format(row.lease_holder),
                "REQUESTED_BY: {}".format(holder),
            ]
            err_msg = os.linesep.join(err_lines)
            raise WorkerBusyError(err_msg) from None
    row.lease_holder = holder
    if row.lease_acquired_at is None or row.lease_holder != holder:
        row.lease_acquired_at = now_value
    elif not is_lease_active(worker_row=row, now=now_value):
        row.lease_acquired_at = now_value
    row.lease_expires_at = now_value + timedelta(seconds=int(ttl_seconds))
    db_session.commit()
    _try_audit_lease_event(
        db_session=db_session,
        kind="audit.queue.lease.acquired",
        worker_id=str(row.worker_id),
        holder=holder,
        ttl_seconds=int(ttl_seconds),
    )
    rtnval = _to_view(row=row)
    return rtnval


def release_lease(
        *,
        db_session: DbSession,
        worker_id: str,
        holder: str,
    ) -> WorkerView:
    """
        Release a lease on ``worker_id``. A no-op when the lease
        is already absent OR held by a different holder (release
        is intentionally permissive — the caller has either
        already given up or never held the lease).
    """
    row = (
        db_session.query(Worker)
        .filter(Worker.worker_id == worker_id)
        .first()
    )
    if row is None:
        err_lines = [
            "Worker not registered.",
            "WORKER_ID: {}".format(worker_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerNotFoundError(err_msg) from None
    if row.lease_holder is not None and row.lease_holder == holder:
        row.lease_holder = None
        row.lease_acquired_at = None
        row.lease_expires_at = None
        db_session.commit()
        _try_audit_lease_event(
            db_session=db_session,
            kind="audit.queue.lease.released",
            worker_id=str(row.worker_id),
            holder=holder,
            ttl_seconds=None,
        )
    rtnval = _to_view(row=row)
    return rtnval


def release_all_leases_for_holder(
        *,
        db_session: DbSession,
        holder: str,
    ) -> List[str]:
    """
        Release every lease this ``holder`` currently has across
        the registry. Used by :class:`FlowRuntime` to clean up on
        flow exit so a crashed flow doesn't leave hardware
        reserved indefinitely.

        :returns: List of worker_ids that had a lease cleared.
    """
    if holder is None or len(holder) == 0:
        return []
    rows = (
        db_session.query(Worker)
        .filter(Worker.lease_holder == holder)
        .all()
    )
    cleared: List[str] = []
    for row in rows:
        row.lease_holder = None
        row.lease_acquired_at = None
        row.lease_expires_at = None
        cleared.append(str(row.worker_id))
    if len(cleared) > 0:
        db_session.commit()
    rtnval = cleared
    return rtnval


def expire_stale_leases(
        *,
        db_session: DbSession,
        now: Optional[datetime] = None,
    ) -> List[str]:
    """
        Clear lease fields on workers whose ``lease_expires_at``
        has passed. Returns the list of worker_ids that were
        cleared. Idempotent — running it twice in a row clears
        nothing the second time.
    """
    if now is None:
        now_value = datetime.now(timezone.utc)
    else:
        now_value = now
    rows = (
        db_session.query(Worker)
        .filter(Worker.lease_holder.isnot(None))
        .filter(Worker.lease_expires_at.isnot(None))
        .all()
    )
    cleared: List[str] = []
    for row in rows:
        expires = _coerce_utc(value=row.lease_expires_at)
        if expires <= now_value:
            row.lease_holder = None
            row.lease_acquired_at = None
            row.lease_expires_at = None
            cleared.append(str(row.worker_id))
    if len(cleared) > 0:
        db_session.commit()
    rtnval = cleared
    return rtnval
