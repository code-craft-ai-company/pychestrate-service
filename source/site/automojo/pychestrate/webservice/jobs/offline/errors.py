"""
.. module:: jobs.offline.errors
    :synopsis: Offline-tolerance exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class OfflineError(Exception):
    """
        Base class for recoverable offline-tolerance errors.
    """


class ReplaySeqGapError(OfflineError):
    """
        Raised when an inbound replay record's sequence skips
        the expected next-sequence on the cursor — the client
        lost track of its replay position and needs to re-fetch.
    """


class ReplayAuthError(OfflineError):
    """
        Raised when the authenticated client_id on a replay post
        does not match the cursor's owning client.
    """
