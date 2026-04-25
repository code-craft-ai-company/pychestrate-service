"""
.. module:: retention.dispatcher
    :synopsis: Action chain dispatcher.

The dispatcher walks a :class:`Sequence` of
:class:`ActionStep`s in order, resolves each
:class:`RetentionActionProtocol` from the registry, and
applies it. M2 honors three semantic flags:

* ``terminal`` — when an action reports
  :data:`ActionApplication(terminal=True)`, the dispatcher
  stops processing further steps for that entity. Permanent
  archive / delete actions set this so a downstream wait-step
  does not fire on a tombstoned entity.
* ``wait_days_after_previous`` — the dispatcher records the
  step's wait deadline on its outcome. When ``now <
  prior.completed_at + wait_days``, the step is queued and
  reported as ``deferred``. The M3 scheduler walks deferred
  rows on the next tick and re-applies them.
* per-step ``dry_run`` — when the policy run is a dry-run,
  every action is invoked with ``dry_run=True``; the
  dispatcher never short-circuits on terminal flags so the
  caller sees the entire chain's hypothetical effect.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, List, Mapping, Optional, Sequence, Tuple, Type

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.retention.factories.action import (
    ActionApplication,
    RetentionActionProtocol,
)
from automojo.pychestrate.webservice.retention.models import ActionStep


@dataclass(frozen=True)
class StepOutcome:
    """
        Per-step result the dispatcher hands back.

        :param action_name: Name of the action that produced
                            this outcome.
        :param outcome: ``applied | skipped | deferred | failed``.
        :param reason: Free-form description.
        :param terminal: ``True`` when this step ended the
                         entity's chain.
        :param applied_at: Timestamp the step ran (or would
                           have run, on dry-run).
        :param wait_until: Computed deferred-deadline when
                           ``outcome == "deferred"``.
    """
    action_name: str
    outcome: str
    reason: str
    terminal: bool
    applied_at: datetime
    wait_until: Optional[datetime] = None


@dataclass(frozen=True)
class ChainResult:
    """
        Aggregate of every :class:`StepOutcome` for one
        entity's chain run.
    """
    entity_id: str
    steps: Tuple[StepOutcome, ...]
    halted_terminal: bool
    final_outcome: str


def dispatch_action_chain(
        *,
        entity_kind: str,
        entity_id: str,
        steps: Sequence[ActionStep],
        dry_run: bool,
        now: Optional[datetime] = None
    ) -> ChainResult:
    """
        Run ``steps`` in order against ``entity_id``.

        :raises: SemanticError on an empty step list (a
                 retention policy with no chain is a
                 configuration bug, not a runtime fallthrough).
    """
    if steps is None or len(steps) == 0:
        err_lines = ["dispatch_action_chain requires a non-empty chain."]
        err_lines.append("ENTITY_ID: {}".format(entity_id))
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None

    materialized_now = (
        now if now is not None else datetime.now(tz=timezone.utc)
    )
    last_completed_at: Optional[datetime] = None
    outcomes: List[StepOutcome] = []
    halted = False
    final_outcome = "applied"

    for step in steps:
        action_cls = _resolve_action(action_name=step.action_name)
        if action_cls is None:
            outcome = StepOutcome(
                action_name=step.action_name,
                outcome="failed",
                reason="action_not_registered",
                terminal=False,
                applied_at=materialized_now,
            )
            outcomes.append(outcome)
            final_outcome = "failed"
            break

        wait_until = _compute_wait_until(
            step=step, last_completed_at=last_completed_at,
        )
        if (
            wait_until is not None
            and dry_run is False
            and materialized_now < wait_until
        ):
            outcome = StepOutcome(
                action_name=step.action_name,
                outcome="deferred",
                reason="wait_days_pending",
                terminal=False,
                applied_at=materialized_now,
                wait_until=wait_until,
            )
            outcomes.append(outcome)
            final_outcome = "deferred"
            break

        try:
            application = action_cls.apply(
                entity_kind=entity_kind,
                entity_id=entity_id,
                parameters=step.parameters,
                dry_run=dry_run,
            )
        except Exception as action_err:
            outcome = StepOutcome(
                action_name=step.action_name,
                outcome="failed",
                reason="{}: {}".format(
                    type(action_err).__name__, action_err,
                ),
                terminal=False,
                applied_at=materialized_now,
            )
            outcomes.append(outcome)
            final_outcome = "failed"
            break

        if not isinstance(application, ActionApplication):
            outcome = StepOutcome(
                action_name=step.action_name,
                outcome="failed",
                reason="action_returned_unexpected_type",
                terminal=False,
                applied_at=materialized_now,
            )
            outcomes.append(outcome)
            final_outcome = "failed"
            break

        outcome = StepOutcome(
            action_name=step.action_name,
            outcome=application.outcome,
            reason=application.reason,
            terminal=bool(application.terminal),
            applied_at=materialized_now,
        )
        outcomes.append(outcome)
        last_completed_at = materialized_now
        if application.outcome != "applied":
            final_outcome = application.outcome

        # On a real run a terminal step ends the chain. Dry
        # runs keep going so operators see the full plan.
        if dry_run is False and application.terminal is True:
            halted = True
            break

    rtnval = ChainResult(
        entity_id=entity_id,
        steps=tuple(outcomes),
        halted_terminal=halted,
        final_outcome=final_outcome,
    )
    return rtnval


def _resolve_action(
        *, action_name: str
    ) -> Optional[Type[RetentionActionProtocol]]:
    candidates = list_factory_implementations(
        factory_protocol_name=RetentionActionProtocol.factory_protocol_name,
    )
    for impl in candidates:
        try:
            if impl.action_name == action_name:
                return impl
        except AttributeError:
            continue
    return None


def _compute_wait_until(
        *,
        step: ActionStep,
        last_completed_at: Optional[datetime]
    ) -> Optional[datetime]:
    wait_days = int(getattr(step, "wait_days_after_previous", 0))
    if wait_days <= 0:
        return None
    if last_completed_at is None:
        return None
    if last_completed_at.tzinfo is None:
        baseline = last_completed_at.replace(tzinfo=timezone.utc)
    else:
        baseline = last_completed_at
    rtnval = baseline + timedelta(days=wait_days)
    return rtnval
