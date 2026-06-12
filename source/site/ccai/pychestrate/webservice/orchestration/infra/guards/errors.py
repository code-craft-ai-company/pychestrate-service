"""
.. module:: orchestration.infra.guards.errors
    :synopsis: Blast-radius-guards exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class GuardError(Exception):
    """
        Base for recoverable guard errors.
    """


class GuardAttachmentNotFoundError(GuardError):
    """
        Raised when an attachment lookup misses.
    """


class GuardRuleUnknownError(GuardError):
    """
        Raised when a caller references a rule_id with no
        registered factory.
    """


class GuardEnvironmentNotFoundError(GuardError):
    """
        Raised when the bound environment is not in the
        registry.
    """
