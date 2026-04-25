"""
.. module:: artifacts.factories.default_promotion
    :synopsis: DefaultPromotionStrategy reference impl.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta

from automojo.pychestrate.webservice.artifacts.factories.promotion_strategy import (
    PromotionDecision,
    PromotionStrategyProtocol,
)


DEFAULT_HOT_TTL_DAYS: int = 30
LARGE_BLOB_THRESHOLD_BYTES: int = 256 * 1024 * 1024


class DefaultPromotionStrategy(PromotionStrategyProtocol):
    """
        M1 strategy: keep blobs ``hot`` for 30 days then promote
        to ``cold``. Blobs above
        :data:`LARGE_BLOB_THRESHOLD_BYTES` skip the hot tier
        entirely (they go straight to cold).
    """

    factory_protocol_name: str = "promotion_strategy"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def strategy_name(cls) -> str:
        rtnval = "default"
        return rtnval

    @classmethod
    def evaluate(
            cls,
            *,
            artifact_type: str,
            size_bytes: int,
            registered_at: datetime
        ) -> PromotionDecision:
        if size_bytes >= LARGE_BLOB_THRESHOLD_BYTES:
            rtnval = PromotionDecision(
                target_tier="cold",
                apply_at=None,
                reason="size>=large_blob_threshold",
            )
            return rtnval
        rtnval = PromotionDecision(
            target_tier="cold",
            apply_at=registered_at + timedelta(days=DEFAULT_HOT_TTL_DAYS),
            reason="default-hot-ttl",
        )
        return rtnval
