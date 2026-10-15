"""
.. module:: test_p19c_run_lifecycle_wiring_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end run-lifecycle wiring tests.

.. moduleauthor:: Code Craft AI LLC

Proves the run state machine is driven through its full lifecycle
by the REST ingest endpoints and the timer-wheel timeout.

Scenarios:
* dispatch-ack advances DISPATCHING -> DISPATCHED.
* progress (first): DISPATCHED -> RUNNING (RECEIPT_RECORDED then
  FIRST_PROGRESS via the tolerant note_progress walker).
* progress (subsequent): RUNNING self-loop (PROGRESS_OBSERVED).
* testbase results/complete with terminal_outcome=success:
  RUNNING -> COMPLETED.
* testbase results/complete with terminal_outcome=failure:
  RUNNING -> FAILED.
* Full chain ack -> progress -> results reaches COMPLETED.
* cancel -> CANCEL_REQUESTED; cancel on terminal run -> 409.
* timer-wheel timeout DISPATCHING -> DISPATCH_UNCONFIRMED.
* advance helpers are tolerant: already-terminal rows are no-ops.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.jobs.dispatch.receipt.timer_wheel import (
    TimerEntry,
    TimerWheel,
    reset_default_timer_wheel_for_testing,
)
from ccai.pychestrate.webservice.jobs.run.state import (
    RunEvent,
    RunState,
    TerminalStateError,
    create_run,
    is_terminal,
    transition,
)
from ccai.pychestrate.webservice.jobs.run.state.advance import (
    advance_to_dispatched,
    advance_to_terminal,
    note_progress,
)
from ccai.pychestrate.webservice.jobs.run.state.machine import (
    request_cancel as run_state_request_cancel,
)
from ccai.pychestrate.webservice.jobs.run.state import repository as run_repo
from ccai.pychestrate.webservice.messaging.event_bus import (
    reset_for_testing as reset_event_bus,
)
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

PROJECT_UUID = "00000000-0000-4000-8000-000000000999"
CLIENT_CN = "pod-client-cert"


# ---------------------------------------------------------------------------
# Fake request builder
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        body: Any = None,
        db_session: Optional[Any] = None,
        mtls_client_cn: Optional[str] = None,
        auth_principal: Optional[Any] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self._body: Any = body
        self.db_session: Optional[Any] = db_session
        if mtls_client_cn is not None:
            self.mtls_client_cn: str = mtls_client_cn
        if auth_principal is not None:
            self.auth_principal: Any = auth_principal
        return

    def json(self) -> Any:
        return self._body


class _FakeAttempt:
    def __init__(
        self,
        *,
        run_id: str,
        project_id: str = PROJECT_UUID
    ) -> None:
        self.attempt_id: str = "attempt-1"
        self.run_id: str = run_id
        self.project_id: str = project_id
        return


def _decode_body(response: Any) -> Any:
    """
        Decode the response body bytes as JSON.

        :param response: Webworks-style response object.

        :returns: Decoded value.
    """
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _prepare_state() -> None:
    """
        Reset the in-process bus before each test.

        :returns: None.
    """
    reset_event_bus()
    return


# ---------------------------------------------------------------------------
# Part 1 / 2: advance_to_dispatched helper + dispatch-ack handler integration
# ---------------------------------------------------------------------------


def test_advance_to_dispatched_moves_dispatching_to_dispatched():
    """
    **Feature: run-lifecycle-wiring**
    **Property: advance_to_dispatched applies RECEIPT_RECORDED to a
    DISPATCHING run and returns DISPATCHED.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        job_type="testbase",
    )
    transition(
        db_session=session,
        run_id=run_id,
        event=RunEvent.DISPATCH_STARTED,
        actor="system:dispatcher",
    )

    result_state = advance_to_dispatched(
        db_session=session,
        run_id=run_id,
        actor="system:dispatch-ack",
        reason="test",
    )

    testbase.assert_equal(result_state, RunState.DISPATCHED)
    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.DISPATCHED)
    return


def test_advance_to_dispatched_is_noop_on_already_dispatched():
    """
    **Feature: run-lifecycle-wiring**
    **Property: advance_to_dispatched is tolerant: a run already
    DISPATCHED returns DISPATCHED without error.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:dispatch-ack",
    )

    result_state = advance_to_dispatched(
        db_session=session,
        run_id=run_id,
        actor="system:dispatch-ack",
        reason="idempotent replay",
    )

    testbase.assert_equal(result_state, RunState.DISPATCHED)
    return


def test_advance_to_dispatched_is_noop_on_terminal():
    """
    **Feature: run-lifecycle-wiring**
    **Property: advance_to_dispatched is tolerant: a terminal run
    returns without raising.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_ABORTED, actor="system:dispatcher",
    )

    result_state = advance_to_dispatched(
        db_session=session,
        run_id=run_id,
        actor="system:dispatch-ack",
        reason="late ack on failed dispatch",
    )

    testbase.assert_true(is_terminal(state=result_state))
    return


def test_dispatch_ack_handler_advances_to_dispatched():
    """
    **Feature: run-lifecycle-wiring**
    **Property: The dispatch-ack REST handler calls
    advance_to_dispatched after recording the receipt, advancing
    the run from DISPATCHING to DISPATCHED.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )

    attempt = _FakeAttempt(run_id=run_id)
    attempt_patch = create_module_patch(runs_routes.dispatch_repo, "get_attempt")
    attempt_mock = attempt_patch.activate()
    attempt_mock.configure(side_effect=lambda **kwargs: attempt)

    receipt_patch = create_module_patch(runs_routes.receipt_service, "record")
    receipt_mock = receipt_patch.activate()
    receipt_mock.configure(side_effect=lambda **kwargs: object())

    try:
        request = _FakeRequest(
            path="/api/v1/runs/{}/dispatch-ack".format(run_id),
            path_params={"run_id": run_id},
            body={
                "envelope_id": "env-1",
                "dispatch_attempt_id": "attempt-1",
                "client_id": "client-1",
                "local_run_id": "local-1",
                "accepted_at": "2026-05-17T12:00:00+00:00",
            },
            db_session=session,
            mtls_client_cn=CLIENT_CN,
        )
        response = runs_routes.handle_dispatch_ack(request=request)
    finally:
        receipt_patch.deactivate()
        attempt_patch.deactivate()

    testbase.assert_equal(response.status_code, 202)

    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.DISPATCHED)
    return


# ---------------------------------------------------------------------------
# Part 3: note_progress helper + progress handler integration
# ---------------------------------------------------------------------------


def test_note_progress_walks_dispatched_to_running():
    """
    **Feature: run-lifecycle-wiring**
    **Property: note_progress applies RECEIPT_RECORDED then
    FIRST_PROGRESS from DISPATCHING, landing the run on RUNNING.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )

    result_state = note_progress(
        db_session=session,
        run_id=run_id,
        actor="system:progress-ingest",
        reason="first progress frame",
    )

    testbase.assert_equal(result_state, RunState.RUNNING)
    return


def test_note_progress_from_running_applies_progress_observed():
    """
    **Feature: run-lifecycle-wiring**
    **Property: note_progress from RUNNING applies PROGRESS_OBSERVED
    (self-loop) and the run stays RUNNING.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:dispatch-ack",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.FIRST_PROGRESS, actor="system:progress-ingest",
    )

    result_state = note_progress(
        db_session=session,
        run_id=run_id,
        actor="system:progress-ingest",
        reason="subsequent frame",
    )

    testbase.assert_equal(result_state, RunState.RUNNING)
    return


def test_progress_handler_advances_dispatched_to_running():
    """
    **Feature: run-lifecycle-wiring**
    **Property: The progress REST handler calls note_progress after
    persisting the frame, advancing the run from DISPATCHED to
    RUNNING on the first frame.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:dispatch-ack",
    )

    summary_patch = create_module_patch(
        runs_routes.progress_service, "ingest_summary",
    )
    summary_mock = summary_patch.activate()
    summary_mock.configure(side_effect=lambda **kwargs: object())

    try:
        request = _FakeRequest(
            path="/api/v1/runs/{}/progress".format(run_id),
            path_params={"run_id": run_id},
            body={
                "summary": {
                    "run_id": run_id,
                    "client_id": "client-1",
                    "format_tag": "testbase",
                    "tests_passed": 1,
                    "tests_failed": 0,
                    "tests_skipped": 0,
                    "tests_errored": 0,
                    "recorded_at": "2026-05-17T12:00:00+00:00",
                }
            },
            db_session=session,
            mtls_client_cn=CLIENT_CN,
        )
        response = runs_routes.handle_post_progress(request=request)
    finally:
        summary_patch.deactivate()

    testbase.assert_equal(response.status_code, 202)
    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.RUNNING)
    return


def test_progress_handler_keeps_running_on_subsequent_frame():
    """
    **Feature: run-lifecycle-wiring**
    **Property: A second progress frame while the run is RUNNING keeps
    the run in RUNNING (PROGRESS_OBSERVED self-loop).**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:dispatch-ack",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.FIRST_PROGRESS, actor="system:progress-ingest",
    )

    summary_patch = create_module_patch(
        runs_routes.progress_service, "ingest_summary",
    )
    summary_mock = summary_patch.activate()
    summary_mock.configure(side_effect=lambda **kwargs: object())

    try:
        request = _FakeRequest(
            path="/api/v1/runs/{}/progress".format(run_id),
            path_params={"run_id": run_id},
            body={
                "summary": {
                    "run_id": run_id,
                    "client_id": "client-1",
                    "format_tag": "testbase",
                    "tests_passed": 3,
                    "tests_failed": 0,
                    "tests_skipped": 0,
                    "tests_errored": 0,
                    "recorded_at": "2026-05-17T12:05:00+00:00",
                }
            },
            db_session=session,
            mtls_client_cn=CLIENT_CN,
        )
        response = runs_routes.handle_post_progress(request=request)
    finally:
        summary_patch.deactivate()

    testbase.assert_equal(response.status_code, 202)
    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.RUNNING)
    return


# ---------------------------------------------------------------------------
# Part 4: advance_to_terminal helper + results/complete integration
# ---------------------------------------------------------------------------


def test_advance_to_terminal_from_dispatching_reaches_completed():
    """
    **Feature: run-lifecycle-wiring**
    **Property: advance_to_terminal with succeeded=True from
    DISPATCHING applies the intermediate events and reaches
    COMPLETED.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )

    result = advance_to_terminal(
        db_session=session,
        run_id=run_id,
        succeeded=True,
        actor="system:result-ingest",
        reason="test",
    )

    testbase.assert_equal(result, RunState.COMPLETED.value)
    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.COMPLETED)
    return


def test_advance_to_terminal_from_running_reaches_failed():
    """
    **Feature: run-lifecycle-wiring**
    **Property: advance_to_terminal with succeeded=False from
    RUNNING applies FAILURE_OBSERVED and reaches FAILED.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:dispatch-ack",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.FIRST_PROGRESS, actor="system:progress-ingest",
    )

    result = advance_to_terminal(
        db_session=session,
        run_id=run_id,
        succeeded=False,
        actor="system:result-ingest",
        reason="test failure outcome",
    )

    testbase.assert_equal(result, RunState.FAILED.value)
    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.FAILED)
    return


def test_advance_to_terminal_is_noop_on_already_completed():
    """
    **Feature: run-lifecycle-wiring**
    **Property: advance_to_terminal is tolerant: a run already in
    COMPLETED returns 'completed' without error.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    advance_to_terminal(
        db_session=session, run_id=run_id,
        succeeded=True, actor="system:result-ingest", reason="first",
    )

    result = advance_to_terminal(
        db_session=session,
        run_id=run_id,
        succeeded=True,
        actor="system:result-ingest",
        reason="idempotent replay",
    )

    testbase.assert_equal(result, RunState.COMPLETED.value)
    return


def test_results_complete_handler_advances_to_completed():
    """
    **Feature: run-lifecycle-wiring**
    **Property: The results/complete handler with terminal_outcome=
    'success' advances the run from RUNNING to COMPLETED.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:dispatch-ack",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.FIRST_PROGRESS, actor="system:progress-ingest",
    )

    scan_patch = create_module_patch(
        runs_routes.result_scanner, "scan_once",
    )

    class _FakeScanOutcome:
        status = "scanned"

    scan_mock = scan_patch.activate()
    scan_mock.configure(side_effect=lambda **kwargs: _FakeScanOutcome())

    try:
        request = _FakeRequest(
            path="/api/v1/runs/{}/results/complete".format(run_id),
            path_params={"run_id": run_id},
            body={
                "client_id": "client-1",
                "format_tag": "testbase",
                "backend_key_prefix": "runs/{}/".format(run_id),
                "completed_at": "2026-05-17T13:00:00+00:00",
                "terminal_outcome": "success",
            },
            db_session=session,
            mtls_client_cn=CLIENT_CN,
        )
        response = runs_routes.handle_post_results_complete(request=request)
    finally:
        scan_patch.deactivate()

    testbase.assert_equal(response.status_code, 202)
    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.COMPLETED)
    return


def test_results_complete_handler_advances_to_failed_on_failure_outcome():
    """
    **Feature: run-lifecycle-wiring**
    **Property: The results/complete handler with terminal_outcome=
    'failure' advances the run from RUNNING to FAILED.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:dispatch-ack",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.FIRST_PROGRESS, actor="system:progress-ingest",
    )

    scan_patch = create_module_patch(
        runs_routes.result_scanner, "scan_once",
    )

    class _FakeScanOutcome:
        status = "scanned"

    scan_mock = scan_patch.activate()
    scan_mock.configure(side_effect=lambda **kwargs: _FakeScanOutcome())

    try:
        request = _FakeRequest(
            path="/api/v1/runs/{}/results/complete".format(run_id),
            path_params={"run_id": run_id},
            body={
                "client_id": "client-1",
                "format_tag": "testbase",
                "backend_key_prefix": "runs/{}/".format(run_id),
                "completed_at": "2026-05-17T13:00:00+00:00",
                "terminal_outcome": "failure",
            },
            db_session=session,
            mtls_client_cn=CLIENT_CN,
        )
        response = runs_routes.handle_post_results_complete(request=request)
    finally:
        scan_patch.deactivate()

    testbase.assert_equal(response.status_code, 202)
    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.FAILED)
    return


def _complete_a_testbase_run_with(*, extra_body):
    """Drive a testbase run to the end through the results/complete handler with a failure outcome plus ``extra_body``; returns the transition reasons."""
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()
    create_run(db_session=session, run_id=run_id, project_id=PROJECT_UUID, job_type="testbase")
    transition(db_session=session, run_id=run_id, event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher")
    transition(db_session=session, run_id=run_id, event=RunEvent.RECEIPT_RECORDED, actor="system:dispatch-ack")
    transition(db_session=session, run_id=run_id, event=RunEvent.FIRST_PROGRESS, actor="system:progress-ingest")

    scan_patch = create_module_patch(runs_routes.result_scanner, "scan_once")

    class _FakeScanOutcome:
        status = "scanned"

    scan_mock = scan_patch.activate()
    scan_mock.configure(side_effect=lambda **kwargs: _FakeScanOutcome())
    try:
        body = {
            "client_id": "client-1", "format_tag": "testbase", "backend_key_prefix": "runs/{}/".format(run_id),
            "completed_at": "2026-05-17T13:00:00+00:00", "terminal_outcome": "failure",
        }
        body.update(extra_body)
        request = _FakeRequest(
            path="/api/v1/runs/{}/results/complete".format(run_id), path_params={"run_id": run_id}, body=body, db_session=session, mtls_client_cn=CLIENT_CN,
        )
        response = runs_routes.handle_post_results_complete(request=request)
    finally:
        scan_patch.deactivate()
    audits = run_repo.list_state_audits(db_session=session, run_id=run_id)
    return response.status_code, [audit.reason for audit in audits if audit.to_state == RunState.FAILED]


def test_the_failed_transition_carries_the_pods_own_explanation_when_it_gave_one():
    """
    **Feature: run-lifecycle-wiring**
    **Property: the reason recorded on a test run's move to FAILED (what its event, and so a failed-run notification, says) is the pod's notes on the manifest ("1 of 2 tests
    failed."), as the run page shows; without notes it is the generic manifest text.**
    """
    with_notes = _complete_a_testbase_run_with(extra_body={"notes": "1 of 2 tests failed."})
    without = _complete_a_testbase_run_with(extra_body={})
    blank = _complete_a_testbase_run_with(extra_body={"notes": "   "})

    testbase.assert_equal(
        (with_notes, without, blank),
        ((202, ["1 of 2 tests failed."]), (202, ["testbase result manifest: outcome=failure"]), (202, ["testbase result manifest: outcome=failure"])),
    )
    return


# ---------------------------------------------------------------------------
# Full chain: ack -> progress -> results
# ---------------------------------------------------------------------------


def test_full_chain_ack_progress_results_reaches_completed():
    """
    **Feature: run-lifecycle-wiring**
    **Property: The full ingest chain -- dispatch-ack, then progress
    frame, then results/complete with success -- walks the run
    from DISPATCHING through to COMPLETED.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )

    # --- Step 1: dispatch-ack ---
    attempt = _FakeAttempt(run_id=run_id)
    attempt_patch = create_module_patch(runs_routes.dispatch_repo, "get_attempt")
    attempt_mock = attempt_patch.activate()
    attempt_mock.configure(side_effect=lambda **kwargs: attempt)

    receipt_patch = create_module_patch(runs_routes.receipt_service, "record")
    receipt_mock = receipt_patch.activate()
    receipt_mock.configure(side_effect=lambda **kwargs: object())

    try:
        ack_request = _FakeRequest(
            path="/api/v1/runs/{}/dispatch-ack".format(run_id),
            path_params={"run_id": run_id},
            body={
                "envelope_id": "env-1",
                "dispatch_attempt_id": "attempt-1",
                "client_id": "client-1",
                "local_run_id": "local-1",
                "accepted_at": "2026-05-17T12:00:00+00:00",
            },
            db_session=session,
            mtls_client_cn=CLIENT_CN,
        )
        ack_response = runs_routes.handle_dispatch_ack(request=ack_request)
    finally:
        receipt_patch.deactivate()
        attempt_patch.deactivate()

    testbase.assert_equal(ack_response.status_code, 202)
    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.DISPATCHED)

    # --- Step 2: progress frame ---
    summary_patch = create_module_patch(
        runs_routes.progress_service, "ingest_summary",
    )
    summary_mock = summary_patch.activate()
    summary_mock.configure(side_effect=lambda **kwargs: object())

    try:
        progress_request = _FakeRequest(
            path="/api/v1/runs/{}/progress".format(run_id),
            path_params={"run_id": run_id},
            body={
                "summary": {
                    "run_id": run_id,
                    "client_id": "client-1",
                    "format_tag": "testbase",
                    "tests_passed": 2,
                    "tests_failed": 0,
                    "tests_skipped": 0,
                    "tests_errored": 0,
                    "recorded_at": "2026-05-17T12:02:00+00:00",
                }
            },
            db_session=session,
            mtls_client_cn=CLIENT_CN,
        )
        progress_response = runs_routes.handle_post_progress(
            request=progress_request,
        )
    finally:
        summary_patch.deactivate()

    testbase.assert_equal(progress_response.status_code, 202)
    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.RUNNING)

    # --- Step 3: results/complete ---
    scan_patch = create_module_patch(
        runs_routes.result_scanner, "scan_once",
    )

    class _FakeScanOutcome:
        status = "scanned"

    scan_mock = scan_patch.activate()
    scan_mock.configure(side_effect=lambda **kwargs: _FakeScanOutcome())

    try:
        results_request = _FakeRequest(
            path="/api/v1/runs/{}/results/complete".format(run_id),
            path_params={"run_id": run_id},
            body={
                "client_id": "client-1",
                "format_tag": "testbase",
                "backend_key_prefix": "runs/{}/".format(run_id),
                "completed_at": "2026-05-17T13:00:00+00:00",
                "terminal_outcome": "success",
            },
            db_session=session,
            mtls_client_cn=CLIENT_CN,
        )
        results_response = runs_routes.handle_post_results_complete(
            request=results_request,
        )
    finally:
        scan_patch.deactivate()

    testbase.assert_equal(results_response.status_code, 202)
    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.COMPLETED)
    return


# ---------------------------------------------------------------------------
# Part 6: cancel route
# ---------------------------------------------------------------------------


class _FakePrincipal:
    def __init__(self, *, user_id: str = "user-test-1") -> None:
        self.user_id: str = user_id
        return


class _FakeRbacDecision:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed: bool = allowed
        return


def _patch_rbac_allow() -> Any:
    """
        Patch rbac_evaluator.check_permission to always allow.

        :returns: Active patch (deactivate in finally).
    """
    patch = create_module_patch(runs_routes.rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeRbacDecision(allowed=True))
    return patch


def test_cancel_handler_transitions_to_cancel_requested():
    """
    **Feature: run-lifecycle-wiring**
    **Property: POST /runs/{id}/cancel on an in-flight run
    transitions it to CANCEL_REQUESTED and returns 200 with the
    snapshot.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:dispatch-ack",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.FIRST_PROGRESS, actor="system:progress-ingest",
    )

    rbac_patch = _patch_rbac_allow()
    try:
        request = _FakeRequest(
            path="/api/v1/runs/{}/cancel".format(run_id),
            path_params={"run_id": run_id},
            body={"reason": "operator requested cancel"},
            db_session=session,
            auth_principal=_FakePrincipal(),
        )
        response = runs_routes.handle_cancel_run(request=request)
    finally:
        rbac_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["state"], RunState.CANCEL_REQUESTED.value)
    testbase.assert_equal(body["run_id"], run_id)

    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.CANCEL_REQUESTED)
    return


def test_cancel_handler_returns_409_on_terminal_run():
    """
    **Feature: run-lifecycle-wiring**
    **Property: POST /runs/{id}/cancel on a COMPLETED run returns
    409 problem+json (TerminalStateError path).**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    advance_to_terminal(
        db_session=session, run_id=run_id,
        succeeded=True, actor="system:result-ingest", reason="done",
    )

    rbac_patch = _patch_rbac_allow()
    try:
        request = _FakeRequest(
            path="/api/v1/runs/{}/cancel".format(run_id),
            path_params={"run_id": run_id},
            body={"reason": "operator cancel after completion"},
            db_session=session,
            auth_principal=_FakePrincipal(),
        )
        response = runs_routes.handle_cancel_run(request=request)
    finally:
        rbac_patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    return


def test_cancel_handler_returns_401_when_unauthenticated():
    """
    **Feature: run-lifecycle-wiring**
    **Property: POST /runs/{id}/cancel without an auth_principal
    returns 401.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )

    request = _FakeRequest(
        path="/api/v1/runs/{}/cancel".format(run_id),
        path_params={"run_id": run_id},
        body={"reason": "test"},
        db_session=session,
    )
    response = runs_routes.handle_cancel_run(request=request)

    testbase.assert_equal(response.status_code, 401)
    return


# ---------------------------------------------------------------------------
# Part 5: timer-wheel timeout
# ---------------------------------------------------------------------------


def test_timer_wheel_timeout_advances_dispatching_to_dispatch_unconfirmed():
    """
    **Feature: run-lifecycle-wiring**
    **Property: A fired timer-wheel entry applies
    RECEIPT_ACK_TIMEOUT to a DISPATCHING run, transitioning it to
    DISPATCH_UNCONFIRMED.**
    """
    _prepare_state()
    reset_default_timer_wheel_for_testing()

    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )

    # Build a fake timer entry that is already expired.
    expired_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    entry = TimerEntry(
        attempt_id="attempt-timeout-1",
        run_id=run_id,
        project_id=PROJECT_UUID,
        deadline_at=expired_at,
    )

    # Simulate the on-timeout callback manually by importing the
    # phase5 bootstrap task builder and wiring it against our session.
    from ccai.pychestrate.webservice.extensions.phase5_bootstrap import (
        _make_timer_wheel_tick_task,
    )

    session_calls = []

    def _session_factory() -> Any:
        session_calls.append(1)
        return session

    task = _make_timer_wheel_tick_task(
        session_factory=_session_factory,
        interval_seconds=1.0,
    )

    # Build a fresh wheel, arm it with our expired entry, then tick.
    wheel = TimerWheel()
    wheel.expect(
        attempt_id=entry.attempt_id,
        run_id=entry.run_id,
        project_id=entry.project_id,
        deadline_at=expired_at,
    )

    # Patch default_timer_wheel to return our test wheel.
    from ccai.pychestrate.webservice.extensions import phase5_bootstrap
    wheel_patch = create_module_patch(phase5_bootstrap, "default_timer_wheel")
    wheel_mock = wheel_patch.activate()
    wheel_mock.configure(side_effect=lambda: wheel)

    try:
        task.run()
    finally:
        wheel_mock = None
        wheel_patch.deactivate()

    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.DISPATCH_UNCONFIRMED)
    return


def test_timer_wheel_timeout_is_tolerant_of_already_dispatched():
    """
    **Feature: run-lifecycle-wiring**
    **Property: When the receipt arrived before the timer fired, the
    on-timeout callback skips the transition silently -- the run
    stays DISPATCHED.**
    """
    _prepare_state()
    reset_default_timer_wheel_for_testing()

    _engine, session = build_in_memory_session()
    run_id = new_uuid()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    # Receipt arrived -- run is already DISPATCHED.
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:dispatch-ack",
    )

    expired_at = datetime.now(timezone.utc) - timedelta(seconds=30)

    from ccai.pychestrate.webservice.extensions.phase5_bootstrap import (
        _make_timer_wheel_tick_task,
    )

    def _session_factory() -> Any:
        return session

    task = _make_timer_wheel_tick_task(
        session_factory=_session_factory,
        interval_seconds=1.0,
    )

    wheel = TimerWheel()
    wheel.expect(
        attempt_id="attempt-late-1",
        run_id=run_id,
        project_id=PROJECT_UUID,
        deadline_at=expired_at,
    )

    from ccai.pychestrate.webservice.extensions import phase5_bootstrap
    wheel_patch = create_module_patch(phase5_bootstrap, "default_timer_wheel")
    wheel_mock = wheel_patch.activate()
    wheel_mock.configure(side_effect=lambda: wheel)

    try:
        task.run()
    finally:
        wheel_patch.deactivate()

    row = run_repo.find_run(db_session=session, run_id=run_id)
    testbase.assert_equal(row.state, RunState.DISPATCHED)
    return


def test_cancel_handler_checks_the_project_scoped_permission():
    """
    **Feature: run cancel (E2E-09)**
    **Property: POST /runs/{id}/cancel checks
    ``project:<run's project>:runs.cancel`` -- the form the RBAC
    evaluator accepts -- not the bare ``project:runs.cancel`` it rejects.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()
    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )

    checked_keys = []

    def _record_and_allow(**kwargs):
        checked_keys.append(kwargs["permission_key"])
        return _FakeRbacDecision(allowed=True)

    patch = create_module_patch(runs_routes.rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(side_effect=_record_and_allow)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/{}/cancel".format(run_id),
            path_params={"run_id": run_id},
            body={"reason": "operator cancel"},
            db_session=session,
            auth_principal=_FakePrincipal(),
        )
        runs_routes.handle_cancel_run(request=request)
    finally:
        patch.deactivate()

    testbase.assert_equal(checked_keys, ["project:{}:runs.cancel".format(PROJECT_UUID)])
    return


def test_cancel_handler_denies_without_the_grant_instead_of_crashing():
    """
    **Feature: run cancel (E2E-09)**
    **Property: with the real RBAC evaluator, a principal that holds no
    cancel grant gets 403 -- the malformed key used to raise
    SemanticError and answer 500.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()
    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )

    # The real evaluator looks the principal up by UUID.
    request = _FakeRequest(
        path="/api/v1/runs/{}/cancel".format(run_id),
        path_params={"run_id": run_id},
        body={"reason": "operator cancel"},
        db_session=session,
        auth_principal=_FakePrincipal(user_id=new_uuid()),
    )
    response = runs_routes.handle_cancel_run(request=request)

    testbase.assert_equal(response.status_code, 403)
    return


def test_cancel_handler_accepts_the_system_wide_cancel_grant():
    """
    **Feature: run cancel (E2E-09)**
    **Property: a principal without the project grant but holding
    ``system:runs.cancel`` (system-admin) can cancel -- an administrator
    can cancel from the global runs page.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()
    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:dispatch-ack",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.FIRST_PROGRESS, actor="system:progress-ingest",
    )

    def _only_system_key(**kwargs):
        return _FakeRbacDecision(allowed=kwargs["permission_key"] == "system:runs.cancel")

    patch = create_module_patch(runs_routes.rbac_evaluator, "check_permission")
    patch.activate().configure(side_effect=_only_system_key)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/{}/cancel".format(run_id),
            path_params={"run_id": run_id},
            body={"reason": "admin cancel"},
            db_session=session,
            auth_principal=_FakePrincipal(),
        )
        response = runs_routes.handle_cancel_run(request=request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    return
