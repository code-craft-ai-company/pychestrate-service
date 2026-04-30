"""
.. module:: test_p26f_job_queue_m3
    :synopsis: Tests for the worker-job queue + RemoteCommand task.

Covers:

* :func:`workers.jobservice.enqueue_job` /
  :func:`claim_next_job` / :func:`report_result` happy path.
* Selector matching on ``target_pod_name`` / ``target_kind``.
* :func:`workers.jobservice.wait_for_completion` returns the
  terminal view as soon as the worker reports a result.
* :func:`workers.jobservice.wait_for_completion` returns the
  pre-terminal view when ``timeout_seconds`` elapses.
* End-to-end :class:`RemoteCommand` invocation: a workflow with a
  single ``RemoteCommand`` step is submitted through a real
  :class:`FlowRuntime`; a stub worker thread polls the queue,
  echoes back stdout, and the flow completes with the worker's
  ``result_code`` propagated up to the submission record.
* The agent-facing REST endpoints
  (``/api/v1/workers/{id}/jobs/poll`` /
  ``/api/v1/workers/{id}/jobs/{job_id}/result``) round-trip a job
  through the full middleware pipeline.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging
import os
import tempfile
import threading
import time

from typing import Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.webworks.authentication.core import (
    AuthenticationContext,
    Principal,
)
from automojo.webworks.routing.request import Request

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)

from automojo.pychestrate.webservice.orchestration.flowruntime import (
    FlowRuntime,
    FlowState,
)
from automojo.pychestrate.webservice.orchestration.remotecommand import (
    RemoteCommand,
    set_session_factory,
)
from automojo.pychestrate.webservice.workers import jobservice
from automojo.pychestrate.webservice.workers import service as worker_service
from automojo.pychestrate.webservice.workers.jobmodels import JobState
from automojo.pychestrate.webservice.workers.models import (
    WorkerKind,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p26f_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def _register_worker(
        *,
        factory: sessionmaker,
        name: str,
        kind: WorkerKind,
        attributes: Optional[dict] = None,
    ) -> str:
    db_session = factory()
    try:
        view = worker_service.register_worker(
            db_session=db_session,
            name=name,
            kind=kind,
            attributes=attributes,
        )
    finally:
        db_session.close()
    rtnval = view.worker_id
    return rtnval


def test_enqueue_claim_report_round_trip():
    """
    **Feature: P26f job queue (M3)**
    **Property: A job enqueued by the service flows through the
    full PENDING -> CLAIMED -> SUCCEEDED state machine when a
    matching worker claims it and reports a zero result code.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(
            factory=factory,
            name="local-worker",
            kind=WorkerKind.LOCAL_PROCESS,
        )

        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={"command": "echo hi"},
            )
        finally:
            db_session.close()
        testbase.assert_equal(enqueued.state, JobState.PENDING.value)

        db_session = factory()
        try:
            claimed = jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(claimed is not None, True)
        testbase.assert_equal(claimed.state, JobState.CLAIMED.value)
        testbase.assert_equal(claimed.worker_id, worker_id)
        testbase.assert_equal(claimed.job_id, enqueued.job_id)

        db_session = factory()
        try:
            reported = jobservice.report_result(
                db_session=db_session,
                worker_id=worker_id,
                job_id=enqueued.job_id,
                result_code=0,
                stdout="hi\n",
                stderr="",
            )
        finally:
            db_session.close()
        testbase.assert_equal(reported.state, JobState.SUCCEEDED.value)
        testbase.assert_equal(reported.result_code, 0)
        testbase.assert_equal(reported.stdout, "hi\n")
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_claim_skips_jobs_targeted_at_other_pods():
    """
    **Feature: P26f job queue (M3)**
    **Property: A job that names a specific target_pod_name is
    only claimable by the worker whose registered name matches
    that selector; other workers see the queue as empty.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_a = _register_worker(
            factory=factory, name="raspi-01",
            kind=WorkerKind.REMOTE_MACHINE,
        )
        worker_b = _register_worker(
            factory=factory, name="raspi-02",
            kind=WorkerKind.REMOTE_MACHINE,
        )

        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={"command": "uname -a"},
                target_pod_name="raspi-02",
            )
        finally:
            db_session.close()

        # raspi-01 cannot pick up a job pinned to raspi-02.
        db_session = factory()
        try:
            claim_a = jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_a,
            )
        finally:
            db_session.close()
        testbase.assert_equal(claim_a, None)

        # raspi-02 picks it up.
        db_session = factory()
        try:
            claim_b = jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_b,
            )
        finally:
            db_session.close()
        testbase.assert_equal(claim_b is not None, True)
        testbase.assert_equal(claim_b.job_id, enqueued.job_id)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_claim_respects_target_kind_selector():
    """
    **Feature: P26f job queue (M3)**
    **Property: A job that selects ``target_kind=remote-machine``
    is not claimable by a ``local-process`` worker.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        local_worker = _register_worker(
            factory=factory,
            name="loopback",
            kind=WorkerKind.LOCAL_PROCESS,
        )
        remote_worker = _register_worker(
            factory=factory,
            name="raspi-99",
            kind=WorkerKind.REMOTE_MACHINE,
        )

        db_session = factory()
        try:
            jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={"command": "/bin/true"},
                target_kind=WorkerKind.REMOTE_MACHINE,
            )
        finally:
            db_session.close()

        db_session = factory()
        try:
            local_claim = jobservice.claim_next_job(
                db_session=db_session, worker_id=local_worker,
            )
        finally:
            db_session.close()
        testbase.assert_equal(local_claim, None)

        db_session = factory()
        try:
            remote_claim = jobservice.claim_next_job(
                db_session=db_session, worker_id=remote_worker,
            )
        finally:
            db_session.close()
        testbase.assert_equal(remote_claim is not None, True)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_wait_for_completion_returns_immediately_after_report():
    """
    **Feature: P26f job queue (M3)**
    **Property: ``wait_for_completion`` is woken by
    ``report_result`` via the module-level event registry and
    returns the terminal JobView well before its timeout
    deadline.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(
            factory=factory,
            name="quick-worker",
            kind=WorkerKind.LOCAL_PROCESS,
        )

        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={"command": "echo done"},
            )
        finally:
            db_session.close()

        # Background thread waits for completion.
        result_holder: dict = {}

        def _waiter() -> None:
            view = jobservice.wait_for_completion(
                session_factory=factory,
                job_id=enqueued.job_id,
                timeout_seconds=5.0,
                poll_interval_seconds=0.05,
            )
            result_holder["view"] = view
            return

        waiter_thread = threading.Thread(target=_waiter, daemon=True)
        waiter_thread.start()

        # Give the waiter a chance to register its event before we
        # report — without this the test passes too, but the wake-up
        # path is the one we want to exercise.
        time.sleep(0.1)

        db_session = factory()
        try:
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
            jobservice.report_result(
                db_session=db_session,
                worker_id=worker_id,
                job_id=enqueued.job_id,
                result_code=0,
                stdout="done",
            )
        finally:
            db_session.close()

        waiter_thread.join(timeout=4.0)
        testbase.assert_equal(waiter_thread.is_alive(), False)
        view = result_holder.get("view", None)
        testbase.assert_equal(view is not None, True)
        testbase.assert_equal(view.state, JobState.SUCCEEDED.value)
        testbase.assert_equal(view.result_code, 0)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_wait_for_completion_times_out_when_no_report():
    """
    **Feature: P26f job queue (M3)**
    **Property: ``wait_for_completion`` returns the (still
    pre-terminal) JobView on timeout rather than blocking
    indefinitely; the caller can read the ``state`` to detect a
    timed-out job.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={"command": "sleep 60"},
            )
        finally:
            db_session.close()

        deadline_before = time.time()
        view = jobservice.wait_for_completion(
            session_factory=factory,
            job_id=enqueued.job_id,
            timeout_seconds=0.3,
            poll_interval_seconds=0.05,
        )
        deadline_after = time.time()
        # Should have respected the deadline (allow 1.0s slack for
        # heavily loaded CI hosts).
        testbase.assert_equal(deadline_after - deadline_before < 1.5, True)
        testbase.assert_equal(view is not None, True)
        testbase.assert_equal(
            view.state in (
                JobState.PENDING.value,
                JobState.CLAIMED.value,
                JobState.RUNNING.value,
            ),
            True,
        )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_remote_command_end_to_end_through_flow_runtime():
    """
    **Feature: P26f job queue (M3)**
    **Property: A workflow whose only step is a RemoteCommand
    task enqueues a job, blocks until a worker reports a result,
    and propagates the worker's exit code into the
    FlowSubmissionRecord.**
    """
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p26f-test-pepper"))
    engine, factory, path = _build_engine_and_factory()
    runtime = FlowRuntime(max_workers=2, session_factory=factory)
    stop_event = threading.Event()

    worker_id = _register_worker(
        factory=factory,
        name="loopback-worker",
        kind=WorkerKind.LOCAL_PROCESS,
    )

    # Stub worker: poll the queue and immediately report a fake
    # result with stdout. Mimics what the in-process worker pool
    # (P26 #6c) and the remote agent script (P26 #6d) will do.
    def _fake_worker_loop() -> None:
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
            command = claimed.payload.get("command", "")
            db_session = factory()
            try:
                jobservice.report_result(
                    db_session=db_session,
                    worker_id=worker_id,
                    job_id=claimed.job_id,
                    result_code=0,
                    stdout="ran: {0}\n".format(command),
                    stderr="",
                )
            finally:
                db_session.close()
        return

    worker_thread = threading.Thread(
        target=_fake_worker_loop, daemon=True,
    )
    worker_thread.start()

    workflow_yaml = "\n".join([
        "name: p26f-remote-command-smoke",
        "environment: {}",
        "parameters: {}",
        "flow:",
        "  - task: probe",
        "    tasktype: automojo.pychestrate.webservice.orchestration.remotecommand@RemoteCommand",
        "    command: echo hello",
        "    timeout_seconds: 5",
        "",
    ])

    try:
        flow_id = runtime.submit_workflow_yaml(
            workflow_yaml=workflow_yaml,
        )

        # Poll the runtime cache until terminal.
        deadline = time.time() + 8.0
        terminal_state: Optional[FlowState] = None
        while time.time() < deadline:
            submission = runtime.status(flow_id=flow_id)
            if submission is None:
                time.sleep(0.05)
                continue
            if submission.state in (FlowState.SUCCEEDED, FlowState.FAILED):
                terminal_state = submission.state
                break
            time.sleep(0.05)
        testbase.assert_equal(
            terminal_state, FlowState.SUCCEEDED,
        )

        # The submission's persisted result_code matches what the
        # stub worker reported; this is the contract RemoteCommand
        # owes the engine.
        submission = runtime.status(flow_id=flow_id)
        testbase.assert_equal(submission is not None, True)
        testbase.assert_equal(submission.result_code, 0)
        testbase.assert_equal(submission.error_text, None)
    finally:
        stop_event.set()
        worker_thread.join(timeout=2.0)
        runtime.shutdown(wait=True)
        # Make sure RemoteCommand's thread-local doesn't leak out
        # of this test into others.
        set_session_factory(factory=None)
        engine.dispose()
        os.unlink(path)
    return


def test_remote_command_returns_one_when_session_factory_unbound():
    """
    **Feature: P26f job queue (M3)**
    **Property: When invoked outside a FlowRuntime worker (no
    session_factory bound on the calling thread), RemoteCommand
    fails the step with a non-zero exit code rather than
    crashing the engine, so a misconfiguration produces a clean
    flow failure.**
    """
    # Make sure no leakage from a previous test left a factory
    # bound on this thread.
    set_session_factory(factory=None)

    logger = logging.getLogger("p26f.remote_command_unbound")
    task = RemoteCommand(
        ordinal="1",
        label="probe",
        task_info={"command": "echo hi"},
        logger=logger,
    )
    rtnval = task.perform_task(
        environment={}, parameters=None, flowstate={},
    )
    testbase.assert_equal(rtnval, 1)
    return


def _admin_context() -> AuthenticationContext:
    return AuthenticationContext(
        principal=Principal(
            identifier="00000000-0000-4000-8000-00000000f000",
            display_name="Admin",
            roles={"system-admin"},
        ),
        scheme="test-injection",
    )


def _wrap(*, app, context: Optional[AuthenticationContext]) -> None:
    original = app.dispatcher.dispatch

    def _wrapped(*, request):
        request.auth = context
        rtnval = original(request=request)
        return rtnval

    app.dispatcher.dispatch = _wrapped
    return


def test_poll_and_result_endpoints_round_trip_via_http():
    """
    **Feature: P26f job queue (M3)**
    **Property: Agents can poll for jobs and report results
    through ``POST /api/v1/workers/{id}/jobs/poll`` and ``POST
    /api/v1/workers/{id}/jobs/{job_id}/result`` — the full HTTP
    middleware pipeline (DbSession, AccessPolicy, JSON encode)
    moves the job through the same state machine the service
    layer drives.**
    """
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p26f-http-pepper"))
    engine, factory, path = _build_engine_and_factory()
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )
    _wrap(app=app, context=_admin_context())
    try:
        register = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/register",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "name": "http-worker", "kind": "local-process",
            }).encode(),
        ))
        testbase.assert_equal(register.status_code, 201)
        worker_id = json.loads(register.body.decode())["worker_id"]

        # Empty queue.
        empty_poll = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/jobs/poll".format(worker_id),
            body=b"",
        ))
        testbase.assert_equal(empty_poll.status_code, 200)
        empty_body = json.loads(empty_poll.body.decode())
        testbase.assert_equal(empty_body, {"job": None})

        # Enqueue directly via the service layer (the admin doesn't
        # have a public enqueue endpoint yet — that lives behind the
        # flows surface).
        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={"command": "/bin/true"},
            )
        finally:
            db_session.close()

        # Worker polls and gets the job.
        poll = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/jobs/poll".format(worker_id),
            body=b"",
        ))
        testbase.assert_equal(poll.status_code, 200)
        polled = json.loads(poll.body.decode())
        testbase.assert_equal(polled["job"] is not None, True)
        testbase.assert_equal(
            polled["job"]["job_id"], enqueued.job_id,
        )
        testbase.assert_equal(
            polled["job"]["state"], JobState.CLAIMED.value,
        )

        # Worker reports result.
        report = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/jobs/{1}/result".format(
                worker_id, enqueued.job_id,
            ),
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "result_code": 0, "stdout": "ok\n", "stderr": "",
            }).encode(),
        ))
        testbase.assert_equal(report.status_code, 200)
        reported = json.loads(report.body.decode())
        testbase.assert_equal(reported["state"], JobState.SUCCEEDED.value)
        testbase.assert_equal(reported["result_code"], 0)
        testbase.assert_equal(reported["stdout"], "ok\n")
    finally:
        app.flow_runtime.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return
