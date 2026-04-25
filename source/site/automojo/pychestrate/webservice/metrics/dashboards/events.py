"""
.. module:: metrics.dashboards.events
    :synopsis: Project-dashboards bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class DashboardEventTopics:
    """
        Project-dashboards bus topics.
    """
    CREATED = "entity.dashboard.created"
    UPDATED = "entity.dashboard.updated"
    DELETED = "entity.dashboard.deleted"
