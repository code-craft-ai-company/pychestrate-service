"""
.. module:: metrics.alerts.errors
    :synopsis: Alerts-budgets exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class AlertError(Exception):
    """
        Base for recoverable alert errors.
    """


class AlertRuleNotFoundError(AlertError):
    """
        Raised when a rule lookup misses.
    """


class AlertRuleConflictError(AlertError):
    """
        Raised when (project, name) UNIQUE is violated on
        create.
    """


class AlertRuleKindUnknownError(AlertError):
    """
        Raised when a rule references a kind with no
        registered factory.
    """


class AlertRuleConfigInvalidError(AlertError):
    """
        Raised when a rule's config payload fails the kind's
        validation.
    """
