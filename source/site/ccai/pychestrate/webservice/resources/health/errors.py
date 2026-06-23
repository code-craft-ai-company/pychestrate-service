"""
.. module:: resources.health.errors
    :synopsis: Resource-health exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class HealthError(Exception):
    """
        Base for recoverable resource-health errors.
    """


class HealthRecordNotFoundError(HealthError):
    """
        Raised when a lookup misses.
    """


class HealthRecordConflictError(HealthError):
    """
        Raised when seeding a duplicate row for the same
        resource.
    """
