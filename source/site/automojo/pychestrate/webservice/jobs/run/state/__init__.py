"""
.. module:: jobs.run.state
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 run state machine.

.. moduleauthor:: Automation Mojo LLC

Public surface:

* :class:`RunState` / :class:`RunEvent` / :class:`TerminalOutcome` —
  canonical enums (:mod:`.enums`).
* :class:`RunStateSnapshot` — detached read-model.
* :func:`transition`, :func:`request_cancel`, :func:`reconcile`,
  :func:`create_run`, :func:`get_snapshot` — machine facade
  (:mod:`.machine`).
* :func:`drain_once` — outbox publisher (:mod:`.outbox_publisher`).
* :class:`RunStateEventTopics` — bus topic constants.
* :class:`IllegalTransitionError`, :class:`TerminalStateError`,
  :class:`RunNotFoundError` — exception hierarchy.

Every other feature that needs to move a run into a new state calls
:func:`transition` with an :class:`RunEvent` — no direct writes to
``runs_run.state`` from outside this package.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.jobs.run.state.enums import (
    RunEvent,
    RunState,
    TerminalOutcome,
    TERMINAL_STATES,
)
from automojo.pychestrate.webservice.jobs.run.state.errors import (
    IllegalTransitionError,
    RunNotFoundError,
    RunStateError,
    TerminalStateError,
)
from automojo.pychestrate.webservice.jobs.run.state.events import (
    RunReconciledPayload,
    RunStateChangedPayload,
    RunStateEventTopics,
)
from automojo.pychestrate.webservice.jobs.run.state.machine import (
    RunStateSnapshot,
    create_run,
    get_snapshot,
    reconcile,
    request_cancel,
    transition,
)
from automojo.pychestrate.webservice.jobs.run.state.models import (
    Run,
    RunEventOutbox,
    RunStateAudit,
)
from automojo.pychestrate.webservice.jobs.run.state.outbox_publisher import (
    drain_once,
)
from automojo.pychestrate.webservice.jobs.run.state.transition_table import (
    is_terminal,
    next_state_for,
    permitted_events_for,
)
