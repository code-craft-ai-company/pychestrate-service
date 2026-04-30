"""
.. module:: workers.jobservice
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Service layer for the worker-job queue.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading
import time

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.workers.jobmodels import (
    JobState,
    WorkerJob,
)
from automojo.pychestrate.webservice.workers.models import (
    Worker,
    WorkerKind,
    WorkerStatus,
)


_WAIT_LOCK = threading.Lock()
_WAIT_EVENTS: Dict[str, threading.Event] = {}


@dataclass(frozen=True)
class JobView:
    """
        Caller-facing snapshot of a :class:`WorkerJob` row.
    """
    job_id: str
    kind: str
    payload: Dict[str, Any]
    target_pod_name: Optional[str]
    target_kind: Optional[str]
    worker_id: Optional[str]
    state: str
    enqueued_at: str
    claimed_at: Optional[str]
    completed_at: Optional[str]
    result_code: Optional[int]
    stdout: str
    stderr: str
    error_text: Optional[str]


def _to_view(*, row: WorkerJob) -> JobView:
    if row.payload is not None:
        payload = dict(row.payload)
    else:
        payload = {}
    if row.worker_id is not None:
        worker_field: Optional[str] = str(row.worker_id)
    else:
        worker_field = None
    if row.claimed_at is not None:
        claimed_field: Optional[str] = row.claimed_at.isoformat()
    else:
        claimed_field = None
    if row.completed_at is not None:
        completed_field: Optional[str] = row.completed_at.isoformat()
    else:
        completed_field = None
    rtnval = JobView(
        job_id=str(row.job_id),
        kind=row.kind,
        payload=payload,
        target_pod_name=row.target_pod_name,
        target_kind=row.target_kind,
        worker_id=worker_field,
        state=row.state,
        enqueued_at=row.enqueued_at.isoformat(),
        claimed_at=claimed_field,
        completed_at=completed_field,
        result_code=row.result_code,
        stdout=row.stdout if row.stdout else "",
        stderr=row.stderr if row.stderr else "",
        error_text=row.error_text,
    )
    return rtnval


def enqueue_job(
        *,
        db_session: DbSession,
        kind: str = "run-command",
        payload: Optional[Dict[str, Any]] = None,
        target_pod_name: Optional[str] = None,
        target_kind: Optional[WorkerKind] = None,
    ) -> JobView:
    """
        Insert a :class:`WorkerJob` row in PENDING state.
    """
    if payload is None:
        payload_value: Dict[str, Any] = {}
    else:
        payload_value = dict(payload)
    if target_kind is not None:
        target_kind_value: Optional[str] = target_kind.value
    else:
        target_kind_value = None
    row = WorkerJob(
        job_id=new_uuid(),
        kind=kind,
        payload=payload_value,
        target_pod_name=target_pod_name,
        target_kind=target_kind_value,
        worker_id=None,
        state=JobState.PENDING.value,
        enqueued_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def claim_next_job(
        *,
        db_session: DbSession,
        worker_id: str,
    ) -> Optional[JobView]:
    """
        Pick the oldest PENDING row that matches the worker's
        ``pod_name`` / ``kind`` selectors and atomically flip it to
        CLAIMED. Returns ``None`` when there's nothing to do.
    """
    worker = (
        db_session.query(Worker)
        .filter(Worker.worker_id == worker_id)
        .first()
    )
    if worker is None:
        return None

    candidates = (
        db_session.query(WorkerJob)
        .filter(WorkerJob.state == JobState.PENDING.value)
        .order_by(WorkerJob.enqueued_at.asc())
        .all()
    )
    matched: Optional[WorkerJob] = None
    for candidate in candidates:
        if candidate.target_pod_name is not None:
            if candidate.target_pod_name != worker.name:
                if candidate.target_pod_name != worker.attributes.get(
                    "pod_name",
                ):
                    continue
        if candidate.target_kind is not None:
            if candidate.target_kind != worker.kind:
                continue
        matched = candidate
        break

    if matched is None:
        return None

    matched.worker_id = worker.worker_id
    matched.state = JobState.CLAIMED.value
    matched.claimed_at = datetime.now(timezone.utc)
    db_session.commit()
    rtnval = _to_view(row=matched)
    return rtnval


def report_result(
        *,
        db_session: DbSession,
        worker_id: str,
        job_id: str,
        result_code: int,
        stdout: str = "",
        stderr: str = "",
        error_text: Optional[str] = None,
    ) -> JobView:
    """
        Worker reports a job's terminal outcome.
    """
    row = (
        db_session.query(WorkerJob)
        .filter(WorkerJob.job_id == job_id)
        .first()
    )
    if row is None:
        err_lines = [
            "Worker job not found.",
            "JOB_ID: {}".format(job_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise LookupError(err_msg)
    row.result_code = int(result_code)
    row.stdout = stdout if stdout is not None else ""
    row.stderr = stderr if stderr is not None else ""
    row.error_text = error_text
    row.completed_at = datetime.now(timezone.utc)
    if error_text is not None:
        row.state = JobState.FAILED.value
    elif int(result_code) == 0:
        row.state = JobState.SUCCEEDED.value
    else:
        row.state = JobState.FAILED.value
    db_session.commit()

    # Wake any waiter blocked on this job.
    with _WAIT_LOCK:
        event = _WAIT_EVENTS.pop(str(row.job_id), None)
    if event is not None:
        event.set()

    rtnval = _to_view(row=row)
    return rtnval


def read_job(
        *,
        db_session: DbSession,
        job_id: str,
    ) -> Optional[JobView]:
    """
        Read one job by id.
    """
    row = (
        db_session.query(WorkerJob)
        .filter(WorkerJob.job_id == job_id)
        .first()
    )
    if row is None:
        return None
    rtnval = _to_view(row=row)
    return rtnval


def wait_for_completion(
        *,
        session_factory,
        job_id: str,
        timeout_seconds: float,
        poll_interval_seconds: float = 0.1,
    ) -> Optional[JobView]:
    """
        Block (with a thread.Event + DB poll fallback) until the job
        reaches a terminal state or ``timeout_seconds`` elapses.

        :param session_factory: Zero-arg callable returning a fresh
                                ``DbSession``. The waiter opens its
                                own session per poll iteration so it
                                doesn't share with the worker
                                thread.
        :returns: The terminal :class:`JobView`, or ``None`` on
                  timeout.
    """
    event = threading.Event()
    with _WAIT_LOCK:
        _WAIT_EVENTS[job_id] = event

    deadline = time.time() + timeout_seconds
    try:
        while time.time() < deadline:
            db_session = session_factory()
            try:
                view = read_job(db_session=db_session, job_id=job_id)
            finally:
                db_session.close()
            if view is None:
                return None
            if view.state in (JobState.SUCCEEDED.value, JobState.FAILED.value):
                return view
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            event.wait(min(poll_interval_seconds, remaining))
            event.clear()
    finally:
        with _WAIT_LOCK:
            _WAIT_EVENTS.pop(job_id, None)

    db_session = session_factory()
    try:
        rtnval = read_job(db_session=db_session, job_id=job_id)
    finally:
        db_session.close()
    return rtnval
