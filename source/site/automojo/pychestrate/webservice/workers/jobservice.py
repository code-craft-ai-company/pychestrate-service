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
from typing import Any, Dict, List, Optional

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
    required_capabilities: List[str]
    lease_holder: Optional[str]
    lease_ttl_seconds: Optional[int]
    priority: int
    project_id: Optional[str]


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
        required_capabilities=(
            list(row.required_capabilities)
            if row.required_capabilities is not None else []
        ),
        lease_holder=row.lease_holder,
        lease_ttl_seconds=(
            int(row.lease_ttl_seconds)
            if row.lease_ttl_seconds is not None else None
        ),
        priority=int(row.priority) if row.priority is not None else 0,
        project_id=(
            str(row.project_id) if row.project_id is not None else None
        ),
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


def _coerce_required_capabilities(
        *,
        value: Optional[Any],
    ) -> List[str]:
    """
        Normalise an incoming required-capabilities parameter to
        a sorted, de-duplicated list of strings. Anything that
        isn't a list (or that contains non-string entries)
        raises ``ValueError`` so a buggy workflow YAML doesn't
        silently match the wrong workers.
    """
    if value is None:
        rtnval: List[str] = []
        return rtnval
    if not isinstance(value, (list, tuple)):
        err_lines = [
            "required_capabilities must be a list of strings.",
            "FOUND_TYPE: {}".format(type(value).__name__),
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg)
    coerced: List[str] = []
    for entry in value:
        if not isinstance(entry, str):
            err_lines = [
                "required_capabilities entries must be strings.",
                "FOUND_TYPE: {}".format(type(entry).__name__),
                "FOUND_VALUE: {!r}".format(entry),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg)
        stripped = entry.strip()
        if len(stripped) == 0:
            continue
        coerced.append(stripped)
    deduped = sorted(set(coerced))
    rtnval = deduped
    return rtnval


def worker_satisfies_capabilities(
        *,
        worker_attributes: Optional[Dict[str, Any]],
        required_capabilities: List[str],
    ) -> bool:
    """
        Return ``True`` when every entry in
        ``required_capabilities`` appears in
        ``worker_attributes['capabilities']`` (a list of
        strings). An empty requirement list always matches.
        Missing / non-list ``capabilities`` is treated as the
        empty set.
    """
    if len(required_capabilities) == 0:
        return True
    if worker_attributes is None:
        return False
    advertised_raw = worker_attributes.get("capabilities", None)
    if not isinstance(advertised_raw, (list, tuple)):
        return False
    advertised = set(
        str(item) for item in advertised_raw if isinstance(item, str)
    )
    for required in required_capabilities:
        if required not in advertised:
            return False
    return True


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
        required_capabilities: Optional[List[str]] = None,
        lease_holder: Optional[str] = None,
        lease_ttl_seconds: Optional[int] = None,
        priority: int = 0,
        project_id: Optional[str] = None,
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
        :param required_capabilities: List of capability strings
                                      the claiming worker must
                                      advertise in
                                      ``attributes.capabilities``.
                                      Empty / None means "any
                                      worker that satisfies the
                                      target_pod_name /
                                      target_kind selector".
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
    capabilities_value = _coerce_required_capabilities(
        value=required_capabilities,
    )
    if lease_ttl_seconds is not None:
        if int(lease_ttl_seconds) <= 0:
            err_lines = [
                "lease_ttl_seconds must be > 0 when supplied.",
                "REQUESTED: {}".format(lease_ttl_seconds),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        lease_ttl_value: Optional[int] = int(lease_ttl_seconds)
    else:
        lease_ttl_value = None
    if lease_holder is not None:
        if len(str(lease_holder)) == 0:
            lease_holder_value: Optional[str] = None
        else:
            lease_holder_value = str(lease_holder)
    else:
        lease_holder_value = None
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
        required_capabilities=capabilities_value,
        lease_holder=lease_holder_value,
        lease_ttl_seconds=lease_ttl_value,
        priority=int(priority),
        project_id=project_id if project_id is not None else None,
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
    # Priority-aware ordering: highest priority first, then
    # FIFO by enqueued_at. The priority column is indexed; the
    # composite ordering matches the index for typical
    # all-pending-rows scans.
    candidates = (
        db_session.query(WorkerJob)
        .filter(WorkerJob.state == JobState.PENDING.value)
        .order_by(
            WorkerJob.priority.desc(),
            WorkerJob.enqueued_at.asc(),
        )
        .all()
    )
    # Lease gate: a worker with an active lease held by someone
    # else can't claim any job (including unscoped ones).
    # Workers leased to the candidate's holder, or unleased, are
    # eligible. We compute this once per claim call.
    from automojo.pychestrate.webservice.workers.service import (
        is_lease_active,
    )
    worker_has_active_lease = is_lease_active(
        worker_row=worker, now=now_value,
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
        # Project gate. A job scoped to project X may only land
        # on workers in project X (or globally-scoped workers
        # with no project_id). Symmetrically, a project-scoped
        # worker only claims jobs from its own project (or
        # unscoped global jobs). The single check below covers
        # both directions: skip iff both sides have a
        # project_id and they differ.
        candidate_project = candidate.project_id
        worker_project = worker.project_id
        if candidate_project is not None and worker_project is not None:
            if str(candidate_project) != str(worker_project):
                continue
        # Capability gate: worker must advertise every required
        # capability in attributes.capabilities (list of strs).
        required_caps = candidate.required_capabilities
        if required_caps is not None and len(required_caps) > 0:
            if worker_satisfies_capabilities(
                worker_attributes=worker.attributes,
                required_capabilities=list(required_caps),
            ) is False:
                continue
        # Lease gate. If the worker is currently leased to
        # someone, only this candidate's matching lease_holder
        # may claim it. If the candidate names a lease_holder
        # but the worker is leased elsewhere, skip.
        if worker_has_active_lease is True:
            if candidate.lease_holder != worker.lease_holder:
                continue
        matched = candidate
        break

    if matched is None:
        return None

    matched.worker_id = worker.worker_id
    matched.state = JobState.CLAIMED.value
    matched.claimed_at = now_value

    # If the candidate names a lease_holder, acquire (or extend)
    # the lease on the worker so subsequent jobs from the same
    # holder land here and other holders are kept out.
    if matched.lease_holder is not None:
        ttl = matched.lease_ttl_seconds
        if ttl is None or int(ttl) <= 0:
            ttl = 600  # 10-minute default if unset.
        worker.lease_holder = matched.lease_holder
        worker.lease_acquired_at = now_value
        worker.lease_expires_at = (
            now_value + timedelta(seconds=int(ttl))
        )

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


def count_jobs_by_state(
        *,
        db_session: DbSession,
    ) -> Dict[str, int]:
    """
        Return a count of :class:`WorkerJob` rows grouped by
        ``state``. Every :class:`JobState` member appears in the
        result with at least ``0`` so the dashboard layer
        doesn't have to special-case empty buckets.
    """
    rows = (
        db_session.query(WorkerJob.state, sa_func_count_label())
        .group_by(WorkerJob.state)
        .all()
    )
    counts: Dict[str, int] = {}
    for member in JobState:
        counts[member.value] = 0
    for state_value, count_value in rows:
        counts[state_value] = int(count_value)
    rtnval = counts
    return rtnval


def count_retry_scheduled_jobs(
        *,
        db_session: DbSession,
        now: Optional[datetime] = None,
    ) -> int:
    """
        Number of PENDING jobs whose ``not_before`` is still in
        the future — i.e. retries waiting on backoff. Useful
        signal for "is the queue stuck or just respecting the
        backoff window?".
    """
    if now is None:
        now_value = datetime.now(timezone.utc)
    else:
        now_value = now
    rows = (
        db_session.query(WorkerJob)
        .filter(WorkerJob.state == JobState.PENDING.value)
        .filter(WorkerJob.not_before.isnot(None))
        .all()
    )
    count = 0
    for row in rows:
        scheduled = _coerce_utc(value=row.not_before)
        if scheduled > now_value:
            count += 1
    rtnval = count
    return rtnval


def oldest_pending_age_seconds(
        *,
        db_session: DbSession,
        now: Optional[datetime] = None,
    ) -> Optional[float]:
    """
        Age (in seconds) of the oldest claimable PENDING job —
        i.e. PENDING with ``not_before`` either NULL or in the
        past. Returns ``None`` when no claimable PENDING row
        exists.
    """
    if now is None:
        now_value = datetime.now(timezone.utc)
    else:
        now_value = now
    rows = (
        db_session.query(WorkerJob)
        .filter(WorkerJob.state == JobState.PENDING.value)
        .order_by(WorkerJob.enqueued_at.asc())
        .all()
    )
    for row in rows:
        if row.not_before is not None:
            scheduled = _coerce_utc(value=row.not_before)
            if scheduled > now_value:
                continue
        enqueued = _coerce_utc(value=row.enqueued_at)
        rtnval = (now_value - enqueued).total_seconds()
        return rtnval
    return None


def list_jobs(
        *,
        db_session: DbSession,
        state: Optional[str] = None,
        target_pod_name: Optional[str] = None,
        target_kind: Optional[str] = None,
        worker_id: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[JobView]:
    """
        List :class:`WorkerJob` rows newest-first with optional
        filters. ``limit`` is clamped to ``[1, 500]`` so a
        runaway dashboard call can't exhaust the API host's
        memory.
    """
    if limit < 1:
        limit_value = 1
    elif limit > 500:
        limit_value = 500
    else:
        limit_value = int(limit)
    query = db_session.query(WorkerJob)
    if state is not None and len(state) > 0:
        query = query.filter(WorkerJob.state == state)
    if target_pod_name is not None and len(target_pod_name) > 0:
        query = query.filter(WorkerJob.target_pod_name == target_pod_name)
    if target_kind is not None and len(target_kind) > 0:
        query = query.filter(WorkerJob.target_kind == target_kind)
    if worker_id is not None and len(worker_id) > 0:
        query = query.filter(WorkerJob.worker_id == worker_id)
    if project_id is not None and len(project_id) > 0:
        query = query.filter(WorkerJob.project_id == project_id)
    rows = (
        query.order_by(WorkerJob.enqueued_at.desc())
        .limit(limit_value)
        .all()
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def sa_func_count_label():
    """
        Return ``sqlalchemy.func.count('*')``. Wrapped in a
        helper so the import of :mod:`sqlalchemy.func` stays
        local — many readers of this module never touch the
        stats path.
    """
    from sqlalchemy import func as sa_func
    rtnval = sa_func.count().label("count")
    return rtnval
