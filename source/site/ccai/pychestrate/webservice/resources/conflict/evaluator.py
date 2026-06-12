"""
.. module:: resources.conflict.evaluator
    :synopsis: Conflict-evaluation facade.

Runs every registered :class:`ConflictRuleProtocol` against a
candidate reservation in PRECEDENCE order. The first vetoing
rule's decision is returned; if every rule accepts, the
evaluation is accepted.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.resources.conflict.rules.rule_protocol import (
    RuleDecision,
)


CONFLICT_RULE_PROTOCOL: str = "conflict_rule"


@dataclass(frozen=True)
class ActiveReservationSnapshot:
    """
        Frozen view of one existing reservation for the
        evaluator.
    """
    reservation_id: str
    project_id: str
    resource_id: str
    mode: str
    requested_by: Optional[str]


@dataclass(frozen=True)
class CandidateReservation:
    """
        Frozen view of the reservation the evaluator is
        considering.
    """
    project_id: str
    resource_id: str
    mode: str
    requested_by: Optional[str]


@dataclass(frozen=True)
class ConflictEvaluation:
    """
        Aggregate outcome.

        :param accepted: Overall verdict.
        :param decisions: One :class:`RuleDecision` per rule the
                          evaluator ran. Stops at the first veto.
        :param vetoed_by: Name of the rule that vetoed (empty on
                          accept).
    """
    accepted: bool
    decisions: Tuple[RuleDecision, ...]
    vetoed_by: str


def evaluate(
        *,
        candidate: CandidateReservation,
        active_reservations: List[ActiveReservationSnapshot]
    ) -> ConflictEvaluation:
    """
        Walk the registered rules in PRECEDENCE order and return
        a :class:`ConflictEvaluation`. Pure function — no side
        effects.
    """
    impls = list_factory_implementations(
        factory_protocol_name=CONFLICT_RULE_PROTOCOL,
    )
    decisions: List[RuleDecision] = []
    vetoed_by = ""
    accepted = True
    for impl in impls:
        decision = impl.evaluate(
            candidate=candidate,
            active_reservations=tuple(active_reservations),
        )
        decisions.append(decision)
        if decision.accepted is False:
            accepted = False
            vetoed_by = decision.rule_name
            break
    rtnval = ConflictEvaluation(
        accepted=accepted,
        decisions=tuple(decisions),
        vetoed_by=vetoed_by,
    )
    return rtnval
