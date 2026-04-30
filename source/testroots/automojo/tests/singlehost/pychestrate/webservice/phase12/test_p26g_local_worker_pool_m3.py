"""
.. module:: test_p26g_local_worker_pool_m3
    :synopsis: Tests for the in-process local worker pool.

Covers:

* :class:`LocalWorker` self-registers a ``local-process`` row in
  the registry on first start, and reuses the row across restarts.
* The worker actually executes ``run-command`` jobs via
  :func:`subprocess.run` and reports stdout / stderr / exit code.
* The worker exits its loop when an admin marks it ``DRAINING``.
* :class:`LocalWorkerPool` honours its ``size`` argument: a
  size-zero pool registers no workers, a size-N pool registers N
  uniquely-named workers.
* :func:`resolve_pool_config_from_env` reads the relevant env
  vars without ever touching the live ``os.environ``.
* End-to-end through :class:`PychestrateApplication`: a flow with
  a single ``RemoteCommand`` step lands on a local-pool worker
  and propagates the subprocess result back to the
  ``FlowSubmissionRecord``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile
import time

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
from automojo.pychestrate.webservice.workers.jobmodels import JobState
from automojo.pychestrate.webservice.workers.localworkerpool import (
    LocalWorker,
    LocalWorkerPool,
    resolve_pool_config_from_env,
)
from automojo.pychestrate.webservice.workers.models import (
    WorkerKind,
    WorkerStatus,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p26g_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def _wait_until(*, predicate, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate() is True:
            return True
        time.sleep(0.05)
    return False


def test_local_worker_self_registers_on_start():
    """
    **Feature: P26g local worker pool (M3)**
    **Property: A LocalWorker instance creates its own
    ``local-process`` row in the worker registry the first time
    it starts, with the supplied name.**
    """
    engine, factory, path = _build_engine_and_factory()
    worker = LocalWorker(
        name="solo",
        session_factory=factory,
        poll_interval_seconds=0.05,
        heartbeat_interval_seconds=60.0,
    )
    try:
        worker.start()
        testbase.assert_equal(worker.worker_id is not None, True)

        db_session = factory()
        try:
            view = worker_service.read_worker(
                db_session=db_session, worker_id=worker.worker_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.name, "solo")
        testbase.assert_equal(view.kind, WorkerKind.LOCAL_PROCESS.value)
    finally:
        worker.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return


def test_local_worker_reuses_row_on_restart():
    """
    **Feature: P26g local worker pool (M3)**
    **Property: A second LocalWorker instance with the same name
    inherits the existing registry row rather than colliding on
    the (project_id, name) unique constraint, so a service
    restart doesn't fragment the registry.**
    """
    engine, factory, path = _build_engine_and_factory()
    first = LocalWorker(
        name="recurring",
        session_factory=factory,
        poll_interval_seconds=0.05,
        heartbeat_interval_seconds=60.0,
    )
    try:
        first.start()
        first_id = first.worker_id
        first.shutdown(wait=True)

        second = LocalWorker(
            name="recurring",
            session_factory=factory,
            poll_interval_seconds=0.05,
            heartbeat_interval_seconds=60.0,
        )
        try:
            second.start()
            testbase.assert_equal(second.worker_id, first_id)
        finally:
            second.shutdown(wait=True)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_local_worker_executes_run_command_job():
    """
    **Feature: P26g local worker pool (M3)**
    **Property: The worker actually runs ``run-command`` jobs via
    subprocess and reports the stdout / exit code back through
    ``report_result``.**
    """
    engine, factory, path = _build_engine_and_factory()
    worker = LocalWorker(
        name="runner",
        session_factory=factory,
        poll_interval_seconds=0.05,
        heartbeat_interval_seconds=60.0,
    )
    try:
        worker.start()

        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={"command": "echo hello-from-pool"},
            )
        finally:
            db_session.close()

        def _is_done() -> bool:
            db_session = factory()
            try:
                view = jobservice.read_job(
                    db_session=db_session, job_id=enqueued.job_id,
                )
            finally:
                db_session.close()
            if view is None:
                return False
            rtnval = view.state in (
                JobState.SUCCEEDED.value, JobState.FAILED.value,
            )
            return rtnval

        completed = _wait_until(predicate=_is_done, timeout_seconds=5.0)
        testbase.assert_equal(completed, True)

        db_session = factory()
        try:
            view = jobservice.read_job(
                db_session=db_session, job_id=enqueued.job_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.state, JobState.SUCCEEDED.value)
        testbase.assert_equal(view.result_code, 0)
        testbase.assert_equal("hello-from-pool" in view.stdout, True)
    finally:
        worker.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return


def test_local_worker_reports_failure_for_unknown_kind():
    """
    **Feature: P26g local worker pool (M3)**
    **Property: A job whose ``kind`` is not ``run-command`` is
    failed cleanly with an explanatory ``error_text`` rather than
    crashing the worker thread.**
    """
    engine, factory, path = _build_engine_and_factory()
    worker = LocalWorker(
        name="kind-guard",
        session_factory=factory,
        poll_interval_seconds=0.05,
        heartbeat_interval_seconds=60.0,
    )
    try:
        worker.start()

        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                kind="copy-files",
                payload={"src": "/tmp", "dest": "/tmp"},
            )
        finally:
            db_session.close()

        def _is_done() -> bool:
            db_session = factory()
            try:
                view = jobservice.read_job(
                    db_session=db_session, job_id=enqueued.job_id,
                )
            finally:
                db_session.close()
            if view is None:
                return False
            rtnval = view.state in (
                JobState.SUCCEEDED.value, JobState.FAILED.value,
            )
            return rtnval

        testbase.assert_equal(
            _wait_until(predicate=_is_done, timeout_seconds=5.0), True,
        )

        db_session = factory()
        try:
            view = jobservice.read_job(
                db_session=db_session, job_id=enqueued.job_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.state, JobState.FAILED.value)
        testbase.assert_equal(
            "unsupported job kind" in (view.error_text or ""), True,
        )
    finally:
        worker.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return


def test_local_worker_exits_when_drained():
    """
    **Feature: P26g local worker pool (M3)**
    **Property: When an admin marks the worker DRAINING via
    ``drain_worker``, the worker's heartbeat path observes the
    DRAINING status and exits the loop.**
    """
    engine, factory, path = _build_engine_and_factory()
    worker = LocalWorker(
        name="drainable",
        session_factory=factory,
        poll_interval_seconds=0.05,
        # Force a heartbeat on every iteration so the drain
        # signal is observed promptly.
        heartbeat_interval_seconds=0.0,
    )
    try:
        worker.start()
        # Confirm the thread is alive and registered.
        testbase.assert_equal(worker.worker_id is not None, True)

        db_session = factory()
        try:
            worker_service.drain_worker(
                db_session=db_session, worker_id=worker.worker_id,
            )
        finally:
            db_session.close()

        def _exited() -> bool:
            rtnval = (
                worker._thread is not None
                and worker._thread.is_alive() is False
            )
            return rtnval

        testbase.assert_equal(
            _wait_until(predicate=_exited, timeout_seconds=3.0), True,
        )
    finally:
        worker.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return


def test_local_worker_pool_zero_size_registers_no_workers():
    """
    **Feature: P26g local worker pool (M3)**
    **Property: A size-zero pool starts (and shuts down) cleanly
    without inserting any workers — supports operators that
    want to disable in-process execution and rely solely on
    remote-machine workers.**
    """
    engine, factory, path = _build_engine_and_factory()
    pool = LocalWorkerPool(session_factory=factory, size=0)
    try:
        pool.start()
        testbase.assert_equal(pool.is_started, True)
        testbase.assert_equal(len(pool.workers), 0)

        db_session = factory()
        try:
            views = worker_service.list_workers(db_session=db_session)
        finally:
            db_session.close()
        testbase.assert_equal(len(views), 0)
    finally:
        pool.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return


def test_local_worker_pool_size_three_registers_three_uniquely_named():
    """
    **Feature: P26g local worker pool (M3)**
    **Property: A pool with size N registers N workers with
    distinct names so the (project_id, name) unique constraint
    is satisfied.**
    """
    engine, factory, path = _build_engine_and_factory()
    pool = LocalWorkerPool(
        session_factory=factory,
        size=3,
        base_name="trio",
        poll_interval_seconds=0.05,
        heartbeat_interval_seconds=60.0,
    )
    try:
        pool.start()
        testbase.assert_equal(len(pool.workers), 3)
        names = [w.name for w in pool.workers]
        testbase.assert_equal(len(set(names)), 3)
        for name in names:
            testbase.assert_equal(name.startswith("trio"), True)
    finally:
        pool.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return


def test_resolve_pool_config_from_env_reads_overrides_without_touching_real_env():
    """
    **Feature: P26g local worker pool (M3)**
    **Property: ``resolve_pool_config_from_env`` reads from the
    supplied ``environment`` mapping rather than the live
    ``os.environ``, so callers can construct deterministic
    config in tests.**
    """
    config = resolve_pool_config_from_env(environment={
        "PYCHESTRATE_LOCAL_WORKER_POOL_SIZE": "4",
        "PYCHESTRATE_LOCAL_WORKER_POOL_NAME": "raspi-host",
        "PYCHESTRATE_LOCAL_WORKER_POLL_INTERVAL": "0.25",
        "PYCHESTRATE_LOCAL_WORKER_HEARTBEAT_INTERVAL": "10",
        "PYCHESTRATE_LOCAL_WORKER_COMMAND_TIMEOUT": "120",
    })
    testbase.assert_equal(config["size"], 4)
    testbase.assert_equal(config["base_name"], "raspi-host")
    testbase.assert_equal(config["poll_interval_seconds"], 0.25)
    testbase.assert_equal(config["heartbeat_interval_seconds"], 10.0)
    testbase.assert_equal(
        config["default_command_timeout_seconds"], 120.0,
    )
    return


def test_resolve_pool_config_from_env_falls_back_to_defaults_for_garbage():
    """
    **Feature: P26g local worker pool (M3)**
    **Property: Garbage values in the env are coerced to
    defaults rather than crashing the bootstrap.**
    """
    config = resolve_pool_config_from_env(environment={
        "PYCHESTRATE_LOCAL_WORKER_POOL_SIZE": "not-a-number",
        "PYCHESTRATE_LOCAL_WORKER_POLL_INTERVAL": "also-bad",
    })
    testbase.assert_equal(config["size"], 1)
    testbase.assert_equal(config["poll_interval_seconds"], 0.5)
    return


def test_pychestrate_application_end_to_end_remote_command_via_local_pool():
    """
    **Feature: P26g local worker pool (M3)**
    **Property: When wired through the full
    :class:`PychestrateApplication` with an autostart pool of
    size 1, a flow with a single ``RemoteCommand`` step
    completes successfully because the local-pool worker picks
    up the queued job and executes it.**
    """
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p26g-test-pepper"))
    engine, factory, path = _build_engine_and_factory()
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
        local_worker_pool_size=1,
        local_worker_pool_autostart=True,
    )
    # Force fast polling so the test doesn't wait for the
    # default 0.5s interval.
    for w in app.local_worker_pool.workers:
        w._poll_interval_seconds = 0.05
    try:
        workflow_yaml = "\n".join([
            "name: p26g-pool-smoke",
            "environment: {}",
            "parameters: {}",
            "flow:",
            "  - task: probe",
            "    tasktype: automojo.pychestrate.webservice.orchestration.remotecommand@RemoteCommand",
            "    command: echo pool-ran",
            "    timeout_seconds: 10",
            "",
        ])
        flow_id = app.flow_runtime.submit_workflow_yaml(
            workflow_yaml=workflow_yaml,
        )

        def _is_terminal() -> bool:
            sub = app.flow_runtime.status(flow_id=flow_id)
            if sub is None:
                return False
            rtnval = sub.state in (
                FlowState.SUCCEEDED, FlowState.FAILED,
            )
            return rtnval

        testbase.assert_equal(
            _wait_until(predicate=_is_terminal, timeout_seconds=10.0),
            True,
        )

        submission = app.flow_runtime.status(flow_id=flow_id)
        testbase.assert_equal(submission.state, FlowState.SUCCEEDED)
        testbase.assert_equal(submission.result_code, 0)
    finally:
        app.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return
