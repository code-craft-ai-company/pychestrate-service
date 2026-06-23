"""
.. module:: orchestration.pipelines.sharding.factories.strategy_protocol
    :synopsis: ``sharding_strategy`` factory contract.
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
class StrategyDescription:
    """
        Static description of a strategy. Returned by
        :meth:`ShardingStrategyProtocol.describe` so callers can
        introspect a strategy without invoking expansion.

        :param strategy_name: Stable identifier the
                              :func:`expand_matrix` service uses
                              to resolve the strategy.
        :param description: Human-readable description.
        :param requires_runtime_history: True when the strategy
                                         consumes the optional
                                         runtime-history query.
        :param should_cancel_on_failure: True when a failing
                                         shard cancels its
                                         siblings.
        :param default_min_success_fraction: M2 partial-success
                                             default.
    """
    strategy_name: str
    description: str
    requires_runtime_history: bool
    should_cancel_on_failure: bool
    default_min_success_fraction: float


@dataclass(frozen=True)
class ExpandedShard:
    """
        Strategy-side row carrying the dimension-tuple plus
        derived shard id, parallel group, and sequence ordinal.

        :param shard_id: 16-char hex digest from
                         :func:`compute_shard_id`.
        :param dimension_values: Materialized dimension-tuple.
        :param parallel_group: Stable group label used by
                               reassembly.
        :param sequence_in_group: Lex-order ordinal within the
                                  group.
    """
    shard_id: str
    dimension_values: Tuple[Tuple[str, str], ...]
    parallel_group: str
    sequence_in_group: int


class ShardingStrategyProtocol(FactoryProtocolBase):
    """
        Contract for ``sharding_strategy`` extensions. A strategy
        translates a :class:`MatrixSpec` into an ordered list of
        :class:`ExpandedShard` rows. The framework owns
        persistence, dispatch, and reassembly; the strategy owns
        ordering + filtering only.
    """

    factory_protocol_name: str = "sharding_strategy"
    protocol_schema_version: int = 1

    @classmethod
    def strategy_name(cls) -> str:
        """
            Stable identifier the
            :func:`expand_matrix` service uses to resolve the
            strategy.
        """
        raise NotImplementedError("Subclasses must implement strategy_name")

    @classmethod
    def describe(cls) -> StrategyDescription:
        """
            Return the strategy's :class:`StrategyDescription`.
        """
        raise NotImplementedError("Subclasses must implement describe")

    @classmethod
    def expand(
            cls,
            *,
            matrix_spec,  # MatrixSpec — avoid circular import
            runtime_history=None
        ) -> List[ExpandedShard]:
        """
            Produce the ordered list of :class:`ExpandedShard`
            rows for the supplied matrix spec.

            :raises: SemanticError, MatrixSpecInvalidError
        """
        raise NotImplementedError("Subclasses must implement expand")
