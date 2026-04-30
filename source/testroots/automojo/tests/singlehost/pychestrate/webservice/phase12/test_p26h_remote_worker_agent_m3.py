"""
.. module:: test_p26h_remote_worker_agent_m3
    :synopsis: Tests for the standalone remote-worker agent script.

The agent (``scripts/worker.py``) talks to the running service over
HTTP. To keep these tests hermetic — and avoid binding a real TCP
port — we monkey-patch the agent's ``_do_request`` helper so it
dispatches against an in-memory ``PychestrateApplication`` instance.
That preserves the full middleware pipeline (DbSession, bearer
auth, AccessPolicy) while skipping ``urllib.request.urlopen``.

Covers:

* ``_execute_job_command`` runs a real subprocess and surfaces
  stdout / exit code.
* ``_execute_job_command`` honours a job's ``timeout_seconds``.
* ``redeem_bearer_token`` round-trips through the dispatcher.
* ``register_worker`` self-creates a ``remote-machine`` row and
  ``poll_next_job`` / ``report_result`` round-trip through the
  dispatcher under the bearer token.
* ``WorkerAgent.run(drain_after_one=True)`` claims a queued job,
  executes it, reports the result, and exits.
* ``WorkerAgent`` exits its loop when the registry status flips
  to ``draining`` between iterations.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import importlib.util
import io
import json
import os
import sys
import tempfile
import time

from typing import Any, Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

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
from automojo.pychestrate.webservice.workers import jobservice
from automojo.pychestrate.webservice.workers.jobmodels import JobState

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _import_worker_module():
    """
        Load ``scripts/worker.py`` as a module. The script lives
        outside any importable package, so we use the spec/loader
        dance.
    """
    repo_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "..", "..", "..", "..", "..",
        ),
    )
    spec = importlib.util.spec_from_file_location(
        "scripts_worker",
        os.path.join(repo_root, "scripts", "worker.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _import_bootstrap_module():
    repo_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "..", "..", "..", "..", "..",
        ),
    )
    spec = importlib.util.spec_from_file_location(
        "scripts_bootstrapadmin",
        os.path.join(repo_root, "scripts", "bootstrapadmin.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_app() -> Tuple[PychestrateApplication, str, sessionmaker]:
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p26h-test-pepper"))
    fd, path = tempfile.mkstemp(prefix="pych_p26h_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )
    return app, path, factory


def _seed_enrollment_secret(*, app, factory) -> Tuple[str, str]:
    """
        Seed an admin + project + enrollment token. Returns
        ``(secret, project_id)``.
    """
    bootstrap = _import_bootstrap_module()

    db_session = factory()
    try:
        bootstrap._sync_role_catalog(db_session=db_session)
        user_id = bootstrap._ensure_user(
            db_session=db_session,
            login_name="admin-26h",
            primary_email="admin-26h@example.com",
            display_name="Admin",
            timezone_name="UTC",
        )
        bootstrap._ensure_admin_binding(
            db_session=db_session, user_id=user_id,
        )
        bootstrap._ensure_local_password(
            db_session=db_session,
            user_id=user_id,
            password="ChangeMe!",
        )
        db_session.commit()

        from automojo.pychestrate.webservice.projects import service as ps
        project = ps.create_project(
            db_session=db_session,
            slug="lab",
            display_name="Lab",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=user_id,
        )
        project_id = str(project.project_id)

        from automojo.pychestrate.webservice.clients.enrollment.service import (
            issue_enrollment_token,
        )
        issued = issue_enrollment_token(
            db_session=db_session,
            project_id=project_id,
            pod_name="raspi-01",
            ttl_seconds=600,
            one_shot=False,
            issued_by=user_id,
        )
        db_session.commit()
        secret = issued.secret
    finally:
        db_session.close()
    return secret, project_id


def _install_dispatcher_transport(*, worker_module, app) -> None:
    """
        Replace ``worker_module._do_request`` with one that
        dispatches against an in-memory app. Keeps the test
        hermetic (no real TCP) while preserving the full
        middleware pipeline.
    """
    def _dispatch(
            *,
            base_url: str,
            method: str,
            path: str,
            bearer_token: Optional[str],
            json_body: Optional[Any] = None,
            timeout_seconds: float = 30.0,
        ) -> Tuple[int, bytes]:
        headers = {}
        if bearer_token is not None:
            headers["Authorization"] = "Bearer {0}".format(bearer_token)
        body_bytes: Optional[bytes] = None
        if json_body is not None:
            body_bytes = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif method != "GET":
            # webworks expects a non-None body for POST/DELETE in
            # some cases; an empty bytestring is fine.
            body_bytes = b""
        request = Request(
            method=method,
            path=path,
            headers=headers,
            body=body_bytes,
        )
        response = app.dispatcher.dispatch(request=request)
        rtnval = (int(response.status_code), response.body)
        return rtnval

    worker_module._do_request = _dispatch
    return


def test_execute_job_command_runs_real_subprocess():
    """
    **Feature: P26h remote worker agent (M3)**
    **Property: ``_execute_job_command`` runs the supplied shell
    command, captures stdout, and returns the actual exit code.**
    """
    worker_module = _import_worker_module()
    rc, stdout, stderr, err = worker_module._execute_job_command(
        command="echo agent-stdout && exit 7",
        timeout_seconds=5.0,
    )
    testbase.assert_equal(rc, 7)
    testbase.assert_equal("agent-stdout" in stdout, True)
    testbase.assert_equal(err, None)
    testbase.assert_equal(stderr, "")
    return


def test_execute_job_command_honours_timeout():
    """
    **Feature: P26h remote worker agent (M3)**
    **Property: A command that exceeds ``timeout_seconds`` is
    killed, gets a non-zero result code, and surfaces an
    ``error_text`` so the report_result path can persist it.**
    """
    worker_module = _import_worker_module()
    rc, _stdout, _stderr, err = worker_module._execute_job_command(
        command="sleep 5",
        timeout_seconds=0.2,
    )
    testbase.assert_equal(rc, 1)
    testbase.assert_equal(err is not None, True)
    testbase.assert_equal("timed out" in err, True)
    return


def test_redeem_bearer_token_via_dispatcher():
    """
    **Feature: P26h remote worker agent (M3)**
    **Property: ``redeem_bearer_token`` POSTs to the public
    ``/api/v1/enrollment-tokens/redeem`` endpoint and pulls
    ``bearer_token`` out of the response. The dispatcher proves
    the request shape matches the server contract.**
    """
    worker_module = _import_worker_module()
    app, db_path, factory = _build_app()
    _install_dispatcher_transport(worker_module=worker_module, app=app)
    try:
        secret, _project_id = _seed_enrollment_secret(
            app=app, factory=factory,
        )
        bearer = worker_module.redeem_bearer_token(
            base_url="http://test",
            secret=secret,
            pod_name="raspi-01",
            agent_version="1.0.0",
        )
        testbase.assert_equal(len(bearer) > 0, True)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return


def test_register_poll_report_round_trip_via_dispatcher():
    """
    **Feature: P26h remote worker agent (M3)**
    **Property: With a redeem-minted bearer, the agent's
    ``register_worker`` / ``poll_next_job`` / ``report_result``
    helpers drive a full job through the queue under the same
    middleware pipeline a real HTTP request would hit.**
    """
    worker_module = _import_worker_module()
    app, db_path, factory = _build_app()
    _install_dispatcher_transport(worker_module=worker_module, app=app)
    try:
        secret, _project_id = _seed_enrollment_secret(
            app=app, factory=factory,
        )
        bearer = worker_module.redeem_bearer_token(
            base_url="http://test",
            secret=secret,
            pod_name="raspi-01",
        )

        worker_id = worker_module.register_worker(
            base_url="http://test",
            bearer_token=bearer,
            worker_name="raspi-01",
            attributes={"host": "raspi-01"},
        )
        testbase.assert_equal(len(worker_id) > 0, True)

        # Empty queue => poll returns None.
        empty = worker_module.poll_next_job(
            base_url="http://test",
            bearer_token=bearer,
            worker_id=worker_id,
        )
        testbase.assert_equal(empty, None)

        # Enqueue via the service so we can exercise the agent
        # path end-to-end. Pin to the worker's pod_name selector
        # so we know it lands here.
        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={"command": "echo agent-ok"},
                target_pod_name="raspi-01",
            )
        finally:
            db_session.close()

        polled = worker_module.poll_next_job(
            base_url="http://test",
            bearer_token=bearer,
            worker_id=worker_id,
        )
        testbase.assert_equal(polled is not None, True)
        testbase.assert_equal(polled["job_id"], enqueued.job_id)

        ok = worker_module.report_result(
            base_url="http://test",
            bearer_token=bearer,
            worker_id=worker_id,
            job_id=enqueued.job_id,
            result_code=0,
            stdout="agent-ok\n",
            stderr="",
            error_text=None,
        )
        testbase.assert_equal(ok, True)

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
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return


def test_worker_agent_drain_loop_processes_one_job():
    """
    **Feature: P26h remote worker agent (M3)**
    **Property: ``WorkerAgent.run(drain_after_one=True)`` claims
    a single queued job, runs the subprocess, reports the
    result, and exits with code 0.**
    """
    worker_module = _import_worker_module()
    app, db_path, factory = _build_app()
    _install_dispatcher_transport(worker_module=worker_module, app=app)
    try:
        secret, _project_id = _seed_enrollment_secret(
            app=app, factory=factory,
        )
        bearer = worker_module.redeem_bearer_token(
            base_url="http://test",
            secret=secret,
            pod_name="raspi-01",
        )
        worker_id = worker_module.register_worker(
            base_url="http://test",
            bearer_token=bearer,
            worker_name="raspi-01",
            attributes={"host": "raspi-01"},
        )

        # Pre-enqueue a job so the drain pass has something to do.
        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={
                    "command": "echo drain-pass",
                    "timeout_seconds": 5,
                },
                target_pod_name="raspi-01",
            )
        finally:
            db_session.close()

        log_buffer = io.StringIO()
        agent = worker_module.WorkerAgent(
            base_url="http://test",
            bearer_token=bearer,
            worker_id=worker_id,
            poll_interval_seconds=0.05,
            heartbeat_interval_seconds=0.0,
            log_writer=log_buffer,
        )
        exit_code = agent.run(drain_after_one=True)
        testbase.assert_equal(exit_code, 0)

        db_session = factory()
        try:
            view = jobservice.read_job(
                db_session=db_session, job_id=enqueued.job_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.state, JobState.SUCCEEDED.value)
        testbase.assert_equal(view.result_code, 0)
        testbase.assert_equal("drain-pass" in view.stdout, True)
        # The agent's own log mentions the job it ran.
        testbase.assert_equal(
            "worker.job.start" in log_buffer.getvalue(), True,
        )
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return


def test_worker_agent_exits_when_status_drains_between_polls():
    """
    **Feature: P26h remote worker agent (M3)**
    **Property: When the registry flips the worker's status to
    DRAINING (an admin issued ``POST /workers/{id}/drain``), the
    agent observes the new status on its next heartbeat and
    exits the loop with code 0.**
    """
    worker_module = _import_worker_module()
    app, db_path, factory = _build_app()
    _install_dispatcher_transport(worker_module=worker_module, app=app)
    try:
        secret, _project_id = _seed_enrollment_secret(
            app=app, factory=factory,
        )
        bearer = worker_module.redeem_bearer_token(
            base_url="http://test",
            secret=secret,
            pod_name="raspi-01",
        )
        worker_id = worker_module.register_worker(
            base_url="http://test",
            bearer_token=bearer,
            worker_name="raspi-01",
            attributes={"host": "raspi-01"},
        )

        # Drain the worker before the agent loop starts so that
        # on the very first heartbeat the agent observes
        # status=draining and exits cleanly.
        from automojo.pychestrate.webservice.workers import service as ws
        db_session = factory()
        try:
            ws.drain_worker(db_session=db_session, worker_id=worker_id)
        finally:
            db_session.close()

        log_buffer = io.StringIO()
        agent = worker_module.WorkerAgent(
            base_url="http://test",
            bearer_token=bearer,
            worker_id=worker_id,
            poll_interval_seconds=0.05,
            heartbeat_interval_seconds=0.0,
            log_writer=log_buffer,
        )
        start = time.time()
        exit_code = agent.run(drain_after_one=False)
        elapsed = time.time() - start
        testbase.assert_equal(exit_code, 0)
        # Should exit promptly via the drain check, not poll for
        # any meaningful duration.
        testbase.assert_equal(elapsed < 2.0, True)
        testbase.assert_equal(
            "draining" in log_buffer.getvalue(), True,
        )
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return
