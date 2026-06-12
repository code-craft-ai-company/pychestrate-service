"""
.. module:: jobs.run.state.transition_table
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Declarative ``(state, event) -> next_state`` edges.

.. moduleauthor:: Code Craft AI LLC

The transition table is the single place the run lifecycle lives. A
feature that believes it needs a new edge adds one row here rather
than carrying state knowledge in a service-layer branch. The table is
built once at import and exposed through the read-only accessors so
the machine and tests cannot mutate it at runtime.

M1 covers the spec's primary flows:

- Dispatch path:    ``pending → dispatching → dispatched → running``.
- Dispatch failure: ``dispatching → dispatch_failed``
                    ``dispatched → dispatch_lost``
                    ``dispatching → dispatch_unconfirmed → dispatch_lost``.
- Progress path:    ``running ↔ progress_stalled`` via
                    ``progress_stall_detected`` /
                    ``progress_resumed``.
- Cancel path:      ``running / progress_stalled → cancel_requested
                    → cancelling → cancelled``.
- Completion path:  ``running / progress_stalled → completing?
                    → completed / failed`` (``completing`` is optional
                    — the client may emit completion directly).
- Reconcile path:   ``cancel_requested / cancelling →
                    completed / failed`` when the client's truth
                    supersedes the in-flight cancel.
- Investigation:    any non-terminal → ``needs_investigation``; the
                    operator then calls ``reconcile`` to pick a
                    terminal outcome.

Every edge here is validated on import against the canonical
:class:`RunState` / :class:`RunEvent` enums.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Dict, FrozenSet, Tuple

from ccai.pychestrate.webservice.jobs.run.state.enums import (
    RunEvent,
    RunState,
    TERMINAL_STATES,
)


# Edges are modeled as a frozen dict of (from_state, event) -> to_state.
# Many-shot self-loops (``running --progress_observed--> running``) are
# modeled explicitly so callers of :func:`next_state_for` never get back
# ``None`` for a valid-but-no-op observation.
_TRANSITIONS: Dict[Tuple[RunState, RunEvent], RunState] = {
    # --- Initial dispatch ----------------------------------------------
    (RunState.PENDING, RunEvent.DISPATCH_STARTED): RunState.DISPATCHING,
    (RunState.PENDING, RunEvent.DISPATCH_ABORTED): RunState.DISPATCH_FAILED,
    (RunState.PENDING, RunEvent.INVESTIGATION_REQUIRED): RunState.NEEDS_INVESTIGATION,

    # --- Dispatching ---------------------------------------------------
    (RunState.DISPATCHING, RunEvent.ENVELOPE_SIGNED): RunState.DISPATCHING,
    (RunState.DISPATCHING, RunEvent.RECEIPT_RECORDED): RunState.DISPATCHED,
    (RunState.DISPATCHING, RunEvent.RECEIPT_ACK_TIMEOUT): RunState.DISPATCH_UNCONFIRMED,
    (RunState.DISPATCHING, RunEvent.DISPATCH_ABORTED): RunState.DISPATCH_FAILED,
    (RunState.DISPATCHING, RunEvent.INVESTIGATION_REQUIRED): RunState.NEEDS_INVESTIGATION,

    # --- Dispatch unconfirmed ------------------------------------------
    (RunState.DISPATCH_UNCONFIRMED, RunEvent.RECEIPT_RECORDED): RunState.DISPATCHED,
    (RunState.DISPATCH_UNCONFIRMED, RunEvent.RECEIPT_LOST): RunState.DISPATCH_LOST,
    (RunState.DISPATCH_UNCONFIRMED, RunEvent.RECONCILED_TO_TERMINAL): RunState.DISPATCH_LOST,
    (RunState.DISPATCH_UNCONFIRMED, RunEvent.INVESTIGATION_REQUIRED): RunState.NEEDS_INVESTIGATION,

    # --- Dispatched ----------------------------------------------------
    (RunState.DISPATCHED, RunEvent.FIRST_PROGRESS): RunState.RUNNING,
    (RunState.DISPATCHED, RunEvent.RECEIPT_LOST): RunState.DISPATCH_LOST,
    (RunState.DISPATCHED, RunEvent.COMPLETION_OBSERVED): RunState.COMPLETED,
    (RunState.DISPATCHED, RunEvent.FAILURE_OBSERVED): RunState.FAILED,
    (RunState.DISPATCHED, RunEvent.CANCEL_REQUESTED): RunState.CANCEL_REQUESTED,
    (RunState.DISPATCHED, RunEvent.INVESTIGATION_REQUIRED): RunState.NEEDS_INVESTIGATION,

    # --- Running -------------------------------------------------------
    (RunState.RUNNING, RunEvent.PROGRESS_OBSERVED): RunState.RUNNING,
    (RunState.RUNNING, RunEvent.FIRST_PROGRESS): RunState.RUNNING,
    (RunState.RUNNING, RunEvent.PROGRESS_STALL_DETECTED): RunState.PROGRESS_STALLED,
    (RunState.RUNNING, RunEvent.COMPLETION_OBSERVED): RunState.COMPLETED,
    (RunState.RUNNING, RunEvent.FAILURE_OBSERVED): RunState.FAILED,
    (RunState.RUNNING, RunEvent.CANCEL_REQUESTED): RunState.CANCEL_REQUESTED,
    (RunState.RUNNING, RunEvent.INVESTIGATION_REQUIRED): RunState.NEEDS_INVESTIGATION,

    # --- Progress stalled ----------------------------------------------
    (RunState.PROGRESS_STALLED, RunEvent.PROGRESS_RESUMED): RunState.RUNNING,
    (RunState.PROGRESS_STALLED, RunEvent.PROGRESS_OBSERVED): RunState.RUNNING,
    (RunState.PROGRESS_STALLED, RunEvent.COMPLETION_OBSERVED): RunState.COMPLETED,
    (RunState.PROGRESS_STALLED, RunEvent.FAILURE_OBSERVED): RunState.FAILED,
    (RunState.PROGRESS_STALLED, RunEvent.CANCEL_REQUESTED): RunState.CANCEL_REQUESTED,
    (RunState.PROGRESS_STALLED, RunEvent.INVESTIGATION_REQUIRED): RunState.NEEDS_INVESTIGATION,

    # --- Cancel path ---------------------------------------------------
    (RunState.CANCEL_REQUESTED, RunEvent.CANCEL_ACK_RECEIVED): RunState.CANCELLING,
    (RunState.CANCEL_REQUESTED, RunEvent.CANCEL_COMPLETED): RunState.CANCELLED,
    (RunState.CANCEL_REQUESTED, RunEvent.COMPLETION_OBSERVED): RunState.COMPLETED,
    (RunState.CANCEL_REQUESTED, RunEvent.FAILURE_OBSERVED): RunState.FAILED,
    (RunState.CANCEL_REQUESTED, RunEvent.INVESTIGATION_REQUIRED): RunState.NEEDS_INVESTIGATION,

    (RunState.CANCELLING, RunEvent.CANCEL_COMPLETED): RunState.CANCELLED,
    (RunState.CANCELLING, RunEvent.COMPLETION_OBSERVED): RunState.COMPLETED,
    (RunState.CANCELLING, RunEvent.FAILURE_OBSERVED): RunState.FAILED,
    (RunState.CANCELLING, RunEvent.INVESTIGATION_REQUIRED): RunState.NEEDS_INVESTIGATION,

    # --- Completing ----------------------------------------------------
    (RunState.COMPLETING, RunEvent.COMPLETION_OBSERVED): RunState.COMPLETED,
    (RunState.COMPLETING, RunEvent.FAILURE_OBSERVED): RunState.FAILED,
    (RunState.COMPLETING, RunEvent.INVESTIGATION_REQUIRED): RunState.NEEDS_INVESTIGATION,

    # --- Needs investigation (operator reconciles to terminal) ---------
    (RunState.NEEDS_INVESTIGATION, RunEvent.RECONCILED_TO_TERMINAL): RunState.FAILED,
    (RunState.NEEDS_INVESTIGATION, RunEvent.COMPLETION_OBSERVED): RunState.COMPLETED,
    (RunState.NEEDS_INVESTIGATION, RunEvent.FAILURE_OBSERVED): RunState.FAILED,
}


def _build_permitted_event_index() -> Dict[RunState, FrozenSet[RunEvent]]:
    """
        Compute the state -> {permitted events} inverse index from the
        transition table. Called once at module import; the result is
        cached on the module namespace and returned by
        :func:`permitted_events_for`.

        :returns: Dict keyed by state, value is the frozenset of
                  permitted events from that state.
    """
    rtnval: Dict[RunState, set] = {}
    for state in RunState:
        rtnval[state] = set()
    for (from_state, event), _to in _TRANSITIONS.items():
        rtnval[from_state].add(event)
    frozen: Dict[RunState, FrozenSet[RunEvent]] = {}
    for state, events in rtnval.items():
        frozen[state] = frozenset(events)
    return frozen


_PERMITTED_EVENTS: Dict[RunState, FrozenSet[RunEvent]] = _build_permitted_event_index()


def next_state_for(
        *,
        from_state: RunState,
        event: RunEvent
    ):
    """
        Return the target state for a given ``(from_state, event)``
        pair, or ``None`` when the edge is not permitted.

        :param from_state: Current state.
        :param event: Event being applied.

        :returns: The :class:`RunState` the machine should transition
                  to, or ``None`` when no such edge exists.
    """
    rtnval = _TRANSITIONS.get((from_state, event), None)
    return rtnval


def permitted_events_for(*, from_state: RunState) -> FrozenSet[RunEvent]:
    """
        Return the frozenset of events that are permitted from the
        given state. Terminal states return an empty frozenset.

        :param from_state: State to look up.

        :returns: Frozenset of :class:`RunEvent` values.
    """
    rtnval = _PERMITTED_EVENTS.get(from_state, frozenset())
    return rtnval


def is_terminal(*, state: RunState) -> bool:
    """
        Return whether a state is terminal (no further transitions
        permitted).

        :param state: State to test.

        :returns: True when ``state`` is in the terminal set.
    """
    rtnval = state in TERMINAL_STATES
    return rtnval


def validate_table_on_startup() -> None:
    """
        Sanity-check the transition table at import time. Raises if
        any edge references an unknown enum value or if a terminal
        state has outgoing edges (a terminal with outgoing edges
        would silently break the :class:`TerminalStateError`
        guarantee).

        :returns: None.
        :raises: AssertionError describing the first inconsistency.
    """
    for (from_state, event), to_state in _TRANSITIONS.items():
        assert isinstance(from_state, RunState), (
            "transition key from_state is not a RunState: {}".format(from_state)
        )
        assert isinstance(event, RunEvent), (
            "transition key event is not a RunEvent: {}".format(event)
        )
        assert isinstance(to_state, RunState), (
            "transition value to_state is not a RunState: {}".format(to_state)
        )

    for terminal_state in TERMINAL_STATES:
        events = permitted_events_for(from_state=terminal_state)
        assert len(events) == 0, (
            "terminal state {} has outgoing edges: {}".format(terminal_state, events)
        )
    return


validate_table_on_startup()
