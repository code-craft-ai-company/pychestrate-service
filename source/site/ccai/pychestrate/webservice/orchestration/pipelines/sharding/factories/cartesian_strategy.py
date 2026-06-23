"""
.. module:: orchestration.pipelines.sharding.factories.cartesian_strategy
    :synopsis: CartesianShardingStrategy — full cartesian + includes/excludes.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List, Tuple

from ccai.pychestrate.webservice.orchestration.pipelines.sharding.expansion import (
    apply_includes_excludes,
    assign_sequence_in_group,
    cartesian_product,
    compute_shard_id,
    validate_matrix_spec,
)
from ccai.pychestrate.webservice.orchestration.pipelines.sharding.factories.strategy_protocol import (
    ExpandedShard,
    ShardingStrategyProtocol,
    StrategyDescription,
)


CARTESIAN_STRATEGY_NAME: str = "cartesian"


class CartesianShardingStrategy(ShardingStrategyProtocol):
    """
        Reference cartesian strategy. Honors ``includes`` +
        ``excludes`` on the matrix spec and emits shards in
        canonical lex order so a re-expand against the same
        :class:`MatrixSpec` produces the same shard-id sequence.
    """

    factory_protocol_name: str = "sharding_strategy"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def strategy_name(cls) -> str:
        rtnval = CARTESIAN_STRATEGY_NAME
        return rtnval

    @classmethod
    def describe(cls) -> StrategyDescription:
        rtnval = StrategyDescription(
            strategy_name=CARTESIAN_STRATEGY_NAME,
            description=(
                "Full cartesian product expansion with includes / "
                "excludes filters. Lex-ordered output."
            ),
            requires_runtime_history=False,
            should_cancel_on_failure=False,
            default_min_success_fraction=1.0,
        )
        return rtnval

    @classmethod
    def expand(
            cls,
            *,
            matrix_spec,
            runtime_history=None
        ) -> List[ExpandedShard]:
        validate_matrix_spec(matrix_spec=matrix_spec)
        cart = cartesian_product(dimensions=matrix_spec.dimensions)
        filtered = apply_includes_excludes(
            candidates=cart,
            includes=list(matrix_spec.includes or []),
            excludes=list(matrix_spec.excludes or []),
        )
        sequenced = assign_sequence_in_group(candidates=filtered)

        rtnval: List[ExpandedShard] = []
        for dim_values, parallel_group, sequence in sequenced:
            shard_id = compute_shard_id(dimension_values=dim_values)
            frozen_dims: Tuple[Tuple[str, str], ...] = tuple(
                sorted(dim_values.items())
            )
            rtnval.append(
                ExpandedShard(
                    shard_id=shard_id,
                    dimension_values=frozen_dims,
                    parallel_group=parallel_group,
                    sequence_in_group=sequence,
                )
            )
        return rtnval
