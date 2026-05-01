"""
.. module:: pychestrate.webservice.workers.staleworkersweeper
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Background sweeper that ages out unresponsive workers.

.. moduleauthor:: Automation Mojo LLC

A registered worker's liveness is signalled by ``last_heartbeat_at``
on its :class:`Worker` row. Real-world workers (especially Pi
hosts on flaky networks) drop off frequently — they lose power,
the network NIC resets, the agent process is killed without a
chance to deregister. Without a sweeper their ``Worker`` rows
stay ``IDLE`` / ``RUNNING`` forever, and any
PENDING / CLAIMED / RUNNING ``WorkerJob`` rows assigned to them
sit in the queue indefinitely.

This module owns the :class:`StaleWorkerSweeper` background
thread that:

1. Walks every non-OFFLINE worker and computes
   ``now - last_heartbeat_at`` (treating ``last_heartbeat_at IS
   NULL`` as ``registered_at``);
2. Marks workers whose lag exceeds the configured threshold as
   :class:`WorkerStatus.OFFLINE`;
3. Walks every CLAIMED / RUNNING ``WorkerJob`` whose owning
   worker is now OFFLINE and fails them with a clear
   ``error_text``, so the queue's :func:`wait_for_completion`
   waiters don't block forever.

The sweeper is owned by :class:`PychestrateApplication` and
shares the application's ``session_factory``. It runs at the
configured cadence (default every 30s) and is configurable via
env vars so operators can dial in tighter or looser thresholds
without code changes.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import threading

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.workers.jobmodels import (
    JobState,
    WorkerJob,
)
from automojo.pychestrate.webservice.workers.models import (
    Worker,
    WorkerStatus,
)


logger = logging.getLogger(__name__)


SessionFactory = Callable[[], DbSession]


_DEFAULT_STALE_THRESHOLD_SECONDS = 60.0
_DEFAULT_SWEEP_INTERVAL_SECONDS = 30.0
_OFFLINE_REASON_TEMPLATE = (
    "worker timed out (no heartbeat for {0:.0f}s; threshold {1:.0f}s)"
)


@dataclass(frozen=True)
class SweepResult:
    """
        Summary of a single sweep pass — useful for tests and
        ops dashboards.

        :ivar workers_marked_offline: Worker IDs flipped to
                                      OFFLINE this pass.
        :ivar jobs_failed: Job IDs failed this pass because
                           their owning worker had timed out
                           AND the job had no retries left.
        :ivar jobs_retried: Job IDs that the sweeper
                            re-enqueued after their owning
                            worker timed out. The original
                            target_pod_name / target_kind
                            selector is kept; the next attempt
                            can therefore land on any worker
                            that satisfies the selector — i.e.
                            another Pi with the same name (or
                            any worker, when the job was
                            unscoped).
    """
    workers_marked_offline: List[str]
    jobs_failed: List[str]
    jobs_retried: List[str]


def _coerce_utc(*, value: datetime) -> datetime:
    """
        Attach UTC to a naive ``datetime``. SQLite drops timezone
        info on round-trip even when ``DateTime(timezone=True)``
        is declared; we always store UTC so the coercion is
        unambiguous.
    """
    if value.tzinfo is not None:
        return value
    rtnval = value.replace(tzinfo=timezone.utc)
    return rtnval


def _stamp_lag_seconds(*, row: Worker, now: datetime) -> float:
    """
        Compute how long ago the worker last signalled liveness.
        ``last_heartbeat_at IS NULL`` is treated as
        ``registered_at`` so a worker that has never heartbeated
        is still aged out eventually.
    """
    if row.last_heartbeat_at is not None:
        last = _coerce_utc(value=row.last_heartbeat_at)
    else:
        last = _coerce_utc(value=row.registered_at)
    delta = now - last
    rtnval = delta.total_seconds()
    return rtnval


def sweep_once(
        *,
        db_session: DbSession,
        stale_threshold_seconds: float,
        now: Optional[datetime] = None,
    ) -> SweepResult:
    """
        Run a single sweep pass against ``db_session``.

        Splits cleanly out of :class:`StaleWorkerSweeper` so
        tests can drive the logic deterministically without
        spinning up the background thread.

        :param db_session: SQLAlchemy session.
        :param stale_threshold_seconds: Workers whose lag
                                        exceeds this are flipped
                                        to OFFLINE.
        :param now: Optional clock override; defaults to
                    ``datetime.now(timezone.utc)``.
        :returns: :class:`SweepResult` describing what changed.
    """
    if now is None:
        now_value = datetime.now(timezone.utc)
    else:
        now_value = now

    candidates = (
        db_session.query(Worker)
        .filter(Worker.status != WorkerStatus.OFFLINE.value)
        .all()
    )

    flipped_worker_ids: List[str] = []
    for row in candidates:
        lag = _stamp_lag_seconds(row=row, now=now_value)
        if lag <= stale_threshold_seconds:
            continue
        row.status = WorkerStatus.OFFLINE.value
        flipped_worker_ids.append(str(row.worker_id))

    failed_job_ids: List[str] = []
    retried_job_ids: List[str] = []
    if len(flipped_worker_ids) > 0:
        # Any in-flight job whose owning worker is now offline
        # is either re-enqueued for another attempt (when the
        # job's retry policy still has attempts left) or failed
        # outright so the wait_for_completion waker fires.
        in_flight_states = (
            JobState.CLAIMED.value, JobState.RUNNING.value,
        )
        stuck_jobs = (
            db_session.query(WorkerJob)
            .filter(WorkerJob.state.in_(in_flight_states))
            .filter(WorkerJob.worker_id.in_(flipped_worker_ids))
            .all()
        )
        # Lazy import — jobservice imports jobmodels and we
        # want to avoid touching the import-time graph.
        from automojo.pychestrate.webservice.workers import jobservice
        for job in stuck_jobs:
            job_lag_seconds: float
            if job.claimed_at is not None:
                claimed = _coerce_utc(value=job.claimed_at)
                job_lag_seconds = (now_value - claimed).total_seconds()
            else:
                job_lag_seconds = stale_threshold_seconds
            error_text = _OFFLINE_REASON_TEMPLATE.format(
                job_lag_seconds, stale_threshold_seconds,
            )
            current_attempt = (
                int(job.attempt) if job.attempt is not None else 1
            )
            max_attempts = (
                int(job.max_attempts)
                if job.max_attempts is not None else 1
            )
            if current_attempt < max_attempts:
                # Re-enqueue. Mirror the report_result retry
                # path: clear attempt-specific state, bump
                # attempt, schedule the next claim.
                job.attempt = current_attempt + 1
                job.state = JobState.PENDING.value
                job.worker_id = None
                job.claimed_at = None
                job.completed_at = None
                job.result_code = None
                job.stdout = ""
                job.stderr = ""
                job.error_text = None
                job.not_before = jobservice.compute_next_retry_at(
                    attempt_just_finished=current_attempt,
                    retry_delay_seconds=float(
                        job.retry_delay_seconds or 0.0,
                    ),
                    retry_strategy=(
                        job.retry_strategy
                        or "fixed"
                    ),
                    now=now_value,
                )
                retried_job_ids.append(str(job.job_id))
            else:
                job.state = JobState.FAILED.value
                job.error_text = error_text
                job.completed_at = now_value
                if job.result_code is None:
                    job.result_code = 1
                failed_job_ids.append(str(job.job_id))

    if (
        len(flipped_worker_ids) > 0
        or len(failed_job_ids) > 0
        or len(retried_job_ids) > 0
    ):
        db_session.commit()
        from automojo.pychestrate.webservice.workers import jobservice
        for job_id in failed_job_ids:
            with jobservice._WAIT_LOCK:
                event = jobservice._WAIT_EVENTS.pop(job_id, None)
            if event is not None:
                event.set()

    rtnval = SweepResult(
        workers_marked_offline=flipped_worker_ids,
        jobs_failed=failed_job_ids,
        jobs_retried=retried_job_ids,
    )
    return rtnval


class StaleWorkerSweeper:
    """
        Background thread that periodically calls
        :func:`sweep_once`.

        Lifecycle: ``__init__`` constructs but does not start.
        :meth:`start` spins up the thread; :meth:`shutdown`
        signals it to stop and (optionally) joins.
    """

    def __init__(
            self,
            *,
            session_factory: SessionFactory,
            stale_threshold_seconds: float = (
                _DEFAULT_STALE_THRESHOLD_SECONDS
            ),
            sweep_interval_seconds: float = (
                _DEFAULT_SWEEP_INTERVAL_SECONDS
            ),
        ):
        if stale_threshold_seconds < 0.0:
            err_lines = [
                "stale_threshold_seconds must be >= 0.",
                "REQUESTED: {}".format(stale_threshold_seconds),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg)
        if sweep_interval_seconds <= 0.0:
            err_lines = [
                "sweep_interval_seconds must be > 0.",
                "REQUESTED: {}".format(sweep_interval_seconds),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg)
        self._session_factory: SessionFactory = session_factory
        self._stale_threshold_seconds: float = stale_threshold_seconds
        self._sweep_interval_seconds: float = sweep_interval_seconds
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_result: Optional[SweepResult] = None
        return

    @property
    def stale_threshold_seconds(self) -> float:
        rtnval = self._stale_threshold_seconds
        return rtnval

    @property
    def sweep_interval_seconds(self) -> float:
        rtnval = self._sweep_interval_seconds
        return rtnval

    @property
    def is_running(self) -> bool:
        rtnval = (
            self._thread is not None and self._thread.is_alive()
        )
        return rtnval

    @property
    def last_result(self) -> Optional[SweepResult]:
        rtnval = self._last_result
        return rtnval

    def start(self) -> None:
        """
            Spin up the background sweep thread.
        """
        if self._thread is not None:
            err_lines = [
                "StaleWorkerSweeper has already been started.",
            ]
            err_msg = os.linesep.join(err_lines)
            raise RuntimeError(err_msg)
        self._thread = threading.Thread(
            target=self._run_loop,
            name="pych-stale-worker-sweeper",
            daemon=True,
        )
        self._thread.start()
        return

    def shutdown(self, *, wait: bool = True) -> None:
        """
            Signal the loop to stop and optionally join.
        """
        self._stop_event.set()
        if wait is True:
            if self._thread is not None:
                self._thread.join(timeout=10.0)
        return

    def run_one_pass(self) -> SweepResult:
        """
            Execute one synchronous sweep pass on the calling
            thread. Used by tests to bypass the background loop.
        """
        db_session = self._session_factory()
        try:
            result = sweep_once(
                db_session=db_session,
                stale_threshold_seconds=self._stale_threshold_seconds,
            )
        finally:
            db_session.close()
        self._last_result = result
        return result

    def _run_loop(self) -> None:
        logger.info(
            "stale_worker_sweeper.start interval=%.1fs threshold=%.1fs",
            self._sweep_interval_seconds,
            self._stale_threshold_seconds,
        )
        while self._stop_event.is_set() is False:
            try:
                self.run_one_pass()
            except Exception:
                logger.exception(
                    "stale_worker_sweeper.crashed — continuing",
                )
            self._stop_event.wait(self._sweep_interval_seconds)
        logger.info("stale_worker_sweeper.stop")
        return


def resolve_sweeper_config_from_env(
        *,
        environment: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
    """
        Read sweeper configuration from process environment so
        the operator can dial in thresholds without a code
        change.

        Recognised vars:

        * ``PYCHESTRATE_WORKER_STALE_THRESHOLD_SECONDS`` —
          seconds since last_heartbeat_at before a worker is
          flipped to OFFLINE; default ``60``. Set to ``0`` to
          disable the sweeper entirely (no workers will be aged
          out).
        * ``PYCHESTRATE_WORKER_SWEEP_INTERVAL_SECONDS`` —
          seconds between sweep passes; default ``30``.
    """
    if environment is None:
        env = os.environ
    else:
        env = environment

    raw_threshold = env.get(
        "PYCHESTRATE_WORKER_STALE_THRESHOLD_SECONDS", None,
    )
    if raw_threshold is None:
        threshold = _DEFAULT_STALE_THRESHOLD_SECONDS
    else:
        try:
            threshold = float(raw_threshold)
        except (TypeError, ValueError):
            threshold = _DEFAULT_STALE_THRESHOLD_SECONDS
        if threshold < 0.0:
            threshold = 0.0

    raw_interval = env.get(
        "PYCHESTRATE_WORKER_SWEEP_INTERVAL_SECONDS", None,
    )
    if raw_interval is None:
        interval = _DEFAULT_SWEEP_INTERVAL_SECONDS
    else:
        try:
            interval = float(raw_interval)
        except (TypeError, ValueError):
            interval = _DEFAULT_SWEEP_INTERVAL_SECONDS
        if interval <= 0.0:
            interval = _DEFAULT_SWEEP_INTERVAL_SECONDS

    rtnval = {
        "stale_threshold_seconds": threshold,
        "sweep_interval_seconds": interval,
        "enabled": threshold > 0.0,
    }
    return rtnval
