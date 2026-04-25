"""
.. module:: orchestration.pipelines.sharding.factories.fail_fast_strategy
    :synopsis: FailFastCartesianStrategy — cartesian + cancel-on-failure.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from automojo.pychestrate.webservice.orchestration.pipelines.sharding.factories.cartesian_strategy import (
    CartesianShardingStrategy,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.factories.strategy_protocol import (
    ExpandedShard,
    ShardingStrategyProtocol,
    StrategyDescription,
)


FAIL_FAST_STRATEGY_NAME: str = "cartesian-fail-fast"


class FailFastCartesianStrategy(ShardingStrategyProtocol):
    """
        Cartesian expansion + ``should_cancel_on_failure``
        flagged as True. Emits the same shard order as
        :class:`CartesianShardingStrategy`; the M2 reassembly
        layer reads :attr:`StrategyDescription.should_cancel_on_failure`
        to drive the cancellation handshake with
        ``5-cancel-reconcile``.
    """

    factory_protocol_name: str = "sharding_strategy"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1100

    @classmethod
    def strategy_name(cls) -> str:
        rtnval = FAIL_FAST_STRATEGY_NAME
        return rtnval

    @classmethod
    def describe(cls) -> StrategyDescription:
        rtnval = StrategyDescription(
            strategy_name=FAIL_FAST_STRATEGY_NAME,
            description=(
                "Cartesian product expansion with fail-fast cancellation: "
                "the first failing shard cancels its siblings."
            ),
            requires_runtime_history=False,
            should_cancel_on_failure=True,
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
        rtnval = CartesianShardingStrategy.expand(
            matrix_spec=matrix_spec, runtime_history=runtime_history,
        )
        return rtnval
