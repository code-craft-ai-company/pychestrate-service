"""
.. module:: orchestration.test.compare.errors
    :synopsis: Compare-runs exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class CompareError(Exception):
    """
        Base for recoverable compare-runs errors.
    """


class CompareReportNotFoundError(CompareError):
    """
        Raised when a report lookup misses.
    """


class CompareInputInvalidError(CompareError):
    """
        Raised when caller supplies the same run id for both
        sides or the project ids do not agree.
    """


class NoMatchingDiffViewerError(CompareError):
    """
        Raised when no registered diff viewer accepts the
        artifact pair.
    """
