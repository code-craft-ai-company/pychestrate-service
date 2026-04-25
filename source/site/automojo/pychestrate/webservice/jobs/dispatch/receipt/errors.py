"""
.. module:: jobs.dispatch.receipt.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception hierarchy for dispatch receipts.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class DispatchReceiptError(Exception):
    """
        Base class for recoverable receipt errors. Subclasses
        classify specific failure modes.
    """


class DuplicateRunReceiptError(DispatchReceiptError):
    """
        Raised when a second distinct receipt (different
        ``client_local_run_id``) arrives for the same ``run_id``.
        A run is scoped to exactly one client-local run id — the
        second observation signals a client-side bug and is
        rejected so it surfaces to operators.
    """


class ReceiptEnvelopeMismatchError(DispatchReceiptError):
    """
        Raised when a receipt's ``envelope_id`` does not match any
        persisted attempt's envelope for the referenced run. A
        mismatched receipt is never treated as authoritative.
    """


class ReceiptNotFoundError(DispatchReceiptError):
    """
        Raised by :func:`lookup_by_local` / :func:`lookup_by_run`
        when the strict variant is used and no row matches.
    """
