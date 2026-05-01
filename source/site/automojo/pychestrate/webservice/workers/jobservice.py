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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.workers.jobmodels import (
    JobState,
    RetryStrategy,
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
    attempt: int
    max_attempts: int
    retry_delay_seconds: float
    retry_strategy: str
    not_before: Optional[str]


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
    if row.not_before is not None:
        not_before_field: Optional[str] = row.not_before.isoformat()
    else:
        not_before_field = None
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
        attempt=int(row.attempt) if row.attempt is not None else 1,
        max_attempts=(
            int(row.max_attempts) if row.max_attempts is not None else 1
        ),
        retry_delay_seconds=(
            float(row.retry_delay_seconds)
            if row.retry_delay_seconds is not None else 0.0
        ),
        retry_strategy=(
            row.retry_strategy
            if row.retry_strategy is not None else RetryStrategy.FIXED.value
        ),
        not_before=not_before_field,
    )
    return rtnval


def _coerce_retry_strategy(
        *,
        value: Optional[Any],
    ) -> str:
    """
        Normalise an incoming retry-strategy parameter to the
        canonical string value, defaulting to ``"fixed"`` when
        the input is unrecognised.
    """
    if value is None:
        rtnval = RetryStrategy.FIXED.value
        return rtnval
    if isinstance(value, RetryStrategy):
        rtnval = value.value
        return rtnval
    raw = str(value)
    try:
        rtnval = RetryStrategy(raw).value
    except ValueError:
        rtnval = RetryStrategy.FIXED.value
    return rtnval


def compute_next_retry_at(
        *,
        attempt_just_finished: int,
        retry_delay_seconds: float,
        retry_strategy: str,
        now: Optional[datetime] = None,
    ) -> Optional[datetime]:
    """
        Compute when the next retry of a failed job is allowed
        to be claimed.

        :param attempt_just_finished: 1-indexed attempt number
                                      that just failed (so the
                                      next attempt is
                                      ``attempt_just_finished +
                                      1``).
        :param retry_delay_seconds: Base delay.
        :param retry_strategy: ``"fixed"`` or ``"exponential"``.
        :param now: Optional clock override; defaults to
                    ``datetime.now(timezone.utc)``.

        :returns: ``not_before`` timestamp for the next attempt,
                  or ``None`` when ``retry_delay_seconds <= 0``
                  (claim immediately).
    """
    if retry_delay_seconds <= 0.0:
        return None
    if now is None:
        now_value = datetime.now(timezone.utc)
    else:
        now_value = now
    if retry_strategy == RetryStrategy.EXPONENTIAL.value:
        # attempt_just_finished is 1-indexed; the next retry's
        # backoff is base * 2**(attempt_just_finished - 1) so
        # the first retry waits ``base``, the second waits
        # ``2 * base``, the third ``4 * base``, etc.
        multiplier = 2 ** max(0, attempt_just_finished - 1)
        delay = retry_delay_seconds * multiplier
    else:
        delay = retry_delay_seconds
    rtnval = now_value + timedelta(seconds=delay)
    return rtnval


def enqueue_job(
        *,
        db_session: DbSession,
        kind: str = "run-command",
        payload: Optional[Dict[str, Any]] = None,
        target_pod_name: Optional[str] = None,
        target_kind: Optional[WorkerKind] = None,
        max_attempts: int = 1,
        retry_delay_seconds: float = 0.0,
        retry_strategy: Optional[Any] = None,
    ) -> JobView:
    """
        Insert a :class:`WorkerJob` row in PENDING state.

        :param max_attempts: How many attempts the queue is
                             allowed to schedule. ``1`` (the
                             default) means no retries on
                             failure.
        :param retry_delay_seconds: Base backoff between
                                    attempts. ``0`` means retry
                                    immediately.
        :param retry_strategy: ``"fixed"`` (default) or
                               ``"exponential"``.
    """
    if payload is None:
        payload_value: Dict[str, Any] = {}
    else:
        payload_value = dict(payload)
    if target_kind is not None:
        target_kind_value: Optional[str] = target_kind.value
    else:
        target_kind_value = None
    if max_attempts < 1:
        err_lines = [
            "max_attempts must be >= 1.",
            "REQUESTED: {}".format(max_attempts),
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg)
    if retry_delay_seconds < 0.0:
        err_lines = [
            "retry_delay_seconds must be >= 0.",
            "REQUESTED: {}".format(retry_delay_seconds),
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg)
    strategy_value = _coerce_retry_strategy(value=retry_strategy)
    row = WorkerJob(
        job_id=new_uuid(),
        kind=kind,
        payload=payload_value,
        target_pod_name=target_pod_name,
        target_kind=target_kind_value,
        worker_id=None,
        state=JobState.PENDING.value,
        enqueued_at=datetime.now(timezone.utc),
        attempt=1,
        max_attempts=int(max_attempts),
        retry_delay_seconds=float(retry_delay_seconds),
        retry_strategy=strategy_value,
        not_before=None,
    )
    db_session.add(row)
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def _coerce_utc(*, value: datetime) -> datetime:
    """
        Attach UTC tzinfo to a naive ``datetime``. SQLite drops
        tz on round-trip even when ``DateTime(timezone=True)`` is
        declared; we always store UTC, so the coercion is
        unambiguous.
    """
    if value.tzinfo is not None:
        return value
    rtnval = value.replace(tzinfo=timezone.utc)
    return rtnval


def claim_next_job(
        *,
        db_session: DbSession,
        worker_id: str,
    ) -> Optional[JobView]:
    """
        Pick the oldest PENDING row that matches the worker's
        ``pod_name`` / ``kind`` selectors, has either no
        ``not_before`` set or a ``not_before`` already in the
        past, and atomically flip it to CLAIMED. Returns
        ``None`` when there's nothing to do.
    """
    worker = (
        db_session.query(Worker)
        .filter(Worker.worker_id == worker_id)
        .first()
    )
    if worker is None:
        return None

    now_value = datetime.now(timezone.utc)
    candidates = (
        db_session.query(WorkerJob)
        .filter(WorkerJob.state == JobState.PENDING.value)
        .order_by(WorkerJob.enqueued_at.asc())
        .all()
    )
    matched: Optional[WorkerJob] = None
    for candidate in candidates:
        # Retry backoff window — skip rows whose not_before is in
        # the future.
        if candidate.not_before is not None:
            window = _coerce_utc(value=candidate.not_before)
            if now_value < window:
                continue
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
    matched.claimed_at = now_value
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
        Worker reports a job's outcome.

        When the outcome is a failure (non-zero ``result_code``
        or non-None ``error_text``) AND
        ``row.attempt < row.max_attempts``, the row is
        re-enqueued for another attempt: ``state`` returns to
        PENDING, ``attempt`` is bumped, ``worker_id`` /
        ``claimed_at`` / ``completed_at`` are cleared, the prior
        attempt's stdout / stderr / error_text are wiped (they
        are best-effort logged at the caller before this call
        runs), and ``not_before`` is set to honour the configured
        backoff. The waiter is NOT woken on retry — the job is
        not yet terminal — so ``wait_for_completion`` keeps
        blocking through the retry window.
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

    is_failure = (
        error_text is not None or int(result_code) != 0
    )
    has_retries_left = (
        is_failure is True and row.attempt < row.max_attempts
    )

    now_value = datetime.now(timezone.utc)
    if has_retries_left is True:
        # Re-enqueue under the configured backoff. Retain
        # max_attempts / retry_delay_seconds / retry_strategy /
        # target_* as-is; reset attempt-specific fields.
        row.attempt = int(row.attempt) + 1
        row.state = JobState.PENDING.value
        row.worker_id = None
        row.claimed_at = None
        row.completed_at = None
        row.result_code = None
        row.stdout = ""
        row.stderr = ""
        row.error_text = None
        row.not_before = compute_next_retry_at(
            attempt_just_finished=int(row.attempt) - 1,
            retry_delay_seconds=float(row.retry_delay_seconds or 0.0),
            retry_strategy=(
                row.retry_strategy or RetryStrategy.FIXED.value
            ),
            now=now_value,
        )
        db_session.commit()
        rtnval = _to_view(row=row)
        return rtnval

    # Terminal — write the outcome and wake any waiter.
    row.result_code = int(result_code)
    row.stdout = stdout if stdout is not None else ""
    row.stderr = stderr if stderr is not None else ""
    row.error_text = error_text
    row.completed_at = now_value
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
