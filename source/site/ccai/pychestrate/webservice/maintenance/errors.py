"""
.. module:: maintenance.errors
    :synopsis: Maintenance-mode exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class MaintenanceError(Exception):
    """
        Base for recoverable maintenance-mode errors.
    """


class MaintenanceScopeInvalidError(MaintenanceError):
    """
        Raised when a scope identifier violates the
        ``"service" | "project:<slug>"`` shape.
    """


class MaintenanceScopeNotFoundError(MaintenanceError):
    """
        Raised when a lookup misses.
    """
