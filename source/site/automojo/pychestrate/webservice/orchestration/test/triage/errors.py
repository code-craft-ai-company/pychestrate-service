"""
.. module:: orchestration.test.triage.errors
    :synopsis: Triage / bug-linking exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class TriageError(Exception):
    """
        Base for recoverable triage errors.
    """


class TriageCaseNotFoundError(TriageError):
    """
        Raised when a case lookup misses.
    """


class TriageClassifierNotFoundError(TriageError):
    """
        Raised when no classifier is registered.
    """


class TriageStackSignatureInvalidError(TriageError):
    """
        Raised when the stack-signature input is empty / oversized.
    """


class TriageTrackerNotFoundError(TriageError):
    """
        Raised when a named bug-tracker driver cannot be resolved.
    """
