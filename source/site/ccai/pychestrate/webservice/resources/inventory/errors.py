"""
.. module:: resources.inventory.errors
    :synopsis: Exception hierarchy for the resource inventory.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class ResourceError(Exception):
    """
        Base for recoverable inventory errors.
    """


class ResourceNotFoundError(ResourceError):
    """
        Raised when a lookup misses.
    """


class ResourceIdentityConflictError(ResourceError):
    """
        Raised when a register call collides with an existing
        non-retired ``(kind, identity_hash)`` row.
    """


class ResourceKindUnknownError(ResourceError):
    """
        Raised when a register call references a ``kind`` that
        is not registered as a :class:`ResourceKindProtocol`
        implementation.
    """


class ResourceRetiredError(ResourceError):
    """
        Raised when a caller asks to change a retired resource: retirement is
        terminal and the record is kept as it was.
    """


class ResourceStateTransitionError(ResourceError):
    """
        Raised when a caller asks for a state transition that
        the kind's policy rejects.
    """
