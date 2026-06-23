"""
.. module:: artifacts.factories.promotion_strategy
    :synopsis: ``promotion_strategy`` factory protocol contract.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


@dataclass(frozen=True)
class PromotionDecision:
    """
        Outcome of a strategy's evaluation.

        :param target_tier: ``"hot"`` or ``"cold"``.
        :param apply_at: When the promotion should be applied,
                         or ``None`` for "now".
        :param reason: Free-form reason (audited).
    """
    target_tier: str
    apply_at: Optional[datetime]
    reason: str


class PromotionStrategyProtocol(FactoryProtocolBase):
    """
        Decides whether a freshly registered blob should stay hot
        or move to cold storage.
    """

    factory_protocol_name: str = "promotion_strategy"
    protocol_schema_version: int = 1

    @classmethod
    def strategy_name(cls) -> str:
        raise NotImplementedError("subclasses must implement strategy_name")

    @classmethod
    def evaluate(
            cls,
            *,
            artifact_type: str,
            size_bytes: int,
            registered_at: datetime
        ) -> PromotionDecision:
        """
            Return the promotion decision for a freshly registered
            blob. Pure function — implementations don't read DB
            state.
        """
        raise NotImplementedError("subclasses must implement evaluate")
