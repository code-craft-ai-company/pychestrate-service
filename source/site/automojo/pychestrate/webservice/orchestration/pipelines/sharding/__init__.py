"""
.. module:: orchestration.pipelines.sharding
    :synopsis: 6-matrix-sharding — matrix expansion + dispatch.

Public surface:

* :class:`ShardSet`, :class:`ShardSpec`, :class:`ShardSetState`,
  :class:`ShardState` — persistence rows + enums.
* :class:`MatrixSpec`, :class:`MatrixDimensionFilter`,
  :class:`ExpandAspects`, :class:`ShardSetView`,
  :class:`ShardSpecView` — IO shapes.
* :func:`expand_matrix`, :func:`get_shard_set`,
  :func:`list_shards_for_set`, :func:`bind_shard_to_run`.
* :class:`ShardingStrategyProtocol` factory contract +
  reference :class:`CartesianShardingStrategy` /
  :class:`FailFastCartesianStrategy`.
* :class:`ShardingEventTopics`.
* Errors: :class:`ShardingError`,
  :class:`ShardSetNotFoundError`,
  :class:`ShardingStrategyNotFoundError`,
  :class:`MatrixSpecInvalidError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.errors import (
    MatrixSpecInvalidError,
    ShardSetNotFoundError,
    ShardingError,
    ShardingStrategyNotFoundError,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.events import (
    ShardingEventTopics,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.expansion import (
    MatrixDimensionFilter,
    MatrixSpec,
    canonicalize_matrix_spec,
    compute_shard_id,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.factories.cartesian_strategy import (
    CartesianShardingStrategy,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.factories.fail_fast_strategy import (
    FailFastCartesianStrategy,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.factories.strategy_protocol import (
    ShardingStrategyProtocol,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.models import (
    ShardSet,
    ShardSetState,
    ShardSpec,
    ShardState,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.service import (
    ExpandAspects,
    ShardSetView,
    ShardSpecView,
    bind_shard_to_run,
    expand_matrix,
    get_shard_set,
    list_shards_for_set,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`CartesianShardingStrategy` and
        :class:`FailFastCartesianStrategy` reference
        implementations.
    """
    register_factory_implementation(implementation=CartesianShardingStrategy)
    register_factory_implementation(implementation=FailFastCartesianStrategy)
    return
