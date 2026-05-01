"""
.. module:: test_p27b_job_retry_policy_m3
    :synopsis: Tests for the worker-job retry policy.

Covers:

* :func:`enqueue_job` accepts ``max_attempts`` /
  ``retry_delay_seconds`` / ``retry_strategy``.
* :func:`compute_next_retry_at` honours both ``fixed`` and
  ``exponential`` strategies; ``retry_delay_seconds <= 0``
  returns ``None`` (claim immediately).
* :func:`report_result` re-enqueues a failed job under the
  configured policy, bumping ``attempt`` and clearing
  attempt-specific fields, and does NOT wake the
  wait_for_completion waker until the job exhausts its
  attempts.
* :func:`report_result` honours ``max_attempts`` exactly: a
  job that fails on its final attempt becomes terminal FAILED
  immediately.
* :func:`claim_next_job` skips rows whose ``not_before`` is
  still in the future, and picks them up once the window has
  elapsed.
* :class:`StaleWorkerSweeper` re-enqueues orphaned jobs that
  still have retries left rather than failing them outright.
* End-to-end through :class:`RemoteCommand`: a workflow with
  ``retries: 2`` whose first attempt fails (rc=1) succeeds on
  the second attempt, and the propagated result is
  SUCCEEDED with the second-attempt's stdout.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile
import threading
import time

from datetime import datetime, timedelta, timezone
from typing import Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)
from automojo.pychestrate.webservice.orchestration.flowruntime import (
    FlowState,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)
from automojo.pychestrate.webservice.workers import jobservice
from automojo.pychestrate.webservice.workers import service as worker_service
from automojo.pychestrate.webservice.workers.jobmodels import (
    JobState,
    RetryStrategy,
    WorkerJob,
)
from automojo.pychestrate.webservice.workers.models import (
    WorkerKind,
)
from automojo.pychestrate.webservice.workers.staleworkersweeper import (
    sweep_once,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p27b_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def test_enqueue_job_accepts_retry_policy_fields():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: enqueue_job stores ``max_attempts``,
    ``retry_delay_seconds``, and ``retry_strategy``; the
    JobView surfaces all three plus ``attempt=1`` and
    ``not_before=None`` for a fresh row.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            view = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={"command": "true"},
                max_attempts=3,
                retry_delay_seconds=2.0,
                retry_strategy="exponential",
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.attempt, 1)
        testbase.assert_equal(view.max_attempts, 3)
        testbase.assert_equal(view.retry_delay_seconds, 2.0)
        testbase.assert_equal(view.retry_strategy, "exponential")
        testbase.assert_equal(view.not_before, None)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_enqueue_job_rejects_invalid_max_attempts():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: ``max_attempts < 1`` and
    ``retry_delay_seconds < 0`` raise ValueError so a buggy
    workflow YAML doesn't silently succeed with weird state.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            try:
                jobservice.enqueue_job(
                    db_session=db_session,
                    payload={"command": "true"},
                    max_attempts=0,
                )
                raised = False
            except ValueError:
                raised = True
            testbase.assert_equal(raised, True)
            try:
                jobservice.enqueue_job(
                    db_session=db_session,
                    payload={"command": "true"},
                    retry_delay_seconds=-1.0,
                )
                raised = False
            except ValueError:
                raised = True
            testbase.assert_equal(raised, True)
        finally:
            db_session.close()
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_compute_next_retry_at_fixed_strategy():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: ``fixed`` strategy returns ``now + delay`` for
    every retry, regardless of attempt number.**
    """
    now = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    first = jobservice.compute_next_retry_at(
        attempt_just_finished=1,
        retry_delay_seconds=5.0,
        retry_strategy=RetryStrategy.FIXED.value,
        now=now,
    )
    testbase.assert_equal(first, now + timedelta(seconds=5))

    fifth = jobservice.compute_next_retry_at(
        attempt_just_finished=5,
        retry_delay_seconds=5.0,
        retry_strategy=RetryStrategy.FIXED.value,
        now=now,
    )
    testbase.assert_equal(fifth, now + timedelta(seconds=5))
    return


def test_compute_next_retry_at_exponential_strategy():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: ``exponential`` strategy doubles the base
    delay each attempt.**
    """
    now = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    # After attempt 1 fails, delay is base * 2^0 = 1 * base.
    one = jobservice.compute_next_retry_at(
        attempt_just_finished=1,
        retry_delay_seconds=2.0,
        retry_strategy=RetryStrategy.EXPONENTIAL.value,
        now=now,
    )
    testbase.assert_equal(one, now + timedelta(seconds=2))
    # After attempt 2 fails, delay is base * 2^1 = 2 * base.
    two = jobservice.compute_next_retry_at(
        attempt_just_finished=2,
        retry_delay_seconds=2.0,
        retry_strategy=RetryStrategy.EXPONENTIAL.value,
        now=now,
    )
    testbase.assert_equal(two, now + timedelta(seconds=4))
    # After attempt 3 fails, delay is base * 2^2 = 4 * base.
    three = jobservice.compute_next_retry_at(
        attempt_just_finished=3,
        retry_delay_seconds=2.0,
        retry_strategy=RetryStrategy.EXPONENTIAL.value,
        now=now,
    )
    testbase.assert_equal(three, now + timedelta(seconds=8))
    return


def test_compute_next_retry_at_zero_delay_returns_none():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: ``retry_delay_seconds <= 0`` means "claim
    immediately" — represented as ``not_before = None``.**
    """
    rtnval = jobservice.compute_next_retry_at(
        attempt_just_finished=1,
        retry_delay_seconds=0.0,
        retry_strategy=RetryStrategy.FIXED.value,
    )
    testbase.assert_equal(rtnval, None)
    return


def test_report_result_re_enqueues_failed_job_with_retries_left():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: A failure (rc != 0) on attempt 1 of a job with
    ``max_attempts=3`` returns the row to PENDING, bumps
    ``attempt`` to 2, clears worker_id / claimed_at / stdout /
    stderr / error_text / result_code, and stamps
    ``not_before`` per the policy.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            worker_view = worker_service.register_worker(
                db_session=db_session,
                name="flaky-pi", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = worker_view.worker_id
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "flaky.sh"},
                max_attempts=3,
                retry_delay_seconds=10.0,
                retry_strategy="fixed",
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
            view = jobservice.report_result(
                db_session=db_session,
                worker_id=worker_id,
                job_id=enqueued.job_id,
                result_code=1,
                stdout="boom\n",
                stderr="failed\n",
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.state, JobState.PENDING.value)
        testbase.assert_equal(view.attempt, 2)
        testbase.assert_equal(view.worker_id, None)
        testbase.assert_equal(view.claimed_at, None)
        testbase.assert_equal(view.completed_at, None)
        testbase.assert_equal(view.result_code, None)
        testbase.assert_equal(view.stdout, "")
        testbase.assert_equal(view.stderr, "")
        testbase.assert_equal(view.error_text, None)
        testbase.assert_equal(view.not_before is not None, True)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_report_result_does_not_wake_waiter_during_retry():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: A failed-but-retried job is not yet terminal,
    so any wait_for_completion waiter must keep blocking.
    The wait-event must NOT be popped + set on retry.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            worker_view = worker_service.register_worker(
                db_session=db_session,
                name="retry-pi", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = worker_view.worker_id
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
                max_attempts=2,
                retry_delay_seconds=0.0,
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
        finally:
            db_session.close()

        wait_event = threading.Event()
        with jobservice._WAIT_LOCK:
            jobservice._WAIT_EVENTS[enqueued.job_id] = wait_event

        db_session = factory()
        try:
            jobservice.report_result(
                db_session=db_session,
                worker_id=worker_id,
                job_id=enqueued.job_id,
                result_code=1,
            )
        finally:
            db_session.close()

        testbase.assert_equal(wait_event.is_set(), False)
        # The wait event is still registered (for the next
        # attempt's terminal report).
        with jobservice._WAIT_LOCK:
            still_registered = (
                enqueued.job_id in jobservice._WAIT_EVENTS
            )
        testbase.assert_equal(still_registered, True)
    finally:
        with jobservice._WAIT_LOCK:
            jobservice._WAIT_EVENTS.clear()
        engine.dispose()
        os.unlink(path)
    return


def test_report_result_terminal_failure_on_final_attempt():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: A failure on the final attempt
    (``attempt == max_attempts``) is recorded as terminal
    FAILED with the worker's reported stdout/stderr/error_text
    intact, AND the wait_for_completion waiter is woken.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            worker_view = worker_service.register_worker(
                db_session=db_session,
                name="last-pi", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = worker_view.worker_id
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
                max_attempts=2,
                retry_delay_seconds=0.0,
            )
            # First failure → re-enqueue.
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
            jobservice.report_result(
                db_session=db_session, worker_id=worker_id,
                job_id=enqueued.job_id, result_code=1,
            )
            # Second claim → second failure → terminal.
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
        finally:
            db_session.close()

        wait_event = threading.Event()
        with jobservice._WAIT_LOCK:
            jobservice._WAIT_EVENTS[enqueued.job_id] = wait_event

        db_session = factory()
        try:
            view = jobservice.report_result(
                db_session=db_session,
                worker_id=worker_id,
                job_id=enqueued.job_id,
                result_code=2,
                stdout="final attempt boom\n",
                stderr="really failed",
            )
        finally:
            db_session.close()

        testbase.assert_equal(view.state, JobState.FAILED.value)
        testbase.assert_equal(view.attempt, 2)
        testbase.assert_equal(view.result_code, 2)
        testbase.assert_equal("really failed" in view.stderr, True)
        testbase.assert_equal(wait_event.is_set(), True)
    finally:
        with jobservice._WAIT_LOCK:
            jobservice._WAIT_EVENTS.clear()
        engine.dispose()
        os.unlink(path)
    return


def test_claim_next_job_respects_not_before_window():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: A job with ``not_before`` in the future is
    skipped by claim_next_job; a job with ``not_before`` in
    the past (or null) is claimable.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            worker_view = worker_service.register_worker(
                db_session=db_session,
                name="claimer", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = worker_view.worker_id
            # Future window — not yet claimable.
            future_view = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "future"},
            )
            future_row = (
                db_session.query(WorkerJob)
                .filter(WorkerJob.job_id == future_view.job_id)
                .first()
            )
            future_row.not_before = (
                datetime.now(timezone.utc) + timedelta(seconds=60)
            )
            db_session.commit()
            # Past window — claimable.
            past_view = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "past"},
            )
            past_row = (
                db_session.query(WorkerJob)
                .filter(WorkerJob.job_id == past_view.job_id)
                .first()
            )
            past_row.not_before = (
                datetime.now(timezone.utc) - timedelta(seconds=60)
            )
            db_session.commit()
            claimed = jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(claimed is not None, True)
        testbase.assert_equal(claimed.job_id, past_view.job_id)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_stale_sweeper_re_enqueues_orphaned_job_with_retries_left():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: When the sweeper times out a worker mid-job
    AND the job has retries left, the job is re-enqueued
    rather than failed. ``jobs_retried`` carries the id;
    ``jobs_failed`` does not.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            worker_view = worker_service.register_worker(
                db_session=db_session,
                name="dropper", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = worker_view.worker_id
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
                max_attempts=3,
                retry_delay_seconds=0.0,
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
            # Backdate the worker's heartbeat so the sweeper
            # ages it out.
            from automojo.pychestrate.webservice.workers.models import (
                Worker,
            )
            worker_row = (
                db_session.query(Worker)
                .filter(Worker.worker_id == worker_id)
                .first()
            )
            worker_row.last_heartbeat_at = (
                datetime.now(timezone.utc) - timedelta(seconds=300)
            )
            db_session.commit()
        finally:
            db_session.close()

        db_session = factory()
        try:
            result = sweep_once(
                db_session=db_session, stale_threshold_seconds=60.0,
            )
        finally:
            db_session.close()

        testbase.assert_equal(result.jobs_retried, [enqueued.job_id])
        testbase.assert_equal(result.jobs_failed, [])

        db_session = factory()
        try:
            view = jobservice.read_job(
                db_session=db_session, job_id=enqueued.job_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.state, JobState.PENDING.value)
        testbase.assert_equal(view.attempt, 2)
        testbase.assert_equal(view.worker_id, None)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_stale_sweeper_fails_orphaned_job_on_final_attempt():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: When the sweeper times out a worker on the
    job's final attempt, the job is failed terminally with
    the sweeper's diagnostic and the wait-event fires.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            worker_view = worker_service.register_worker(
                db_session=db_session,
                name="lastdrop", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = worker_view.worker_id
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
                max_attempts=1,
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
            from automojo.pychestrate.webservice.workers.models import (
                Worker,
            )
            worker_row = (
                db_session.query(Worker)
                .filter(Worker.worker_id == worker_id)
                .first()
            )
            worker_row.last_heartbeat_at = (
                datetime.now(timezone.utc) - timedelta(seconds=300)
            )
            db_session.commit()
        finally:
            db_session.close()

        wait_event = threading.Event()
        with jobservice._WAIT_LOCK:
            jobservice._WAIT_EVENTS[enqueued.job_id] = wait_event

        db_session = factory()
        try:
            result = sweep_once(
                db_session=db_session, stale_threshold_seconds=60.0,
            )
        finally:
            db_session.close()
        testbase.assert_equal(result.jobs_failed, [enqueued.job_id])
        testbase.assert_equal(result.jobs_retried, [])
        testbase.assert_equal(wait_event.is_set(), True)
    finally:
        with jobservice._WAIT_LOCK:
            jobservice._WAIT_EVENTS.clear()
        engine.dispose()
        os.unlink(path)
    return


def test_remote_command_succeeds_on_second_attempt():
    """
    **Feature: P27b job retry policy (M3)**
    **Property: A workflow with ``retries: 1`` whose first
    attempt fails and second attempt succeeds reaches
    terminal SUCCEEDED with the second-attempt's stdout. The
    queue + sweeper machinery handle the retry transparently
    to the workflow author.**
    """
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p27b-test-pepper"))
    engine, factory, path = _build_engine_and_factory()
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
        local_worker_pool_size=0,  # use a stub worker thread.
    )

    # Pre-register the worker the stub will identify as.
    db_session = factory()
    try:
        worker_view = worker_service.register_worker(
            db_session=db_session,
            name="flake-pi",
            kind=WorkerKind.REMOTE_MACHINE,
            attributes={"pod_name": "flake-pi"},
        )
        worker_id = worker_view.worker_id
    finally:
        db_session.close()

    stop_event = threading.Event()
    attempts_seen: list = []

    def _stub_worker_loop() -> None:
        while not stop_event.is_set():
            db_session = factory()
            try:
                claimed = jobservice.claim_next_job(
                    db_session=db_session, worker_id=worker_id,
                )
            finally:
                db_session.close()
            if claimed is None:
                stop_event.wait(0.05)
                continue
            attempts_seen.append(claimed.attempt)
            db_session = factory()
            try:
                if claimed.attempt == 1:
                    # First attempt fails.
                    jobservice.report_result(
                        db_session=db_session,
                        worker_id=worker_id,
                        job_id=claimed.job_id,
                        result_code=1,
                        stderr="transient blip\n",
                    )
                else:
                    # Second attempt succeeds.
                    jobservice.report_result(
                        db_session=db_session,
                        worker_id=worker_id,
                        job_id=claimed.job_id,
                        result_code=0,
                        stdout="recovered on attempt {0}\n".format(
                            claimed.attempt,
                        ),
                    )
            finally:
                db_session.close()
        return

    worker_thread = threading.Thread(
        target=_stub_worker_loop, daemon=True,
    )
    worker_thread.start()

    try:
        workflow_yaml = "\n".join([
            "name: p27b-retry-smoke",
            "environment: {}",
            "parameters: {}",
            "flow:",
            "  - task: probe",
            "    tasktype: automojo.pychestrate.webservice.orchestration.remotecommand@RemoteCommand",
            "    command: flaky-test.sh",
            "    target_pod_name: flake-pi",
            "    retries: 2",
            "    retry_delay_seconds: 0",
            "    timeout_seconds: 5",
            "",
        ])
        flow_id = app.flow_runtime.submit_workflow_yaml(
            workflow_yaml=workflow_yaml,
        )
        deadline = time.time() + 10.0
        terminal_state = None
        while time.time() < deadline:
            sub = app.flow_runtime.status(flow_id=flow_id)
            if sub is not None and sub.state in (
                FlowState.SUCCEEDED, FlowState.FAILED,
            ):
                terminal_state = sub.state
                break
            time.sleep(0.05)
        testbase.assert_equal(terminal_state, FlowState.SUCCEEDED)

        # Two distinct attempts were seen.
        testbase.assert_equal(attempts_seen, [1, 2])

        # And the persisted job carries the second attempt's
        # output.
        db_session = factory()
        try:
            from automojo.pychestrate.webservice.workers.jobmodels import (
                WorkerJob,
            )
            row = (
                db_session.query(WorkerJob)
                .filter(WorkerJob.target_pod_name == "flake-pi")
                .first()
            )
        finally:
            db_session.close()
        testbase.assert_equal(row.state, JobState.SUCCEEDED.value)
        testbase.assert_equal(row.attempt, 2)
        testbase.assert_equal("recovered" in row.stdout, True)
    finally:
        stop_event.set()
        worker_thread.join(timeout=2.0)
        app.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return
