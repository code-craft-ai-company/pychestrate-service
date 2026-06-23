"""
.. module:: metrics.slos.events
    :synopsis: SLO-views bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class SLOEventTopics:
    """
        SLO-views bus topics. M1 emits CREATED + DELETED +
        STATUS_COMPUTED; M2 wires the burn-rate alert
        attachment topics.
    """
    CREATED = "entity.slo.created"
    UPDATED = "entity.slo.updated"
    DELETED = "entity.slo.deleted"
    STATUS_COMPUTED = "entity.slo.status_computed"
    BUDGET_DEPLETED = "entity.slo.budget_depleted"
