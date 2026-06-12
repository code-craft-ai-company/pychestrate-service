"""
.. module:: orchestration.pipelines.sharding.errors
    :synopsis: Sharding exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class ShardingError(Exception):
    """
        Base for recoverable sharding errors.
    """


class ShardSetNotFoundError(ShardingError):
    """
        Raised when a shard-set lookup misses.
    """


class ShardingStrategyNotFoundError(ShardingError):
    """
        Raised when ``expand_matrix`` is called with a
        ``strategy_name`` that no registered
        :class:`ShardingStrategyProtocol` implementation claims.
    """


class MatrixSpecInvalidError(ShardingError):
    """
        Raised when the matrix spec violates an M1 invariant —
        empty dimensions, empty value lists, conflicting
        includes/excludes.
    """


class ShardSetTimedOutError(ShardingError):
    """
        Raised internally during the M2 deadline sweep. Surfaced
        in metrics; never bubbles to callers.
    """
