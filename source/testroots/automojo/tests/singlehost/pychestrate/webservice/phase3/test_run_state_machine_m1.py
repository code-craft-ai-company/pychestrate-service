"""
.. module:: test_run_state_machine_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 5-run-state-machine M1.

.. moduleauthor:: Automation Mojo LLC

Covers the M1 spec's core behavior:

* The canonical state set is what the spec says it is (15 states)
  and terminal states carry no outgoing edges.
* ``transition`` updates the run row, appends an audit row, inserts
  an outbox row, and publishes on the in-process bus — all
  atomically on commit.
* Illegal ``(state, event)`` pairs raise
  ``IllegalTransitionError`` with a multiline message naming the
  state + event + permitted events.
* Terminal state rejection — a second ``transition`` on a completed
  run raises ``TerminalStateError``.
* Happy-path dispatch → running → completed produces the expected
  audit trail.
* ``request_cancel`` transitions to ``cancel_requested`` AND emits
  the ``entity.run.cancelled`` event at the request phase (per
  Requirement 3 AC #1).
* ``reconcile(client_reported_state=completed)`` on a cancelling
  run resolves to ``completed`` AND emits ``entity.run.reconciled``.
* The outbox publisher's ``drain_once`` marks rows published and
  returns the correct count.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.jobs.run import state as run_state_api
from automojo.pychestrate.webservice.jobs.run.state import (
    IllegalTransitionError,
    Run,
    RunEvent,
    RunEventOutbox,
    RunNotFoundError,
    RunState,
    RunStateAudit,
    RunStateEventTopics,
    TERMINAL_STATES,
    TerminalOutcome,
    TerminalStateError,
    create_run,
    drain_once,
    get_snapshot,
    is_terminal,
    next_state_for,
    permitted_events_for,
    reconcile,
    request_cancel,
    transition,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    session_for,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000000101"


def _fresh_run_id() -> str:
    """
        Return a fresh UUIDv4 string, used everywhere a test needs
        a per-case run id.
    """
    rtnval = new_uuid()
    return rtnval


def _prepare_state() -> None:
    """
        Reset the in-process bus before each test so subscribers from
        prior tests cannot leak receive events they should not.
    """
    reset_event_bus()
    return


def test_canonical_state_set_has_every_spec_name():
    """
    **Feature: 5-run-state-machine (M1)**
    **Property: RunState exposes exactly the 15 spec-defined
    states, and every terminal state carries no outgoing edges.**
    """
    names = sorted(s.value for s in RunState)
    expected = sorted([
        "pending", "dispatching", "dispatched", "dispatch_unconfirmed",
        "dispatch_lost", "dispatch_failed", "running", "progress_stalled",
        "cancel_requested", "cancelling", "cancelled", "completing",
        "completed", "failed", "needs_investigation",
    ])
    testbase.assert_equal(names, expected)

    for state in RunState:
        if state in TERMINAL_STATES:
            testbase.assert_equal(is_terminal(state=state), True)
            testbase.assert_equal(len(permitted_events_for(from_state=state)), 0)
        else:
            testbase.assert_equal(is_terminal(state=state), False)
    return


def test_transition_happy_path_dispatch_to_completed():
    """
    **Feature: 5-run-state-machine (M1)**
    **Property: pending → dispatching → dispatched → running →
    completed walks the transition table; the audit log captures
    every hop in order.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = _fresh_run_id()

    snap = create_run(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        job_type="testbase-singlehost",
    )
    testbase.assert_equal(snap.state, RunState.PENDING)

    snap = transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:dispatcher",
    )
    testbase.assert_equal(snap.state, RunState.DISPATCHING)

    snap = transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:dispatcher",
    )
    testbase.assert_equal(snap.state, RunState.DISPATCHED)

    snap = transition(
        db_session=session, run_id=run_id,
        event=RunEvent.FIRST_PROGRESS, actor="system:progress-ingest",
    )
    testbase.assert_equal(snap.state, RunState.RUNNING)

    snap = transition(
        db_session=session, run_id=run_id,
        event=RunEvent.COMPLETION_OBSERVED, actor="system:result-watcher",
    )
    testbase.assert_equal(snap.state, RunState.COMPLETED)
    testbase.assert_equal(snap.terminal_outcome, TerminalOutcome.SUCCESS.value)

    # Audit trail has all four transitions in order.
    fresh = session_for(engine=_engine)
    audits = (
        fresh.query(RunStateAudit)
        .filter(RunStateAudit.run_id == run_id)
        .order_by(RunStateAudit.transitioned_at.asc())
        .all()
    )
    sequence = [(a.from_state, a.to_state, a.event) for a in audits]
    testbase.assert_equal(sequence, [
        (RunState.PENDING, RunState.DISPATCHING, RunEvent.DISPATCH_STARTED),
        (RunState.DISPATCHING, RunState.DISPATCHED, RunEvent.RECEIPT_RECORDED),
        (RunState.DISPATCHED, RunState.RUNNING, RunEvent.FIRST_PROGRESS),
        (RunState.RUNNING, RunState.COMPLETED, RunEvent.COMPLETION_OBSERVED),
    ])
    return


def test_illegal_transition_raises_with_permitted_events():
    """
    **Feature: 5-run-state-machine (M1)**
    **Property: applying an event that has no edge from the current
    state raises IllegalTransitionError naming the state, event, and
    permitted-events set in a multiline message.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = _fresh_run_id()

    create_run(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase-singlehost",
    )

    raised = False
    try:
        transition(
            db_session=session, run_id=run_id,
            event=RunEvent.FIRST_PROGRESS,
            actor="system:test",
        )
    except IllegalTransitionError as xcpt:
        raised = True
        message = str(xcpt)
        testbase.assert_equal("FROM_STATE: pending" in message, True)
        testbase.assert_equal("EVENT: first_progress" in message, True)
        testbase.assert_equal("dispatch_started" in message, True)
    testbase.assert_equal(raised, True)
    return


def test_terminal_state_rejects_further_transitions():
    """
    **Feature: 5-run-state-machine (M1)**
    **Property: a transition against a completed run raises
    TerminalStateError.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = _fresh_run_id()

    create_run(db_session=session, run_id=run_id, project_id=PROJECT_UUID, job_type="t")
    transition(db_session=session, run_id=run_id, event=RunEvent.DISPATCH_STARTED, actor="x")
    transition(db_session=session, run_id=run_id, event=RunEvent.RECEIPT_RECORDED, actor="x")
    transition(db_session=session, run_id=run_id, event=RunEvent.FIRST_PROGRESS, actor="x")
    transition(db_session=session, run_id=run_id, event=RunEvent.COMPLETION_OBSERVED, actor="x")

    raised = False
    try:
        transition(
            db_session=session, run_id=run_id,
            event=RunEvent.FAILURE_OBSERVED, actor="x",
        )
    except TerminalStateError as xcpt:
        raised = True
        testbase.assert_equal("completed" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_request_cancel_emits_cancelled_event_at_request_phase():
    """
    **Feature: 5-run-state-machine (M1)**
    **Property: request_cancel transitions to cancel_requested AND
    publishes entity.run.cancelled synchronously (request-phase
    emission per Requirement 3 AC #1).**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = _fresh_run_id()

    # Drive the run to RUNNING so cancel is legal.
    create_run(db_session=session, run_id=run_id, project_id=PROJECT_UUID, job_type="t")
    transition(db_session=session, run_id=run_id, event=RunEvent.DISPATCH_STARTED, actor="x")
    transition(db_session=session, run_id=run_id, event=RunEvent.RECEIPT_RECORDED, actor="x")
    transition(db_session=session, run_id=run_id, event=RunEvent.FIRST_PROGRESS, actor="x")

    received_cancelled: List[EntityEvent] = []
    subscribe(
        topic=RunStateEventTopics.CANCELLED,
        subscriber=lambda e: received_cancelled.append(e),
    )

    snap = request_cancel(
        db_session=session, run_id=run_id,
        actor="user:abc", reason="stop-the-lights",
    )
    testbase.assert_equal(snap.state, RunState.CANCEL_REQUESTED)
    testbase.assert_equal(len(received_cancelled), 1)
    payload = received_cancelled[0].payload
    testbase.assert_equal(payload["to_state"], "cancel_requested")
    testbase.assert_equal(payload["actor"], "user:abc")
    testbase.assert_equal(payload["reason"], "stop-the-lights")
    return


def test_reconcile_resolves_mid_cancel_to_completed():
    """
    **Feature: 5-run-state-machine (M1)**
    **Property: reconcile with client_reported_state=COMPLETED on
    a cancelling run resolves to completed AND emits
    entity.run.reconciled.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = _fresh_run_id()

    create_run(db_session=session, run_id=run_id, project_id=PROJECT_UUID, job_type="t")
    transition(db_session=session, run_id=run_id, event=RunEvent.DISPATCH_STARTED, actor="x")
    transition(db_session=session, run_id=run_id, event=RunEvent.RECEIPT_RECORDED, actor="x")
    transition(db_session=session, run_id=run_id, event=RunEvent.FIRST_PROGRESS, actor="x")
    request_cancel(db_session=session, run_id=run_id, actor="user:x", reason="oops")
    transition(db_session=session, run_id=run_id, event=RunEvent.CANCEL_ACK_RECEIVED, actor="x")
    # Run is now CANCELLING.

    received_reconciled: List[EntityEvent] = []
    received_completed: List[EntityEvent] = []
    subscribe(
        topic=RunStateEventTopics.RECONCILED,
        subscriber=lambda e: received_reconciled.append(e),
    )
    subscribe(
        topic=RunStateEventTopics.COMPLETED,
        subscriber=lambda e: received_completed.append(e),
    )

    snap = reconcile(
        db_session=session, run_id=run_id,
        client_reported_state=RunState.COMPLETED,
        source="client_truth",
        actor="system:result-watcher",
    )
    testbase.assert_equal(snap.state, RunState.COMPLETED)
    testbase.assert_equal(snap.terminal_outcome, TerminalOutcome.SUCCESS.value)

    testbase.assert_equal(len(received_reconciled), 1)
    testbase.assert_equal(received_reconciled[0].payload["prior_state"], "cancelling")
    testbase.assert_equal(received_reconciled[0].payload["resolved_state"], "completed")
    testbase.assert_equal(received_reconciled[0].payload["source"], "client_truth")

    testbase.assert_equal(len(received_completed), 1)
    return


def test_outbox_rows_materialize_and_drain_once_publishes_them():
    """
    **Feature: 5-run-state-machine (M1)**
    **Property: each transition writes a runs_run_event_outbox row;
    drain_once publishes unpublished rows and marks them
    published_at.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = _fresh_run_id()

    create_run(db_session=session, run_id=run_id, project_id=PROJECT_UUID, job_type="t")
    transition(db_session=session, run_id=run_id, event=RunEvent.DISPATCH_STARTED, actor="x")

    # After the first transition, at least one outbox row exists.
    fresh = session_for(engine=_engine)
    rows = (
        fresh.query(RunEventOutbox)
        .filter(RunEventOutbox.run_id == run_id)
        .all()
    )
    testbase.assert_equal(len(rows) >= 1, True)

    unpublished_before = sum(1 for r in rows if r.published_at is None)
    testbase.assert_equal(unpublished_before >= 1, True)

    # Drain the outbox.
    received: List[EntityEvent] = []
    subscribe(
        topic=RunStateEventTopics.STATE_CHANGED,
        subscriber=lambda e: received.append(e),
    )
    published = drain_once(db_session=fresh)
    testbase.assert_equal(published, unpublished_before)

    # After drain, no unpublished rows remain.
    fresh2 = session_for(engine=_engine)
    unpublished_after = (
        fresh2.query(RunEventOutbox)
        .filter(RunEventOutbox.run_id == run_id)
        .filter(RunEventOutbox.published_at.is_(None))
        .count()
    )
    testbase.assert_equal(unpublished_after, 0)
    return


def test_get_snapshot_raises_run_not_found_for_unknown_id():
    """
    **Feature: 5-run-state-machine (M1)**
    **Property: get_snapshot against an unknown run_id raises
    RunNotFoundError — never silently returns an empty row.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        get_snapshot(db_session=session, run_id=_fresh_run_id())
    except RunNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_progress_stall_cycle_updates_progress_timestamp():
    """
    **Feature: 5-run-state-machine (M1)**
    **Property: running → progress_stalled → running traverses the
    stall cycle; progress_resumed updates progress_last_observed_at.**
    """
    _prepare_state()
    _engine, session = build_in_memory_session()
    run_id = _fresh_run_id()

    create_run(db_session=session, run_id=run_id, project_id=PROJECT_UUID, job_type="t")
    transition(db_session=session, run_id=run_id, event=RunEvent.DISPATCH_STARTED, actor="x")
    transition(db_session=session, run_id=run_id, event=RunEvent.RECEIPT_RECORDED, actor="x")
    snap = transition(db_session=session, run_id=run_id, event=RunEvent.FIRST_PROGRESS, actor="x")
    testbase.assert_equal(snap.state, RunState.RUNNING)

    snap = transition(
        db_session=session, run_id=run_id,
        event=RunEvent.PROGRESS_STALL_DETECTED, actor="system:stall-sweeper",
    )
    testbase.assert_equal(snap.state, RunState.PROGRESS_STALLED)

    snap = transition(
        db_session=session, run_id=run_id,
        event=RunEvent.PROGRESS_RESUMED, actor="system:progress-ingest",
    )
    testbase.assert_equal(snap.state, RunState.RUNNING)

    fresh = session_for(engine=_engine)
    row = fresh.query(Run).filter(Run.run_id == run_id).first()
    testbase.assert_equal(row.progress_last_observed_at is not None, True)
    return
