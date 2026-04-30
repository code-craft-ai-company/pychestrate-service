"""
.. module:: test_p24k_flow_persistence_m3
    :synopsis: Tests for FlowSubmissionRecord persistence + log endpoint.

Exercises :class:`FlowRuntime` against a shared file-backed SQLite
engine so worker threads (which open their own session) see the same
DB state as the main thread. Verifies that:

* every submission writes a :class:`FlowSubmissionRecord` row;
* state transitions update the row;
* terminal SUCCEEDED / FAILED transitions populate completed_at,
  result_code, and log_text;
* a fresh runtime backed by the same DB recovers historical
  submissions on init;
* the new ``GET /api/v1/flows/{id}/log`` endpoint returns the
  captured log.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import tempfile
import time

from typing import Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.webworks.authentication.core import (
    AuthenticationContext,
    Principal,
)
from automojo.webworks.routing.request import Request

from automojo.pychestrate.webservice.orchestration.flowruntime import (
    FlowRuntime,
    FlowState,
)
from automojo.pychestrate.webservice.orchestration.flowsubmissionrecord import (
    FlowSubmissionRecord,
)
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


_ADMIN_AUTH_CONTEXT = AuthenticationContext(
    principal=Principal(
        identifier="00000000-0000-4000-8000-00000000a000",
        display_name="Test Admin",
        roles={"system-admin"},
    ),
    scheme="test-injection",
)


def _wrap_app_with_admin_auth(app: PychestrateApplication) -> None:
    """
        Wrap ``app.dispatcher.dispatch`` so every test request lands
        with a pre-populated system-admin AuthenticationContext on
        ``request.auth``. Mirrors the helper in
        :mod:`test_p24h_end_to_end_application_smoke_m3` so gated
        endpoints (POST /api/v1/flows) accept the request.
    """
    original = app.dispatcher.dispatch

    def _wrapped(*, request):
        request.auth = _ADMIN_AUTH_CONTEXT
        rtnval = original(request=request)
        return rtnval

    app.dispatcher.dispatch = _wrapped
    return


_SMOKE_WORKFLOW_YAML = """
name: persisted-smoke
environment: {}
parameters: {}
flow:
  - task: noop
    tasktype: automojo.taskplus.tasks.runcommand@RunCommand
    command: echo persistedhello
"""


def _make_engine() -> Tuple[object, str]:
    """
        Build a file-backed SQLite engine with the phase-1 schema
        applied. File-backed so worker threads share state with the
        main thread (in-memory SQLite would give each connection its
        own database).

        :returns: ``(engine, path)`` — caller is responsible for
                  unlinking the file.
    """
    fd, path = tempfile.mkstemp(prefix="pych_p24k_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    rtnval = (engine, path)
    return rtnval


def _wait_terminal(*, runtime: FlowRuntime, flow_id: str, deadline_s: float = 5.0) -> str:
    """
        Poll until the submission reaches a terminal state, capped at
        ``deadline_s`` seconds.

        :returns: The terminal state value, or the last observed
                  state when the deadline elapses.
    """
    end = time.time() + deadline_s
    while time.time() < end:
        snapshot = runtime.status(flow_id=flow_id)
        if snapshot is None:
            time.sleep(0.05)
            continue
        if snapshot.state in (FlowState.SUCCEEDED, FlowState.FAILED):
            return snapshot.state.value
        time.sleep(0.05)
    return snapshot.state.value if snapshot is not None else "MISSING"


def test_persistent_runtime_writes_flow_submission_row():
    """
    **Feature: P24k flow persistence (M3)**
    **Property: Submitting a workflow against a persistent runtime
    creates a FlowSubmissionRecord row whose state cycles through
    PENDING -> RUNNING -> SUCCEEDED, with started_at, completed_at,
    result_code=0, and log_text populated by the terminal write.**
    """
    engine, path = _make_engine()
    factory = sessionmaker(bind=engine)
    runtime = FlowRuntime(session_factory=factory)
    try:
        flow_id = runtime.submit_workflow_yaml(
            workflow_yaml=_SMOKE_WORKFLOW_YAML,
            actor_user_id=None,
        )
        terminal = _wait_terminal(runtime=runtime, flow_id=flow_id)
        testbase.assert_equal(terminal, "SUCCEEDED")

        # Read the row directly to confirm persistence.
        check_session = factory()
        try:
            record = (
                check_session.query(FlowSubmissionRecord)
                .filter(FlowSubmissionRecord.flow_id == flow_id)
                .first()
            )
            testbase.assert_equal(record is None, False)
            testbase.assert_equal(record.state, "SUCCEEDED")
            testbase.assert_equal(record.result_code, 0)
            testbase.assert_equal(record.started_at is None, False)
            testbase.assert_equal(record.completed_at is None, False)
            testbase.assert_equal(record.workflow_yaml.find("persisted-smoke") >= 0, True)
        finally:
            check_session.close()
    finally:
        runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_runtime_recovers_historical_submissions_on_init():
    """
    **Feature: P24k flow persistence (M3)**
    **Property: A second FlowRuntime constructed against the same DB
    returns the prior submission via list_submissions and status,
    proving submissions survive a process restart.**
    """
    engine, path = _make_engine()
    factory = sessionmaker(bind=engine)

    first_runtime = FlowRuntime(session_factory=factory)
    try:
        flow_id = first_runtime.submit_workflow_yaml(
            workflow_yaml=_SMOKE_WORKFLOW_YAML,
        )
        terminal = _wait_terminal(runtime=first_runtime, flow_id=flow_id)
        testbase.assert_equal(terminal, "SUCCEEDED")
    finally:
        first_runtime.shutdown(wait=True)

    # Simulate a fresh process boot.
    second_runtime = FlowRuntime(session_factory=factory)
    try:
        listed = second_runtime.list_submissions()
        ids = [s.flow_id for s in listed]
        testbase.assert_equal(flow_id in ids, True)

        snapshot = second_runtime.status(flow_id=flow_id)
        testbase.assert_equal(snapshot is None, False)
        testbase.assert_equal(snapshot.state, FlowState.SUCCEEDED)
    finally:
        second_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_log_endpoint_returns_captured_text():
    """
    **Feature: P24k flow persistence (M3)**
    **Property: GET /api/v1/flows/{id}/log returns 200 with the
    captured log_text once the submission completes. The log
    contains the RunCommand-emitted RESULT CODE line.**
    """
    reset_phase1_runtime()
    engine, path = _make_engine()
    factory = sessionmaker(bind=engine)

    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )
    _wrap_app_with_admin_auth(app=app)
    try:
        submit_request = Request(
            method="POST",
            path="/api/v1/flows",
            headers={"Content-Type": "application/yaml"},
            body=_SMOKE_WORKFLOW_YAML.encode("utf-8"),
        )
        submit_response = app.dispatcher.dispatch(request=submit_request)
        testbase.assert_equal(submit_response.status_code, 202)
        flow_id = json.loads(submit_response.body.decode("utf-8"))["flow_id"]

        terminal = _wait_terminal(
            runtime=app.flow_runtime, flow_id=flow_id, deadline_s=5.0,
        )
        testbase.assert_equal(terminal, "SUCCEEDED")

        log_request = Request(
            method="GET",
            path="/api/v1/flows/{0}/log".format(flow_id),
        )
        log_response = app.dispatcher.dispatch(request=log_request)
        testbase.assert_equal(log_response.status_code, 200)
        body = json.loads(log_response.body.decode("utf-8"))
        testbase.assert_equal(body["flow_id"], flow_id)
        log_text = body["log_text"]
        testbase.assert_equal(isinstance(log_text, str), True)
        testbase.assert_equal("RESULT CODE: 0" in log_text, True)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_log_endpoint_returns_404_for_unknown_flow():
    """
    **Feature: P24k flow persistence (M3)**
    **Property: GET /api/v1/flows/{unknown}/log surfaces 404 the
    same way the status endpoint does.**
    """
    reset_phase1_runtime()
    engine, path = _make_engine()
    factory = sessionmaker(bind=engine)

    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )
    _wrap_app_with_admin_auth(app=app)
    try:
        request = Request(
            method="GET",
            path="/api/v1/flows/00000000-0000-0000-0000-000000000000/log",
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 404)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return
