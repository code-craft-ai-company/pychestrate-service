"""
.. module:: orchestration.infra.environment.errors
    :synopsis: Environment-registry exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class EnvironmentError(Exception):
    """
        Base for recoverable environment errors.
    """


class EnvironmentNotFoundError(EnvironmentError):
    """
        Raised when a lookup misses.
    """


class EnvironmentKindUnknownError(EnvironmentError):
    """
        Raised when a declare references a kind with no
        registered factory.
    """


class EnvironmentAttrsInvalidError(EnvironmentError):
    """
        Raised when attrs fail the kind's input validation.
    """


class EnvironmentStateError(EnvironmentError):
    """
        Raised when a state-transitioning op is requested
        against a row in an incompatible state — e.g. archiving
        a destroyed env.
    """


class EnvironmentNameConflictError(EnvironmentError):
    """
        Raised when the (project, kind, name) UNIQUE is
        violated on declare.
    """
