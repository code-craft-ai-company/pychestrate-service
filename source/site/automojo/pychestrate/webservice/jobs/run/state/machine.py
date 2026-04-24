"""
.. module:: jobs.run.state.machine
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: RunStateMachine — the authoritative run lifecycle engine.

.. moduleauthor:: Automation Mojo LLC

Every non-read state change flows through :func:`transition`. That
function is the only place ``runs_run.state`` is written, and it
always writes three rows atomically: the updated ``runs_run`` row,
an append-only ``runs_run_state_audit`` entry, and a
``runs_run_event_outbox`` row for durable delivery. The in-process
bus also receives an ``after_commit`` publish via
:mod:`messaging.outbox` so subscribers wake near-instantaneously;
the outbox table exists so a crash between commit and publish does
not lose the event (a drainer in M2 will finish delivery).

Convenience wrappers :func:`request_cancel` and :func:`reconcile`
layer spec-level semantics on top of :func:`transition`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.jobs.run.state import repository
from automojo.pychestrate.webservice.jobs.run.state import transition_table
from automojo.pychestrate.webservice.jobs.run.state.enums import (
    RunEvent,
    RunState,
    TERMINAL_STATE_TO_OUTCOME,
)
from automojo.pychestrate.webservice.jobs.run.state.errors import (
    IllegalTransitionError,
    TerminalStateError,
)
from automojo.pychestrate.webservice.jobs.run.state.events import (
    RunStateEventTopics,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


@dataclass(frozen=True)
class RunStateSnapshot:
    """
        Read-model returned by the public machine API. Callers use
        this rather than holding the SQLAlchemy row so they aren't
        bound to the session the machine operated on.

        :param run_id: Run UUID.
        :param project_id: Owning project UUID.
        :param state: Current state.
        :param prior_state: Prior state (``None`` on a freshly
                            created run).
        :param entered_state_at: UTC timestamp of the last transition.
        :param terminal_outcome: Outcome when the run is in a
                                 terminal state, else ``None``.
    """
    run_id: str
    project_id: str
    state: RunState
    prior_state: Optional[RunState]
    entered_state_at: datetime
    terminal_outcome: Optional[str]


def create_run(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        job_type: str
    ) -> RunStateSnapshot:
    """
        Create a fresh run row at :attr:`RunState.PENDING` and
        commit. Most callers follow immediately with a
        :func:`transition` to ``dispatch_started``; keeping them
        separate preserves a clean audit trail that reflects the
        "row existed for N ms before dispatch began" reality.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID (caller-supplied).
        :param project_id: Owning project UUID.
        :param job_type: Job-type string.

        :returns: :class:`RunStateSnapshot` of the newly-created row.
    """
    row = repository.create_run(
        db_session=db_session,
        run_id=run_id,
        project_id=project_id,
        job_type=job_type,
    )
    db_session.commit()
    rtnval = _snapshot_from_row(row=row)
    return rtnval


def transition(
        *,
        db_session: DbSession,
        run_id: str,
        event: RunEvent,
        actor: str,
        reason: Optional[str] = None
    ) -> RunStateSnapshot:
    """
        Apply ``event`` to the run identified by ``run_id``. Writes
        one :class:`Run` UPDATE, one :class:`RunStateAudit` INSERT,
        and one :class:`RunEventOutbox` INSERT in the caller's
        transaction, then commits. The session's
        :mod:`messaging.outbox` after-commit hook publishes the bus
        event synchronously once commit lands.

        Terminal states raise :class:`TerminalStateError` — callers
        that want idempotent no-op semantics check
        :func:`transition_table.is_terminal` first.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Target run UUID.
        :param event: Event to apply.
        :param actor: Authenticated actor id (``"user:<uuid>"`` /
                      ``"system:<subsystem>"``).
        :param reason: Optional free-form reason (audited).

        :returns: :class:`RunStateSnapshot` of the run after commit.
        :raises: RunNotFoundError, IllegalTransitionError,
                 TerminalStateError.
    """
    row = repository.get_run(db_session=db_session, run_id=run_id)
    from_state = row.state

    if transition_table.is_terminal(state=from_state) is True:
        err_lines = ["Run is in a terminal state; no further transitions permitted."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append("CURRENT_STATE: {}".format(from_state.value))
        err_lines.append("REJECTED_EVENT: {}".format(event.value))
        err_msg = os.linesep.join(err_lines)
        raise TerminalStateError(err_msg) from None

    to_state = transition_table.next_state_for(from_state=from_state, event=event)
    if to_state is None:
        permitted = sorted(
            e.value for e in transition_table.permitted_events_for(from_state=from_state)
        )
        err_lines = ["Illegal run state transition."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append("FROM_STATE: {}".format(from_state.value))
        err_lines.append("EVENT: {}".format(event.value))
        err_lines.append("PERMITTED EVENTS FROM THIS STATE:")
        for name in permitted:
            err_lines.append("    {}".format(name))
        err_msg = os.linesep.join(err_lines)
        raise IllegalTransitionError(err_msg) from None

    now = utc_now()

    row.prior_state = from_state
    row.state = to_state
    row.entered_state_at = now
    if event in (RunEvent.FIRST_PROGRESS, RunEvent.PROGRESS_OBSERVED, RunEvent.PROGRESS_RESUMED):
        row.progress_last_observed_at = now
    terminal_outcome = TERMINAL_STATE_TO_OUTCOME.get(to_state, None)
    if terminal_outcome is not None:
        row.terminal_outcome = terminal_outcome

    repository.append_state_audit(
        db_session=db_session,
        run_id=run_id,
        from_state=from_state,
        to_state=to_state,
        event=event,
        actor=actor,
        reason=reason,
        transitioned_at=now,
    )

    _emit_state_change(
        db_session=db_session,
        run_id=run_id,
        project_id=str(row.project_id),
        from_state=from_state,
        to_state=to_state,
        event=event,
        actor=actor,
        reason=reason,
        transitioned_at=now,
    )

    db_session.commit()

    rtnval = _snapshot_from_row(row=row)
    return rtnval


def request_cancel(
        *,
        db_session: DbSession,
        run_id: str,
        actor: str,
        reason: str
    ) -> RunStateSnapshot:
    """
        Transition a non-terminal run to :attr:`RunState.CANCEL_REQUESTED`
        and emit the request-phase
        :attr:`RunStateEventTopics.CANCELLED` event. The actual
        cancel RPC to the pod client is owned by
        ``5-cancel-reconcile``; this function only records the
        intent.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Target run UUID.
        :param actor: Authenticated actor id.
        :param reason: Human-readable cancel reason.

        :returns: :class:`RunStateSnapshot`.
        :raises: IllegalTransitionError, TerminalStateError,
                 RunNotFoundError.
    """
    row = repository.get_run(db_session=db_session, run_id=run_id)
    row.cancel_reason = reason
    row.cancel_actor = actor
    db_session.flush()

    rtnval = transition(
        db_session=db_session,
        run_id=run_id,
        event=RunEvent.CANCEL_REQUESTED,
        actor=actor,
        reason=reason,
    )
    return rtnval


def reconcile(
        *,
        db_session: DbSession,
        run_id: str,
        client_reported_state: RunState,
        source: str,
        actor: str = "system:reconcile"
    ) -> RunStateSnapshot:
    """
        Apply a client-reported truth that supersedes the service's
        in-flight view. Used when the client's run finished before a
        cancel RPC could reach it, or when an operator resolves a
        ``needs_investigation`` run.

        The target state must be terminal from the client's
        perspective (``completed``, ``failed``, ``cancelled``). The
        resolved path writes a synthetic
        :class:`RunEvent.COMPLETION_OBSERVED` or
        :class:`RunEvent.FAILURE_OBSERVED` or
        :class:`RunEvent.RECONCILED_TO_TERMINAL` through
        :func:`transition` so the audit trail records the reconcile
        event distinctly, and then publishes an additional
        :attr:`RunStateEventTopics.RECONCILED` event so subscribers
        can observe the divergence.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Target run UUID.
        :param client_reported_state: The client's authoritative
                                      state (must be terminal).
        :param source: Origin tag published on the reconciled event
                       (``"client_truth"``, ``"operator"``).
        :param actor: Authenticated actor id.

        :returns: :class:`RunStateSnapshot`.
        :raises: IllegalTransitionError when the current state has
                 no edge to a canonical event that produces the
                 requested terminal state.
    """
    if transition_table.is_terminal(state=client_reported_state) is False:
        err_lines = ["reconcile requires a terminal client_reported_state."]
        err_lines.append("RECEIVED: {}".format(client_reported_state.value))
        err_msg = os.linesep.join(err_lines)
        raise IllegalTransitionError(err_msg) from None

    row_before = repository.get_run(db_session=db_session, run_id=run_id)
    prior_state = row_before.state

    reconcile_event = _reconcile_event_for(target_state=client_reported_state)

    snapshot = transition(
        db_session=db_session,
        run_id=run_id,
        event=reconcile_event,
        actor=actor,
        reason="reconcile:{}".format(source),
    )

    now = utc_now()
    payload = {
        "run_id": str(run_id),
        "project_id": snapshot.project_id,
        "prior_state": prior_state.value,
        "resolved_state": snapshot.state.value,
        "source": source,
        "reconciled_at": now.isoformat(),
    }
    reconciled_event = EntityEvent(
        topic=RunStateEventTopics.RECONCILED,
        payload=payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=reconciled_event)
    repository.append_outbox_row(
        db_session=db_session,
        run_id=str(run_id),
        topic=RunStateEventTopics.RECONCILED,
        payload=payload,
        created_at=now,
    )
    db_session.commit()

    rtnval = snapshot
    return rtnval


def get_snapshot(
        *,
        db_session: DbSession,
        run_id: str
    ) -> RunStateSnapshot:
    """
        Return the current snapshot for ``run_id``.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: :class:`RunStateSnapshot`.
        :raises: RunNotFoundError.
    """
    row = repository.get_run(db_session=db_session, run_id=run_id)
    rtnval = _snapshot_from_row(row=row)
    return rtnval


def _emit_state_change(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        from_state: RunState,
        to_state: RunState,
        event: RunEvent,
        actor: str,
        reason: Optional[str],
        transitioned_at: datetime
    ) -> None:
    """
        Write the outbox row + the session-scoped in-process bus
        publish for a state_changed + optional terminal-class event.

        :returns: None.
    """
    payload = {
        "run_id": str(run_id),
        "project_id": project_id,
        "from_state": from_state.value,
        "to_state": to_state.value,
        "event": event.value,
        "actor": actor,
        "reason": reason,
        "transitioned_at": transitioned_at.isoformat(),
    }

    repository.append_outbox_row(
        db_session=db_session,
        run_id=str(run_id),
        topic=RunStateEventTopics.STATE_CHANGED,
        payload=payload,
        created_at=transitioned_at,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RunStateEventTopics.STATE_CHANGED,
            payload=payload,
            source_event_id=new_uuid(),
        ),
    )

    terminal_topic = _terminal_topic_for(to_state=to_state)
    if terminal_topic is None:
        return

    # For terminal transitions, emit the matching domain-specific
    # topic in addition to the generic state_changed event so
    # subscribers can select precisely.
    repository.append_outbox_row(
        db_session=db_session,
        run_id=str(run_id),
        topic=terminal_topic,
        payload=payload,
        created_at=transitioned_at,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=terminal_topic,
            payload=payload,
            source_event_id=new_uuid(),
        ),
    )

    # request-phase cancel — emit the CANCELLED topic even though the
    # run hasn't terminated yet. This matches Requirement 3 AC #1.
    return


def _reconcile_event_for(*, target_state: RunState) -> RunEvent:
    """
        Map a terminal client-reported state to the canonical event
        the transition table uses to enter it from mid-cancel or
        needs_investigation paths.

        :param target_state: Terminal state the client reported.

        :returns: :class:`RunEvent` to apply.
    """
    if target_state == RunState.COMPLETED:
        return RunEvent.COMPLETION_OBSERVED
    if target_state == RunState.FAILED:
        return RunEvent.FAILURE_OBSERVED
    if target_state == RunState.CANCELLED:
        return RunEvent.CANCEL_COMPLETED
    if target_state == RunState.DISPATCH_LOST:
        return RunEvent.RECONCILED_TO_TERMINAL
    if target_state == RunState.DISPATCH_FAILED:
        return RunEvent.DISPATCH_ABORTED
    # Should be unreachable given the caller's is_terminal guard.
    raise IllegalTransitionError(
        "No reconcile event mapping for state {}".format(target_state.value)
    )


def _terminal_topic_for(*, to_state: RunState):
    """
        Return the domain-specific topic string for a terminal
        target state, or ``None`` when the target is non-terminal.
        Request-phase ``CANCEL_REQUESTED`` also emits ``CANCELLED``
        because the spec's Requirement 3 AC #1 treats the request
        as the first cancelled event.

        :param to_state: State the transition is moving to.

        :returns: Topic string or ``None``.
    """
    if to_state == RunState.COMPLETED:
        return RunStateEventTopics.COMPLETED
    if to_state == RunState.FAILED:
        return RunStateEventTopics.FAILED
    if to_state == RunState.CANCELLED:
        return RunStateEventTopics.CANCELLED
    if to_state == RunState.CANCEL_REQUESTED:
        return RunStateEventTopics.CANCELLED
    return None


def _snapshot_from_row(*, row) -> RunStateSnapshot:
    """
        Convert a :class:`Run` ORM row into a detached snapshot.

        :param row: ORM row.

        :returns: :class:`RunStateSnapshot`.
    """
    prior = None
    if row.prior_state is not None:
        prior = row.prior_state
    terminal_outcome = None
    if row.terminal_outcome is not None:
        terminal_outcome = row.terminal_outcome.value
    rtnval = RunStateSnapshot(
        run_id=str(row.run_id),
        project_id=str(row.project_id),
        state=row.state,
        prior_state=prior,
        entered_state_at=row.entered_state_at,
        terminal_outcome=terminal_outcome,
    )
    return rtnval
