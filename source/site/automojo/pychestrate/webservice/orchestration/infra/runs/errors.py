"""
.. module:: orchestration.infra.runs.errors
    :synopsis: Infra-orchestration exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class InfraError(Exception):
    """
        Base for recoverable infra-orchestration errors.
    """


class InfraRunNotFoundError(InfraError):
    """
        Raised when a lookup misses.
    """


class InfraDriverUnknownError(InfraError):
    """
        Raised when ``trigger_run`` references a driver_name
        with no registered factory.
    """


class InfraInputsInvalidError(InfraError):
    """
        Raised when caller-supplied inputs violate an invariant.
    """


class InfraEnvironmentStateError(InfraError):
    """
        Raised when the bound environment is in a state that
        forbids the requested action (e.g. apply against an
        archived environment).
    """
