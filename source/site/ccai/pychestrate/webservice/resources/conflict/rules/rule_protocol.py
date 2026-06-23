"""
.. module:: resources.conflict.rules.rule_protocol
    :synopsis: ``conflict_rule`` factory contract.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import List, Optional, Tuple

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


@dataclass(frozen=True)
class RuleDecision:
    """
        One rule's verdict on a candidate reservation.

        :param accepted: ``True`` when the rule lets the
                         reservation through; ``False`` to veto.
        :param reason: Short reason string (empty on accept).
        :param rule_name: Identifier of the rule that produced
                          the decision.
    """
    accepted: bool
    reason: str
    rule_name: str


class ConflictRuleProtocol(FactoryProtocolBase):
    """
        Contract for conflict-rule extensions. Rules are pure
        functions over the candidate reservation + the existing
        active reservations on the same resource. The evaluator
        calls them in priority order and the first veto wins.
    """

    factory_protocol_name: str = "conflict_rule"
    protocol_schema_version: int = 1

    @classmethod
    def rule_name(cls) -> str:
        """
            Stable identifier the evaluator records on the
            decision row.
        """
        raise NotImplementedError("Subclasses must implement rule_name")

    @classmethod
    def evaluate(
            cls,
            *,
            candidate,  # CandidateReservation (avoid circular import)
            active_reservations
        ) -> RuleDecision:
        """
            Return :class:`RuleDecision` for ``candidate`` against
            ``active_reservations``.
        """
        raise NotImplementedError("Subclasses must implement evaluate")
