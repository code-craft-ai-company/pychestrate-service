"""
.. module:: resources.lease.errors
    :synopsis: Lease exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class LeaseError(Exception):
    """
        Base for recoverable lease errors.
    """


class LeaseNotFoundError(LeaseError):
    """
        Raised when a lookup misses.
    """


class LeaseStateError(LeaseError):
    """
        Raised when a heartbeat / release is requested against a
        lease in an incompatible state — e.g. heartbeating an
        already-expired lease.
    """


class LeaseAspectsInvalidError(LeaseError):
    """
        Raised when caller-supplied :class:`LeaseAspects` violates
        the M1 TTL clamp. The message names the offending field.
    """
