"""
.. module:: resources.usage_history.errors
    :synopsis: Usage-history exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class UsageHistoryError(Exception):
    """
        Base for recoverable usage-history errors.
    """


class TimelineEventNotFoundError(UsageHistoryError):
    """
        Raised when an event lookup misses.
    """
