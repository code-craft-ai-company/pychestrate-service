"""
.. module:: identity.users.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 1-user-management.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class UserEventTopics:
    """
        String constants for every entity topic owned by 1-user-management.
    """

    USER_CREATED: str = "entity.user.created"
    USER_UPDATED: str = "entity.user.updated"
    USER_DEACTIVATED: str = "entity.user.deactivated"
    USER_REACTIVATED: str = "entity.user.reactivated"
    USER_ANONYMISED: str = "entity.user.anonymised"
    GROUP_CREATED: str = "entity.group.created"
    GROUP_DELETED: str = "entity.group.deleted"
    GROUP_MEMBERSHIP_CHANGED: str = "entity.group.membership.changed"
