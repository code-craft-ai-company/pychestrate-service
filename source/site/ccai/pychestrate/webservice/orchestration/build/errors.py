"""
.. module:: orchestration.build.errors
    :synopsis: Build-orchestration exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
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


class BuildSourceIntegrationUnknownError(BuildError):
    """
        Raised when ``trigger_run`` is given a
        ``source_integration_id`` that resolves to no registered
        source-integration for the project.
    """


class BuildDispatchUnavailableError(BuildError):
    """
        Raised when ``trigger_run`` cannot dispatch the build job
        because the orchestration runtime has no
        :class:`JobDispatcher` wired -- the build service was used
        before :func:`set_active_job_dispatcher` ran.
    """


class BuildDispatchFailedError(BuildError):
    """
        Raised when the build job envelope was built but the
        underlying :meth:`JobDispatcher.dispatch` call failed (no
        eligible candidate, transport failure, ...). The BuildRun is
        left in ``FAILED`` with a ``final_state_reason`` describing
        the dispatch failure.
    """
