"""
.. module:: orchestration.pipelines.sharding.events
    :synopsis: Sharding bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ShardingEventTopics:
    """
        Sharding bus topics. M1 emits ``EXPANDED`` and
        ``SHARD_BOUND``; M2 wires the COMPLETED /
        STATE_CHANGED / FAIL_FAST topics tied to the Layer-5
        run-state mirror.
    """
    EXPANDED = "entity.shard_set.expanded"
    SHARD_BOUND = "entity.shard.bound"
    SHARD_STATE_CHANGED = "entity.shard.state_changed"
    SET_COMPLETED = "entity.shard_set.completed"
    FAIL_FAST_TRIGGERED = "entity.shard_set.fail_fast_triggered"
