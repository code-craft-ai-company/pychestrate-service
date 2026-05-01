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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.workers.exceptions import (
    WorkerAlreadyRegisteredError,
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
