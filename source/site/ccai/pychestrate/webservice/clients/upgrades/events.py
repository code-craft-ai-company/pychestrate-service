"""
.. module:: clients.upgrades.events
    :synopsis: 3-agent-upgrade-channel event topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class UpgradeEventTopics:
    """
        Stable event-bus topics for the agent upgrade
        channel. M1 emits DRAFTED / STARTED /
        STAGE_STARTED + the per-offer OFFERED /
        SUCCEEDED / FAILED / INTEGRITY_FAILED topics; the
        promote / halt / resume topics land in M2.
    """
    DRAFTED: str = "entity.rollout.drafted"
    STARTED: str = "entity.rollout.started"
    STAGE_STARTED: str = "entity.rollout.stage_started"
    STAGE_COMPLETED: str = "entity.rollout.stage_completed"
    HALTED: str = "entity.rollout.halted"
    RESUMED: str = "entity.rollout.resumed"
    COMPLETED: str = "entity.rollout.completed"
    OFFERED: str = "entity.upgrade.offered"
    SUCCEEDED: str = "entity.upgrade.succeeded"
    FAILED: str = "entity.upgrade.failed"
    DEFERRED: str = "entity.upgrade.deferred"
    INTEGRITY_FAILED: str = "entity.upgrade.integrity_failed"
    PIN_SET: str = "entity.client.upgrade_pin_set"
    PIN_CLEARED: str = "entity.client.upgrade_pin_cleared"
