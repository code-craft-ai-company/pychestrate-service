"""
.. module:: metrics.alerts.factories.rule_kind_protocol
    :synopsis: ``alert_rule_kind`` factory contract.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


@dataclass(frozen=True)
class AlertRuleKindRecord:
    """
        Caller-facing description of a registered rule kind.
    """
    kind: str
    description: str
    config_schema_keys: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AlertEvaluationOutcome:
    """
        Per-rule evaluation outcome.

        :param fires: True ⇒ alert is firing.
        :param observed_value: Value pulled from the
                               timeseries backend (None for
                               kinds that don't need a value
                               read).
        :param threshold_value: Threshold the value was
                                compared against.
        :param reason: Human-readable explanation surfaced on
                       the live-state row.
    """
    fires: bool
    observed_value: Optional[float] = None
    threshold_value: Optional[float] = None
    reason: str = ""


class AlertRuleKindProtocol(FactoryProtocolBase):
    """
        Contract for ``alert_rule_kind`` extensions.
    """

    factory_protocol_name: str = "alert_rule_kind"
    protocol_schema_version: int = 1

    @classmethod
    def kind_name(cls) -> str:
        """
            Stable identifier matching :attr:`AlertRule.kind`.
        """
        raise NotImplementedError("Subclasses must implement kind_name")

    @classmethod
    def record(cls) -> AlertRuleKindRecord:
        """
            Static description used by REST listings.
        """
        raise NotImplementedError("Subclasses must implement record")

    @classmethod
    def validate_config(
            cls,
            *,
            config: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        """
            Validate the rule's config payload.
        """
        raise NotImplementedError("Subclasses must implement validate_config")

    @classmethod
    def evaluate(
            cls,
            *,
            db_session: DbSession,
            project_id: str,
            config: Mapping[str, Any]
        ) -> AlertEvaluationOutcome:
        """
            Compute the rule's outcome. Implementations are
            expected to read from the timeseries backend or
            other read-only sources only — alert evaluation
            never mutates infra state.
        """
        raise NotImplementedError("Subclasses must implement evaluate")
