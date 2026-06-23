"""
.. module:: resources.pools.events
    :synopsis: Pool bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class PoolEventTopics:
    """
        Resource-pool bus topics.
    """
    CREATED = "pychestrate.resource.pool.created"
    DELETED = "pychestrate.resource.pool.deleted"
    MEMBER_ADDED = "pychestrate.resource.pool.member_added"
    MEMBER_REMOVED = "pychestrate.resource.pool.member_removed"
