"""
.. module:: ingest.progress.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception hierarchy for the progress receiver.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class ProgressError(Exception):
    """
        Base class for recoverable progress-ingest errors.
    """


class ProgressUnknownRunError(ProgressError):
    """
        Raised when a progress payload references a run id whose
        ``run`` row does not exist or has no recorded receipt.
    """


class ProgressClientMismatchError(ProgressError):
    """
        Raised when the authenticated ``client_id`` of the
        forwarding connection does not match the
        ``DispatchReceipt.client_id`` recorded for the run. Surfaces
        as HTTP 403 at the transport boundary.
    """


class ProgressFormatError(ProgressError):
    """
        Raised when a progress payload fails the parser's structural
        check (missing required fields, malformed JSON, unknown
        format tag).
    """
