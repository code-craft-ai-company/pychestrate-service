"""
.. module:: orchestration.infra.runs.events
    :synopsis: Infra-orchestration bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class InfraEventTopics:
    """
        Infra-orchestration bus topics.
    """
    TRIGGERED = "entity.infra.run_triggered"
    DISPATCHED = "entity.infra.run_dispatched"
    PLAN_RECORDED = "entity.infra.run_plan_recorded"
    STATE_CHANGED = "entity.infra.run_state_changed"
    COMPLETED = "entity.infra.run_completed"
    FAILED = "entity.infra.run_failed"
    CANCELLED = "entity.infra.run_cancelled"
    REJECTED_BY_GUARD = "entity.infra.run_rejected_by_guard"
