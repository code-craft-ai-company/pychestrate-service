"""
.. module:: notifications.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exceptions raised by 2-notification-hub service APIs.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ChannelAlreadyExistsError(Exception):
    """
        Raised when a channel name collides within its scope.
    """


class ChannelNotFoundError(Exception):
    """
        Raised when a requested channel cannot be resolved.
    """


class UnsupportedChannelKindError(Exception):
    """
        Raised when no ``notification_channel`` implementation matches a kind.
    """


class TemplateNotFoundError(Exception):
    """
        Raised when no template with the given name is registered.
    """


class NotificationDispatchError(Exception):
    """
        Raised when a channel send fails at the protocol layer.
    """
