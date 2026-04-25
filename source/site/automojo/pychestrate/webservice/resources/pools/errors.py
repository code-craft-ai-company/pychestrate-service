"""
.. module:: resources.pools.errors
    :synopsis: Pool exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class PoolError(Exception):
    """
        Base for recoverable pool errors.
    """


class PoolNotFoundError(PoolError):
    """
        Raised when a lookup misses.
    """


class PoolMemberConflictError(PoolError):
    """
        Raised when a caller adds a resource that is already a
        member.
    """


class PoolEmptyError(PoolError):
    """
        Raised when ``pick_candidate`` finds no eligible members.
    """
