"""
.. module:: jobs.run.state.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception hierarchy for the run state machine.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class RunStateError(Exception):
    """
        Base class for recoverable run-state errors. Subclasses
        classify specific failure modes; REST / wire layers
        translate each subclass to a distinct status code.
    """


class IllegalTransitionError(RunStateError):
    """
        Raised when a caller asks the machine to apply an event from
        a state that has no edge for that event. The message is a
        multiline block naming the current state, event, and full set
        of permitted events from the current state.
    """


class TerminalStateError(RunStateError):
    """
        Raised when a caller asks the machine to transition away from
        a terminal state. Callers that want idempotent no-op behavior
        check :func:`transition_table.is_terminal` first.
    """


class RunNotFoundError(RunStateError):
    """
        Raised when a lookup by ``run_id`` finds no ``run`` row.
    """
