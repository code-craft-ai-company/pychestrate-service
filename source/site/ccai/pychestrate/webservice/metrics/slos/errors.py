"""
.. module:: metrics.slos.errors
    :synopsis: SLO-views exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class SLOError(Exception):
    """
        Base for recoverable SLO errors.
    """


class SLONotFoundError(SLOError):
    """
        Raised when a lookup misses.
    """


class SLOConflictError(SLOError):
    """
        Raised when (project, name) UNIQUE is violated.
    """


class SLOKindUnknownError(SLOError):
    """
        Raised when an SLO references a kind with no registered
        factory.
    """


class SLOConfigInvalidError(SLOError):
    """
        Raised when an SLO's definition_config payload fails
        the kind's validation.
    """
