"""
.. module:: clients.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception types raised by the client plane.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ClientNotFoundError(Exception):
    """
        Raised when a lookup by client_id / scope finds no row.
    """


class ClientAlreadyExistsError(Exception):
    """
        Raised when an enrollment attempt collides with an existing
        (project_id, pod_name) pair.
    """


class UnknownAttributeKindError(Exception):
    """
        Raised when a caller supplies an attribute value for a kind that
        is not registered via ``ClientAttributeExtension``.
    """


class InvalidAttributeValueError(Exception):
    """
        Raised when an attribute value does not match the kind's schema.
    """


class EnrollmentTokenNotFoundError(Exception):
    """
        Raised when a token_id or secret does not match any stored row.
    """


class EnrollmentTokenInvalidError(Exception):
    """
        Raised when a token is expired, already redeemed, or revoked.
    """


class EnrollmentRejectedError(Exception):
    """
        Raised when the identity verifier rejects the inbound enrollment
        payload.
    """
