"""
.. module:: identity.users.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception types raised by the user management service.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class UserAlreadyExistsError(Exception):
    """
        Raised when a create_user call conflicts with an existing record.
    """


class UserNotFoundError(Exception):
    """
        Raised when a lookup by user_id returns no row.
    """


class DirectoryCollisionError(Exception):
    """
        Raised when two user_directory_source implementations claim the same
        ``login_name`` or ``(provisioning_source, external_id)`` pair.
    """


class DirectorySyncTransientError(Exception):
    """
        Raised when a directory source's transport is reachable but a single
        sync cycle failed. The caller is expected to retry on the next cycle.
    """
