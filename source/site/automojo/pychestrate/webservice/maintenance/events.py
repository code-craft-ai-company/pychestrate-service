"""
.. module:: maintenance.events
    :synopsis: Maintenance-mode bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class MaintenanceEventTopics:
    """
        Maintenance-mode bus topics.
    """
    MODE_CHANGED = "entity.maintenance.mode_changed"
    MODE_CLEARED = "entity.maintenance.mode_cleared"
    DRAIN_STARTED = "entity.maintenance.drain_started"
    DRAIN_ENDED = "entity.maintenance.drain_ended"
