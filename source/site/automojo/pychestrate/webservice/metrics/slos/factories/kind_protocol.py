"""
.. module:: metrics.slos.factories.kind_protocol
    :synopsis: ``slo_definition_kind`` factory contract.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


@dataclass(frozen=True)
class SLOKindRecord:
    """
        Caller-facing description of a registered SLO kind.
    """
    kind: str
    description: str
    config_schema_keys: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SLOComputationOutcome:
    """
        Output of an SLO kind's ``compute`` method.

        :param achieved_ratio: ``[0.0, 1.0]``; the observed
                               ratio of good outcomes over the
                               window. ``None`` when no samples
                               were observed.
        :param good_count: Count of good observations.
        :param total_count: Count of total observations.
        :param reason: Human-readable explanation surfaced on
                       the status view.
    """
    achieved_ratio: Optional[float]
    good_count: int
    total_count: int
    reason: str = ""


class SLODefinitionProtocol(FactoryProtocolBase):
    """
        Contract for ``slo_definition_kind`` extensions. M1
        ships only :class:`AvailabilityRatioSloKind`; M2 widens
        to ``latency_quantile`` + ``threshold_budget`` kinds.
    """

    factory_protocol_name: str = "slo_definition_kind"
    protocol_schema_version: int = 1

    @classmethod
    def kind_name(cls) -> str:
        """
            Stable identifier matching :attr:`SLO.kind`.
        """
        raise NotImplementedError("Subclasses must implement kind_name")

    @classmethod
    def record(cls) -> SLOKindRecord:
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
            Validate the SLO's definition_config payload.
        """
        raise NotImplementedError("Subclasses must implement validate_config")

    @classmethod
    def compute(
            cls,
            *,
            db_session: DbSession,
            project_id: str,
            config: Mapping[str, Any],
            window_seconds: int
        ) -> SLOComputationOutcome:
        """
            Compute the achieved ratio over ``window_seconds``.
        """
        raise NotImplementedError("Subclasses must implement compute")
