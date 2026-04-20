"""
.. module:: secrets.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception types raised by the secrets vault service.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class SecretAlreadyExistsError(Exception):
    """
        Raised when put_secret finds an existing row for the same secret_ref.
    """


class SecretNotFoundError(Exception):
    """
        Raised when a lookup by secret_ref finds nothing.
    """


class SecretAccessDeniedError(Exception):
    """
        Raised when ACL evaluation denies the requested action.
    """


class SecretReadTimeoutError(Exception):
    """
        Raised when a backend read exceeds aspects.timeout_seconds.
    """


class SecretBackendUnavailableError(Exception):
    """
        Raised when a backend's transport fails beyond aspects.retry_budget.
    """


class SecretVersionExpiredError(Exception):
    """
        Raised when a reader references a version past its grace window.
    """


class AuditUnavailableError(Exception):
    """
        Raised when secrets writes are blocked because the audit sink
        is unhealthy (NFR-4: writes fail closed).
    """
