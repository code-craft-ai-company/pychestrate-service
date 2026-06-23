"""
.. module:: retention.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exceptions raised by 2-retention-policies service APIs.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class PolicyAlreadyExistsError(Exception):
    """
        Raised when a policy name collides within its scope.
    """


class PolicyNotFoundError(Exception):
    """
        Raised when a policy lookup has no matching row.
    """


class PolicyStateTransitionError(Exception):
    """
        Raised when a requested state transition is invalid (e.g.
        publishing a policy that is already archived).
    """


class UnsupportedRetentionActionError(Exception):
    """
        Raised when a referenced action_name has no registered
        implementation.
    """
