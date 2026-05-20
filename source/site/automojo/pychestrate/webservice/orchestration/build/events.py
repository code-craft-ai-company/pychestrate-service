"""
.. module:: orchestration.build.events
    :synopsis: Build-orchestration bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class BuildEventTopics:
    """
        Build-orchestration bus topics. M1 emits TRIGGERED +
        STATE_CHANGED + COMPLETED; M2 wires the replay /
        reproducibility-mismatch / cache-allocated topics.
    """
    TRIGGERED = "entity.build.run_triggered"
    DISPATCHED = "entity.build.run_dispatched"
    STATE_CHANGED = "entity.build.run_state_changed"
    COMPLETED = "entity.build.run_completed"
    FAILED = "entity.build.run_failed"
    CANCELLED = "entity.build.run_cancelled"
