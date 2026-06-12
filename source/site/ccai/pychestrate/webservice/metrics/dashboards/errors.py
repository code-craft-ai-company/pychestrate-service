"""
.. module:: metrics.dashboards.errors
    :synopsis: Project-dashboards exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class DashboardError(Exception):
    """
        Base for recoverable dashboard errors.
    """


class DashboardNotFoundError(DashboardError):
    """
        Raised when a lookup misses.
    """


class DashboardConflictError(DashboardError):
    """
        Raised when a name conflict is detected at create
        time.
    """


class TileKindUnknownError(DashboardError):
    """
        Raised when a tile references a kind with no registered
        factory.
    """


class TileConfigInvalidError(DashboardError):
    """
        Raised when a tile config payload fails the kind's
        validation.
    """
