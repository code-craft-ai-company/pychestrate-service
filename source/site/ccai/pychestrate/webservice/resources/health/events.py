"""
.. module:: resources.health.events
    :synopsis: Resource-health bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class HealthEventTopics:
    """
        Resource-health bus topics. M1 emits SEEDED, PROBED and
        DROPPED. M2 adds the QUARANTINE_DEFERRED and
        BACKOFF_APPLIED topics tied to the M2 state machine.
    """
    SEEDED = "entity.resource.health.seeded"
    PROBED = "entity.resource.health.probed"
    DROPPED = "entity.resource.health.dropped"
