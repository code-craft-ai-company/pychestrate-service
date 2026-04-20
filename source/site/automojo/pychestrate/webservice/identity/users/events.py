"""
.. module:: identity.users.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 1-user-management.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
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
    GROUP_CREATED: str = "entity.group.created"
    GROUP_DELETED: str = "entity.group.deleted"
    GROUP_MEMBERSHIP_CHANGED: str = "entity.group.membership.changed"
