"""
.. module:: notifications.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 2-notification-hub.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class NotificationEventTopics:
    """
        String constants for every entity topic owned by 2-notification-hub.
    """

    NOTIFICATION_DISPATCHED: str = "entity.notification.dispatched"
    NOTIFICATION_FAILED: str = "entity.notification.failed"
