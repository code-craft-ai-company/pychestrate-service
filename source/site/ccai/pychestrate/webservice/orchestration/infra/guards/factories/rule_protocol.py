"""
.. module:: orchestration.infra.guards.factories.rule_protocol
    :synopsis: ``guard_rule`` factory contract + verdict types.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from dataclasses import dataclass, field
from typing import Any, Mapping, Tuple

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class GuardVerdict(str, enum.Enum):
    """
        Possible per-rule verdicts.

        ``DENY_PENDING_REVIEW`` is reserved for the M2 two-person
        review surface; M1 rules return only ``ALLOW`` or
        ``DENY``.
    """
    ALLOW = "allow"
    DENY = "deny"
    DENY_PENDING_REVIEW = "deny_pending_review"


@dataclass(frozen=True)
class GuardContext:
    """
        Inputs available to every rule's ``evaluate(...)``.

        :param project_id: Owning project.
        :param environment_id: Bound environment.
        :param environment_state: Stringified
                                  :class:`EnvironmentState`
                                  value (``"active"`` /
                                  ``"frozen"`` / ``"archived"``
                                  / ``"destroyed"``).
        :param environment_kind: Environment-kind name.
        :param environment_attrs: Attrs dict pulled from the
                                  registry.
        :param actor_role_set: Role identifiers the caller
                               carries.
        :param action: Stringified ``InfraAction`` value
                       (``"plan"`` / ``"apply"`` / ``"destroy"``).
        :param requester_id: UUID of the human requesting the
                             action.
    """
    project_id: str
    environment_id: str
    environment_state: str
    environment_kind: str
    environment_attrs: Mapping[str, Any] = field(default_factory=dict)
    actor_role_set: Tuple[str, ...] = ()
    action: str = ""
    requester_id: str = ""


@dataclass(frozen=True)
class GuardDecision:
    """
        Per-rule decision produced by :meth:`evaluate`.

        :param verdict: Resolved :class:`GuardVerdict`.
        :param reason: Human-readable explanation when the
                       verdict is not ``ALLOW``; empty
                       otherwise.
    """
    verdict: GuardVerdict
    reason: str = ""


class GuardRuleProtocol(FactoryProtocolBase):
    """
        Contract for ``guard_rule`` extensions. Rules are pure
        functions over a :class:`GuardContext`. The framework
        owns the registry, attachment surface, and aggregate
        decision — rules return per-context verdicts only.
    """

    factory_protocol_name: str = "guard_rule"
    protocol_schema_version: int = 1

    @classmethod
    def rule_id(cls) -> str:
        """
            Stable identifier matching
            :attr:`GuardAttachment.rule_id`.
        """
        raise NotImplementedError("Subclasses must implement rule_id")

    @classmethod
    def description(cls) -> str:
        """
            Human-readable description used by REST listings.
        """
        raise NotImplementedError("Subclasses must implement description")

    @classmethod
    def evaluate(
            cls,
            *,
            context: GuardContext
        ) -> GuardDecision:
        """
            Return the rule's per-context verdict.
        """
        raise NotImplementedError("Subclasses must implement evaluate")
