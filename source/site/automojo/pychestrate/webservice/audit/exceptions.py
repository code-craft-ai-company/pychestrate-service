"""
.. module:: audit.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception types raised by the audit service.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class UnknownAuditKindError(Exception):
    """
        Raised when ``capture_event`` receives a kind that isn't in the
        registered catalog.
    """


class AuditChainBrokenError(Exception):
    """
        Raised when the chain verifier detects a mismatch between stored
        and recomputed hashes.
    """
