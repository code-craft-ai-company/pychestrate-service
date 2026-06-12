"""
.. module:: orchestration.test.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Test-orchestration exception hierarchy.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class TestOrchestrationError(Exception):
    """
        Base for recoverable test-orchestration errors.
    """


class TestRunNotFoundError(TestOrchestrationError):
    """
        Raised when ``trigger_run`` references a catalog entry that
        does not exist or has been retired.
    """


class CapabilityMismatchError(TestOrchestrationError):
    """
        Raised when no candidate pod satisfies the catalog entry's
        required capability tags.
    """


class DispatchFailedError(TestOrchestrationError):
    """
        Raised when the underlying ``5-job-dispatch`` call fails
        for a reason other than transport. Wraps the inner cause.
    """
