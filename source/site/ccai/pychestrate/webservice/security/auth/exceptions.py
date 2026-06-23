"""
.. module:: security.auth.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception types raised by the authentication service.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class AuthenticationError(Exception):
    """
        Raised when credential, state, or assertion validation fails. Emitted
        to the client as a bare 401 without leaking the failure reason.
    """


class SessionExpiredError(Exception):
    """
        Raised when a session cookie references an expired row.
    """


class SessionNotFoundError(Exception):
    """
        Raised when a session cookie references an unknown row.
    """


class MfaRequiredError(Exception):
    """
        Raised when local verification succeeds but MFA is still required.
    """
