"""
.. module:: orchestration.build.errors
    :synopsis: Build-orchestration exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class BuildError(Exception):
    """
        Base for recoverable build-orchestration errors.
    """


class BuildRunNotFoundError(BuildError):
    """
        Raised when a build-run lookup misses.
    """


class BuildRunnerKindUnknownError(BuildError):
    """
        Raised when a runner_kind references a name with no
        registered factory.
    """


class BuildInputsInvalidError(BuildError):
    """
        Raised when caller-supplied :class:`BuildRunInputs`
        violates an M1 invariant.
    """
