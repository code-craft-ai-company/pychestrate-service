"""
.. module:: jobs.run.state.advance
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tolerant state-advance helpers built on machine.transition.

.. moduleauthor:: Code Craft AI LLC

Every ingest endpoint that needs to move a run forward (dispatch-ack,
progress, result-complete, timer-wheel timeout) calls one of the three
public helpers here rather than calling :func:`machine.transition`
directly.

All three helpers are **tolerant / idempotent**: an event the
transition table rejects from the current state is silently skipped,
a run that is already terminal is a no-op, and a missing run row
returns ``None`` without raising. This matches the established pattern
in :func:`ingest.result.completion._advance_run_state_to_terminal`,
which is now removed in favour of :func:`advance_to_terminal` here.

Typical call paths:

* :func:`advance_to_dispatched` — called by the dispatch-ack handler
  after ``receipt_service.record`` succeeds.
* :func:`note_progress` — called by the progress ingest handler after
  ``progress_service.ingest_summary`` or ``ingest_record`` succeeds.
* :func:`advance_to_terminal` — called by the testbase result handler
  after ``result_scanner.scan_once`` succeeds and by the build /
  provision completion path.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from typing import Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.jobs.run.state import repository as run_repo
from ccai.pychestrate.webservice.jobs.run.state.enums import (
    RunEvent,
    RunState,
    TERMINAL_STATES,
)
from ccai.pychestrate.webservice.jobs.run.state.errors import (
    IllegalTransitionError,
    RunNotFoundError,
    TerminalStateError,
)
from ccai.pychestrate.webservice.jobs.run.state.machine import (
    transition as _transition,
)


_LOGGER = logging.getLogger("pychestrate.jobs.run.state.advance")


#: Intermediate events applied before the terminal event so a run
#: stuck at DISPATCHING can reach COMPLETED / FAILED without an
#: intermediate ack + progress post. Mirrors the list in the now-
#: deleted ``ingest.result.completion._advance_run_state_to_terminal``.
_TERMINAL_WALK_EVENTS = (
    RunEvent.RECEIPT_RECORDED,
    RunEvent.FIRST_PROGRESS,
)


def advance_to_dispatched(
        *,
        db_session: DbSession,
        run_id: str,
        actor: str,
        reason: str
    ) -> Optional[RunState]:
    """
        Try to apply :attr:`RunEvent.RECEIPT_RECORDED` to the run.

        Tolerant: the event is skipped silently when the run is
        already past the DISPATCHING state, is already terminal,
        or does not exist in the database. Returns the state the
        run reached after the attempt (or the current state when
        the advance was a no-op), or ``None`` when no row exists.

        The helper goes straight to :func:`machine.transition`
        without reading ``row.state`` first — the transition table
        and machine already guard every precondition. This keeps
        the code path tight and avoids a redundant query when the
        fast path (DISPATCHING -> DISPATCHED) succeeds.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param actor: Actor tag written to the state-audit row.
        :param reason: Human-readable reason written to the audit row.

        :returns: The :class:`RunState` after the attempt, or
                  ``None`` when no run row exists.
    """
    try:
        snapshot = _transition(
            db_session=db_session,
            run_id=run_id,
            event=RunEvent.RECEIPT_RECORDED,
            actor=actor,
            reason=reason,
        )
        rtnval = snapshot.state
        return rtnval
    except TerminalStateError:
        # Already terminal; fetch current state for the caller.
        row = run_repo.find_run(db_session=db_session, run_id=run_id)
        if row is None:
            rtnval = None
            return rtnval
        rtnval = row.state
        return rtnval
    except IllegalTransitionError:
        # Already past DISPATCHING (e.g. DISPATCHED, RUNNING); no-op.
        row = run_repo.find_run(db_session=db_session, run_id=run_id)
        if row is None:
            rtnval = None
            return rtnval
        rtnval = row.state
        return rtnval
    except RunNotFoundError:
        rtnval = None
        return rtnval


def note_progress(
        *,
        db_session: DbSession,
        run_id: str,
        actor: str,
        reason: str
    ) -> Optional[RunState]:
    """
        Walk the run toward RUNNING and record progress.

        Strategy: try PROGRESS_OBSERVED first (the self-loop that
        works when the run is already RUNNING or PROGRESS_STALLED).
        When that is rejected (the run hasn't reached RUNNING yet),
        walk the intermediate events
        (:attr:`RunEvent.RECEIPT_RECORDED`,
        :attr:`RunEvent.FIRST_PROGRESS`) tolerantly, skipping any
        the transition table rejects from the current state.

        Tolerant: already-terminal and missing rows are no-ops.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param actor: Actor tag written to the state-audit row.
        :param reason: Human-readable reason written to the audit row.

        :returns: The :class:`RunState` after the attempt, or
                  ``None`` when no run row exists.
    """
    # Optimistic fast path: the run is already RUNNING.  A single
    # PROGRESS_OBSERVED transition covers the common case without
    # an extra find_run call.
    try:
        snapshot = _transition(
            db_session=db_session,
            run_id=run_id,
            event=RunEvent.PROGRESS_OBSERVED,
            actor=actor,
            reason=reason,
        )
        rtnval = snapshot.state
        return rtnval
    except RunNotFoundError:
        rtnval = None
        return rtnval
    except TerminalStateError:
        # Already terminal; no-op.
        row = run_repo.find_run(db_session=db_session, run_id=run_id)
        if row is None:
            rtnval = None
            return rtnval
        rtnval = row.state
        return rtnval
    except IllegalTransitionError:
        # Not RUNNING / PROGRESS_STALLED yet — fall through to the
        # walk-to-RUNNING path below.
        pass

    # Walk: RECEIPT_RECORDED -> DISPATCHED, FIRST_PROGRESS -> RUNNING.
    walk_events = (
        RunEvent.RECEIPT_RECORDED,
        RunEvent.FIRST_PROGRESS,
    )
    for event in walk_events:
        try:
            _transition(
                db_session=db_session,
                run_id=run_id,
                event=event,
                actor=actor,
                reason=reason,
            )
        except (IllegalTransitionError, TerminalStateError):
            continue
        except RunNotFoundError:
            rtnval = None
            return rtnval

    row = run_repo.find_run(db_session=db_session, run_id=run_id)
    if row is None:
        rtnval = None
        return rtnval
    rtnval = row.state
    return rtnval


def advance_to_terminal(
        *,
        db_session: DbSession,
        run_id: str,
        succeeded: bool,
        actor: str,
        reason: str
    ) -> Optional[str]:
    """
        Drive the run-state row to a terminal state.

        A run may be stuck at any intermediate state
        (DISPATCHING, DISPATCHED, RUNNING, …). The walker applies
        the intermediate canonical events in
        :data:`_TERMINAL_WALK_EVENTS` (RECEIPT_RECORDED,
        FIRST_PROGRESS), skipping any the transition table rejects
        from the current state, then applies
        :attr:`RunEvent.COMPLETION_OBSERVED` or
        :attr:`RunEvent.FAILURE_OBSERVED` as the terminal event.

        The walk is tolerant: events the table rejects are skipped;
        an already-terminal row causes the terminal-event attempt to
        raise :class:`TerminalStateError`, which the walker catches
        and handles by returning the current state; a missing row
        returns ``None``. The caller's domain terminal record
        (BuildRun, InfraRun, or the testbase summary's pass/fail
        count) is the authoritative completion state — if the
        run-state row cannot be driven terminal from its current
        position, the divergence is logged rather than raised.

        This function supersedes the private
        ``_advance_run_state_to_terminal`` that previously lived in
        :mod:`ingest.result.completion` — both build/provision and
        testbase result paths share this single implementation.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param succeeded: True when the run completed successfully.
        :param actor: Actor tag written to the state-audit row.
        :param reason: Human-readable reason written to the audit row.

        :returns: The terminal run-state value string, the last
                  observed run-state value string when terminal
                  could not be reached, or ``None`` when no
                  run-state row exists.
    """
    terminal_event = RunEvent.COMPLETION_OBSERVED
    if succeeded is False:
        terminal_event = RunEvent.FAILURE_OBSERVED

    # Walk intermediate events tolerantly.  A TerminalStateError
    # means the row is already terminal so we stop walking and let
    # the final transition attempt surface the state.
    for event in _TERMINAL_WALK_EVENTS:
        try:
            _transition(
                db_session=db_session,
                run_id=run_id,
                event=event,
                actor=actor,
                reason="advance-to-terminal: {}".format(reason),
            )
        except TerminalStateError:
            # Already terminal — skip the rest of the walk; the
            # terminal event attempt below will also raise
            # TerminalStateError and return the current state.
            break
        except IllegalTransitionError:
            continue
        except RunNotFoundError:
            rtnval = None
            return rtnval

    try:
        snapshot = _transition(
            db_session=db_session,
            run_id=run_id,
            event=terminal_event,
            actor=actor,
            reason=reason,
        )
        rtnval = snapshot.state.value
        return rtnval
    except TerminalStateError:
        # Already terminal (no-op idempotent replay).  Return
        # whatever state the row is in.
        current = run_repo.find_run(db_session=db_session, run_id=run_id)
        if current is None:
            rtnval = None
            return rtnval
        rtnval = current.state.value
        return rtnval
    except IllegalTransitionError as xcpt:
        err_lines = [
            "pychestrate.jobs.run.state.advance: run_state_not_terminal",
        ]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append("TERMINAL_EVENT: {}".format(terminal_event.value))
        err_lines.append("REASON: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_lines)
        _LOGGER.warning(err_msg)
        current = run_repo.find_run(db_session=db_session, run_id=run_id)
        if current is None:
            rtnval = None
            return rtnval
        rtnval = current.state.value
        return rtnval
    except RunNotFoundError:
        rtnval = None
        return rtnval


__all__ = [
    "advance_to_dispatched",
    "note_progress",
    "advance_to_terminal",
]
