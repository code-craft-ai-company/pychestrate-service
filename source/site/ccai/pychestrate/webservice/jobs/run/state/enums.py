"""
.. module:: jobs.run.state.enums
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Canonical RunState / RunEvent / TerminalOutcome enums.

.. moduleauthor:: Code Craft AI LLC

The enums here are the single source of truth for the run lifecycle.
The state set is enumerated exactly as in Requirement 1 AC #1 of
``specs/5-run-state-machine/requirements.md``. Event names are from
the design's "Events Consumed" + internal transitions (cancel,
stall).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum


class RunState(str, enum.Enum):
    """
        Canonical run state set. ``str`` mixin keeps the enum
        JSON-serializable without a custom encoder.
    """
    PENDING = "pending"
    DISPATCHING = "dispatching"
    DISPATCHED = "dispatched"
    DISPATCH_UNCONFIRMED = "dispatch_unconfirmed"
    DISPATCH_LOST = "dispatch_lost"
    DISPATCH_FAILED = "dispatch_failed"
    RUNNING = "running"
    PROGRESS_STALLED = "progress_stalled"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETING = "completing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_INVESTIGATION = "needs_investigation"


class RunEvent(str, enum.Enum):
    """
        Events that drive :class:`RunState` transitions. Callers
        always pass an event; the machine resolves the target state
        via :mod:`.transition_table`.
    """
    DISPATCH_STARTED = "dispatch_started"
    ENVELOPE_SIGNED = "envelope_signed"
    RECEIPT_RECORDED = "receipt_recorded"
    RECEIPT_ACK_TIMEOUT = "receipt_ack_timeout"
    RECEIPT_LOST = "receipt_lost"
    DISPATCH_ABORTED = "dispatch_aborted"
    FIRST_PROGRESS = "first_progress"
    PROGRESS_OBSERVED = "progress_observed"
    PROGRESS_STALL_DETECTED = "progress_stall_detected"
    PROGRESS_RESUMED = "progress_resumed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCEL_ACK_RECEIVED = "cancel_ack_received"
    CANCEL_COMPLETED = "cancel_completed"
    COMPLETION_OBSERVED = "completion_observed"
    FAILURE_OBSERVED = "failure_observed"
    RECONCILED_TO_TERMINAL = "reconciled_to_terminal"
    INVESTIGATION_REQUIRED = "investigation_required"


class TerminalOutcome(str, enum.Enum):
    """
        The final classification attached to a run that reached a
        terminal state. ``dispatch_failed`` / ``dispatch_lost`` are
        distinct from ``failure`` because their root cause is the
        transport layer, not the job itself — downstream metrics and
        triage treat them differently.
    """
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    DISPATCH_FAILED = "dispatch_failed"
    DISPATCH_LOST = "dispatch_lost"


TERMINAL_STATES = frozenset({
    RunState.COMPLETED,
    RunState.FAILED,
    RunState.CANCELLED,
    RunState.DISPATCH_FAILED,
    RunState.DISPATCH_LOST,
})


TERMINAL_STATE_TO_OUTCOME = {
    RunState.COMPLETED: TerminalOutcome.SUCCESS,
    RunState.FAILED: TerminalOutcome.FAILURE,
    RunState.CANCELLED: TerminalOutcome.CANCELLED,
    RunState.DISPATCH_FAILED: TerminalOutcome.DISPATCH_FAILED,
    RunState.DISPATCH_LOST: TerminalOutcome.DISPATCH_LOST,
}
