"""
.. module:: jobs.cancel.errors
    :synopsis: Cancel-RPC exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class CancelError(Exception):
    """
        Base class for recoverable cancel-RPC errors.
    """


class CancelTransportError(CancelError):
    """
        Raised when the transport adapter fails to deliver the
        cancel RPC. The cancel-request row records the failure
        and the offline-tolerance queue (M1 of
        ``5-offline-tolerance``) takes over.
    """


class CancelDuplicateRequestError(CancelError):
    """
        Raised when a second cancel request lands for a run that
        already has an open one. The partial unique index on
        ``run_id`` enforces the invariant at the DB layer.
    """
