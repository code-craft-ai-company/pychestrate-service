"""
.. module:: metrics.dashboards.events
    :synopsis: Project-dashboards bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class DashboardEventTopics:
    """
        Project-dashboards bus topics.
    """
    CREATED = "entity.dashboard.created"
    UPDATED = "entity.dashboard.updated"
    DELETED = "entity.dashboard.deleted"
