"""
.. module:: security.auth.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception types raised by the authentication service.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
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


class MfaMethodUnknownError(Exception):
    """
        Raised when a caller references a method_name with no
        registered ``MFAMethodExtension``.
    """


class MfaEnrollmentNotFoundError(Exception):
    """
        Raised when a per-(user, method) enrollment lookup misses.
    """


class MfaChallengeRejectedError(Exception):
    """
        Raised when a verify_response call fails its constant-time
        compare.
    """


class MfaChallengeExpiredError(Exception):
    """
        Raised when a challenge is consumed past its TTL.
    """


class MfaChallengeUnknownError(Exception):
    """
        Raised when a challenge id lookup misses.
    """


class MfaEnrollmentNotVerifiedError(Exception):
    """
        Raised when a verify_response is requested for an
        enrollment that has not yet completed its initial
        verify-on-enroll handshake.
    """
