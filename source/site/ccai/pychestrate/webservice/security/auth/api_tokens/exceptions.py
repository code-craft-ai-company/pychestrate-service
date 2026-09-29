"""
.. module:: security.auth.api_tokens.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception types raised by the API-token service.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Optional


class ApiTokenValidationError(ValueError):
    """
        Raised when a token or service-account request carries an
        invalid field (empty name, unsupported scope, lifetime out of
        range). The message is safe to show to the caller.

        ``field`` names the request field the message is about
        (``name``, ``expires_in_days``, ``scope``, ``login_name``), so
        a form can show it next to that input; it is ``None`` when the
        message is about the request as a whole.
    """

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        self.field: Optional[str] = field
        super().__init__(message)
        return


class ApiTokenNotFoundError(LookupError):
    """
        Raised when a token id does not name an existing token (or
        names one the caller may not see).
    """


class ApiTokenRejectedError(Exception):
    """
        Raised when a presented token cannot authenticate: unknown,
        expired, revoked, or belonging to an account that is not
        active. :attr:`reason` names which, for logs; callers answer
        the client with one generic message.
    """

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason: str = reason
        return


class ServiceAccountNotFoundError(LookupError):
    """
        Raised when a user id does not name a service account.
    """
