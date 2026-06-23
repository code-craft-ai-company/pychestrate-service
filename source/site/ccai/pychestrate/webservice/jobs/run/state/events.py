"""
.. module:: jobs.run.state.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bus-topic constants + payload shapes for run lifecycle events.

.. moduleauthor:: Code Craft AI LLC

Every caller that needs to subscribe to run lifecycle events imports
the :class:`RunStateEventTopics` constants rather than writing raw
strings. The payload dataclasses document the stable shape each
subscriber can rely on.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ccai.pychestrate.webservice.jobs.run.state.enums import RunEvent, RunState


class RunStateEventTopics:
    """
        Canonical bus topic strings. Use the class attributes rather
        than raw strings so a rename is a one-file change.
    """
    STATE_CHANGED = "entity.run.state_changed"
    COMPLETED = "entity.run.completed"
    FAILED = "entity.run.failed"
    CANCELLED = "entity.run.cancelled"
    RECONCILED = "entity.run.reconciled"


@dataclass(frozen=True)
class RunStateChangedPayload:
    """
        Payload shape published on :attr:`RunStateEventTopics.STATE_CHANGED`
        after every :meth:`RunStateMachine.transition` commit.

        :param run_id: Run UUID.
        :param project_id: Owning project UUID.
        :param from_state: State the run was in before the transition.
        :param to_state: State the run is in after the transition.
        :param event: :class:`RunEvent` that drove the transition.
        :param actor: Authenticated actor / ``system:<subsystem>`` id.
        :param reason: Optional free-form reason the caller supplied.
        :param transitioned_at: UTC timestamp of the commit.
    """
    run_id: str
    project_id: str
    from_state: RunState
    to_state: RunState
    event: RunEvent
    actor: str
    reason: Optional[str]
    transitioned_at: datetime


@dataclass(frozen=True)
class RunReconciledPayload:
    """
        Payload shape published on :attr:`RunStateEventTopics.RECONCILED`
        when :meth:`RunStateMachine.reconcile` resolves a
        client-truth divergence.

        :param run_id: Run UUID.
        :param project_id: Owning project UUID.
        :param prior_state: State before the reconcile.
        :param resolved_state: State the reconcile produced.
        :param source: Origin tag (``"client_truth"``, ``"operator"``).
        :param reconciled_at: UTC timestamp of the commit.
    """
    run_id: str
    project_id: str
    prior_state: RunState
    resolved_state: RunState
    source: str
    reconciled_at: datetime
