"""
.. module:: test_p27a_stale_worker_sweeper_m3
    :synopsis: Tests for the stale-worker sweeper.

Covers:

* :func:`sweep_once` flips a worker whose ``last_heartbeat_at``
  exceeds the threshold from IDLE to OFFLINE.
* A worker with a fresh heartbeat is left alone.
* A worker with no heartbeat at all is aged from
  ``registered_at`` (so a Pi that crashes between register and
  first heartbeat still exits the registry).
* CLAIMED / RUNNING jobs whose owning worker just flipped to
  OFFLINE are themselves failed with an explanatory
  ``error_text``; jobservice.wait_for_completion waiters are
  woken so they don't block forever.
* Already-OFFLINE workers and already-terminal jobs are skipped.
* :class:`StaleWorkerSweeper` start/shutdown lifecycle and the
  ``run_one_pass`` helper drive the same logic synchronously.
* :func:`resolve_sweeper_config_from_env` honours overrides and
  falls back to defaults on garbage; ``threshold=0`` reports
  ``enabled=False`` so the bootstrap can skip the autostart.
* End-to-end via :class:`PychestrateApplication`: a flow with a
  RemoteCommand step whose target worker dies mid-flight is
  failed by the sweeper, and the FlowSubmissionRecord captures
  the failure rather than hanging until the workflow timeout.
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
    WorkerJob,
)
from automojo.pychestrate.webservice.workers.models import (
    Worker,
    WorkerKind,
    WorkerStatus,
)
from automojo.pychestrate.webservice.workers.staleworkersweeper import (
    StaleWorkerSweeper,
    resolve_sweeper_config_from_env,
    sweep_once,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p27a_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def _stamp_heartbeat(
        *,
        factory: sessionmaker,
        worker_id: str,
        when: datetime,
    ) -> None:
    """
        Force-set the worker's ``last_heartbeat_at`` so the
        sweeper sees a deterministic age.
    """
    db_session = factory()
    try:
        row = (
            db_session.query(Worker)
            .filter(Worker.worker_id == worker_id)
            .first()
        )
        row.last_heartbeat_at = when
        db_session.commit()
    finally:
        db_session.close()
    return


def test_sweep_flips_stale_worker_to_offline():
    """
    **Feature: P27a stale-worker sweeper (M3)**
    **Property: A worker whose ``last_heartbeat_at`` is older
    than the threshold is moved from IDLE to OFFLINE on a
    sweep.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            view = worker_service.register_worker(
                db_session=db_session,
                name="lost-pi", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = view.worker_id
        finally:
            db_session.close()
        # Backdate the heartbeat past the threshold.
        _stamp_heartbeat(
            factory=factory, worker_id=worker_id,
            when=datetime.now(timezone.utc) - timedelta(seconds=120),
        )

        db_session = factory()
        try:
            result = sweep_once(
                db_session=db_session, stale_threshold_seconds=60.0,
            )
        finally:
            db_session.close()
        testbase.assert_equal(result.workers_marked_offline, [worker_id])

        db_session = factory()
        try:
            row = (
                db_session.query(Worker)
                .filter(Worker.worker_id == worker_id)
                .first()
            )
            testbase.assert_equal(row.status, WorkerStatus.OFFLINE.value)
        finally:
            db_session.close()
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_sweep_leaves_fresh_worker_alone():
    """
    **Feature: P27a stale-worker sweeper (M3)**
    **Property: A worker with a recent heartbeat (well under the
    threshold) is not flipped to OFFLINE.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            view = worker_service.register_worker(
                db_session=db_session,
                name="alive-pi", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = view.worker_id
        finally:
            db_session.close()
        _stamp_heartbeat(
            factory=factory, worker_id=worker_id,
            when=datetime.now(timezone.utc) - timedelta(seconds=5),
        )

        db_session = factory()
        try:
            result = sweep_once(
                db_session=db_session, stale_threshold_seconds=60.0,
            )
        finally:
            db_session.close()
        testbase.assert_equal(result.workers_marked_offline, [])

        db_session = factory()
        try:
            row = (
                db_session.query(Worker)
                .filter(Worker.worker_id == worker_id)
                .first()
            )
            testbase.assert_equal(row.status, WorkerStatus.IDLE.value)
        finally:
            db_session.close()
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_sweep_uses_registered_at_when_heartbeat_is_null():
    """
    **Feature: P27a stale-worker sweeper (M3)**
    **Property: When ``last_heartbeat_at`` is NULL — for example
    a worker that registered then immediately crashed — the
    sweeper falls back to ``registered_at`` so the row still
    ages out.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            row = Worker(
                worker_id="00000000-0000-4000-8000-00000000aa01",
                name="never-pulsed",
                kind=WorkerKind.REMOTE_MACHINE.value,
                project_id=None,
                client_id=None,
                status=WorkerStatus.IDLE.value,
                # registered 5 minutes ago, no heartbeat.
                registered_at=(
                    datetime.now(timezone.utc) - timedelta(seconds=300)
                ),
                last_heartbeat_at=None,
                attributes={},
            )
            db_session.add(row)
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
        testbase.assert_equal(len(result.workers_marked_offline), 1)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_sweep_fails_in_flight_jobs_owned_by_offline_worker():
    """
    **Feature: P27a stale-worker sweeper (M3)**
    **Property: Any CLAIMED / RUNNING ``WorkerJob`` whose owning
    worker has just been flipped to OFFLINE is failed with a
    descriptive ``error_text``, completed_at is stamped, and
    ``result_code`` defaults to 1 — so
    ``wait_for_completion`` waiters wake immediately.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            view = worker_service.register_worker(
                db_session=db_session,
                name="dead-pi", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = view.worker_id
        finally:
            db_session.close()
        _stamp_heartbeat(
            factory=factory, worker_id=worker_id,
            when=datetime.now(timezone.utc) - timedelta(seconds=300),
        )

        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={"command": "uname"},
            )
            claimed = jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(claimed.job_id, enqueued.job_id)

        # Simulate the waiter set up by RemoteCommand.
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

        testbase.assert_equal(
            result.workers_marked_offline, [worker_id],
        )
        testbase.assert_equal(result.jobs_failed, [enqueued.job_id])
        # Waker fired.
        testbase.assert_equal(wait_event.is_set(), True)

        db_session = factory()
        try:
            view = jobservice.read_job(
                db_session=db_session, job_id=enqueued.job_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.state, JobState.FAILED.value)
        testbase.assert_equal(view.result_code, 1)
        testbase.assert_equal(
            "worker timed out" in (view.error_text or ""), True,
        )
        testbase.assert_equal(view.completed_at is not None, True)
    finally:
        # Clean up any lingering wait events.
        with jobservice._WAIT_LOCK:
            jobservice._WAIT_EVENTS.clear()
        engine.dispose()
        os.unlink(path)
    return


def test_sweep_skips_already_offline_workers():
    """
    **Feature: P27a stale-worker sweeper (M3)**
    **Property: A worker already in OFFLINE is filtered out of
    the candidate set, so the sweeper does no redundant writes.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            view = worker_service.register_worker(
                db_session=db_session,
                name="zombie", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = view.worker_id
            row = (
                db_session.query(Worker)
                .filter(Worker.worker_id == worker_id)
                .first()
            )
            row.status = WorkerStatus.OFFLINE.value
            row.last_heartbeat_at = (
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
        testbase.assert_equal(result.workers_marked_offline, [])
        testbase.assert_equal(result.jobs_failed, [])
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_sweep_skips_terminal_jobs_even_when_worker_offline():
    """
    **Feature: P27a stale-worker sweeper (M3)**
    **Property: SUCCEEDED / FAILED jobs are not touched when
    their owning worker times out — only jobs still in
    CLAIMED or RUNNING are failed.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            view = worker_service.register_worker(
                db_session=db_session,
                name="finished-pi", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = view.worker_id
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={"command": "true"},
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
            # Mark terminal before the sweep runs.
            jobservice.report_result(
                db_session=db_session,
                worker_id=worker_id,
                job_id=enqueued.job_id,
                result_code=0,
                stdout="ok\n",
            )
        finally:
            db_session.close()
        _stamp_heartbeat(
            factory=factory, worker_id=worker_id,
            when=datetime.now(timezone.utc) - timedelta(seconds=300),
        )

        db_session = factory()
        try:
            result = sweep_once(
                db_session=db_session, stale_threshold_seconds=60.0,
            )
        finally:
            db_session.close()
        # Worker did flip — but the terminal job is left alone.
        testbase.assert_equal(result.workers_marked_offline, [worker_id])
        testbase.assert_equal(result.jobs_failed, [])

        db_session = factory()
        try:
            view = jobservice.read_job(
                db_session=db_session, job_id=enqueued.job_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.state, JobState.SUCCEEDED.value)
        testbase.assert_equal(view.result_code, 0)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_stale_worker_sweeper_run_one_pass_synchronously():
    """
    **Feature: P27a stale-worker sweeper (M3)**
    **Property: ``StaleWorkerSweeper.run_one_pass`` drives the
    same logic on the calling thread for deterministic test
    use, and stashes the result in ``last_result``.**
    """
    engine, factory, path = _build_engine_and_factory()
    sweeper = StaleWorkerSweeper(
        session_factory=factory,
        stale_threshold_seconds=10.0,
        sweep_interval_seconds=60.0,
    )
    try:
        db_session = factory()
        try:
            view = worker_service.register_worker(
                db_session=db_session,
                name="explicit", kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_id = view.worker_id
        finally:
            db_session.close()
        _stamp_heartbeat(
            factory=factory, worker_id=worker_id,
            when=datetime.now(timezone.utc) - timedelta(seconds=60),
        )

        result = sweeper.run_one_pass()
        testbase.assert_equal(result.workers_marked_offline, [worker_id])
        testbase.assert_equal(sweeper.last_result, result)
    finally:
        sweeper.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return


def test_stale_worker_sweeper_background_thread_lifecycle():
    """
    **Feature: P27a stale-worker sweeper (M3)**
    **Property: ``start`` spins up a daemon thread and
    ``shutdown`` joins cleanly. ``is_running`` reflects the
    state.**
    """
    engine, factory, path = _build_engine_and_factory()
    sweeper = StaleWorkerSweeper(
        session_factory=factory,
        stale_threshold_seconds=60.0,
        sweep_interval_seconds=0.05,
    )
    try:
        testbase.assert_equal(sweeper.is_running, False)
        sweeper.start()
        # Give the thread a moment to actually start.
        time.sleep(0.1)
        testbase.assert_equal(sweeper.is_running, True)
    finally:
        sweeper.shutdown(wait=True)
        testbase.assert_equal(sweeper.is_running, False)
        engine.dispose()
        os.unlink(path)
    return


def test_resolve_sweeper_config_from_env_overrides():
    """
    **Feature: P27a stale-worker sweeper (M3)**
    **Property: env-driven config overrides are read off the
    supplied environment mapping (not ``os.environ``), and
    ``threshold=0`` opts out of autostart via ``enabled=False``.**
    """
    config = resolve_sweeper_config_from_env(environment={
        "PYCHESTRATE_WORKER_STALE_THRESHOLD_SECONDS": "120",
        "PYCHESTRATE_WORKER_SWEEP_INTERVAL_SECONDS": "5",
    })
    testbase.assert_equal(config["stale_threshold_seconds"], 120.0)
    testbase.assert_equal(config["sweep_interval_seconds"], 5.0)
    testbase.assert_equal(config["enabled"], True)

    disabled = resolve_sweeper_config_from_env(environment={
        "PYCHESTRATE_WORKER_STALE_THRESHOLD_SECONDS": "0",
    })
    testbase.assert_equal(disabled["stale_threshold_seconds"], 0.0)
    testbase.assert_equal(disabled["enabled"], False)

    garbage = resolve_sweeper_config_from_env(environment={
        "PYCHESTRATE_WORKER_STALE_THRESHOLD_SECONDS": "not-a-number",
        "PYCHESTRATE_WORKER_SWEEP_INTERVAL_SECONDS": "0",
    })
    testbase.assert_equal(garbage["stale_threshold_seconds"], 60.0)
    testbase.assert_equal(garbage["sweep_interval_seconds"], 30.0)
    return


def test_remote_command_unblocks_when_worker_is_swept_offline():
    """
    **Feature: P27a stale-worker sweeper (M3)**
    **Property: End-to-end through PychestrateApplication: a
    flow whose RemoteCommand step claims a job and then loses
    the worker (no further heartbeats) is unblocked promptly by
    the sweeper. The orphaned WorkerJob lands in FAILED with the
    sweeper's ``error_text``, the FlowRuntime worker stops
    waiting (well before the workflow ``timeout_seconds``), and
    the submission reaches a terminal state. This is the
    real-world Pi-loses-power scenario.**
    """
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p27a-test-pepper"))
    engine, factory, path = _build_engine_and_factory()
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
        # No autostart — we'll drive the sweeper synchronously.
    )
    # Manually pre-register a worker that will go silent.
    db_session = factory()
    try:
        view = worker_service.register_worker(
            db_session=db_session,
            name="silent-pi", kind=WorkerKind.REMOTE_MACHINE,
            attributes={"pod_name": "silent-pi"},
        )
        worker_id = view.worker_id
    finally:
        db_session.close()
    # Pretend the worker has not heartbeated for a long time. We
    # also have it claim the job before the sweep runs, since
    # only CLAIMED / RUNNING jobs are touched.
    try:
        workflow_yaml = "\n".join([
            "name: p27a-silent-worker",
            "environment: {}",
            "parameters: {}",
            "flow:",
            "  - task: probe",
            "    tasktype: automojo.pychestrate.webservice.orchestration.remotecommand@RemoteCommand",
            "    command: echo never-runs",
            "    target_pod_name: silent-pi",
            # Generous workflow-side timeout — we want the
            # sweeper to be the thing that fails this, not the
            # RemoteCommand timeout.
            "    timeout_seconds: 60",
            "",
        ])
        flow_id = app.flow_runtime.submit_workflow_yaml(
            workflow_yaml=workflow_yaml,
        )

        # Wait until the RemoteCommand has enqueued a job.
        deadline = time.time() + 5.0
        enqueued_job_id = None
        while time.time() < deadline and enqueued_job_id is None:
            db_session = factory()
            try:
                row = (
                    db_session.query(WorkerJob)
                    .filter(WorkerJob.target_pod_name == "silent-pi")
                    .first()
                )
                if row is not None:
                    enqueued_job_id = str(row.job_id)
            finally:
                db_session.close()
            if enqueued_job_id is None:
                time.sleep(0.05)
        testbase.assert_equal(enqueued_job_id is not None, True)

        # Have the worker claim the job, then go silent.
        db_session = factory()
        try:
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
        finally:
            db_session.close()
        _stamp_heartbeat(
            factory=factory, worker_id=worker_id,
            when=datetime.now(timezone.utc) - timedelta(seconds=300),
        )

        # Run the sweeper synchronously — fails the in-flight job.
        result = app.stale_worker_sweeper.run_one_pass()
        testbase.assert_equal(
            result.workers_marked_offline, [worker_id],
        )
        testbase.assert_equal(result.jobs_failed, [enqueued_job_id])

        # The flow's wait_for_completion was woken by the
        # sweeper's wait-event broadcast — the submission
        # reaches a terminal state well under the 60s
        # workflow timeout.
        deadline = time.time() + 5.0
        terminal_state = None
        while time.time() < deadline:
            sub = app.flow_runtime.status(flow_id=flow_id)
            if sub is not None and sub.state in (
                FlowState.SUCCEEDED, FlowState.FAILED,
            ):
                terminal_state = sub.state
                break
            time.sleep(0.05)
        # Either FlowState terminal is acceptable here — the
        # property under test is "the flow stopped waiting",
        # not the engine's success-vs-fail mapping for a
        # non-zero task rc (that's a separate orchestration
        # concern). What matters is that the WorkerJob below
        # carries the sweeper's error_text.
        testbase.assert_equal(
            terminal_state in (
                FlowState.SUCCEEDED, FlowState.FAILED,
            ),
            True,
        )

        # The orphaned job carries the sweeper's diagnostic.
        db_session = factory()
        try:
            job_view = jobservice.read_job(
                db_session=db_session, job_id=enqueued_job_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(job_view.state, JobState.FAILED.value)
        testbase.assert_equal(
            "worker timed out" in (job_view.error_text or ""), True,
        )
    finally:
        app.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return
