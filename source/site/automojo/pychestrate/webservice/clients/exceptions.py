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


class CertificateAuthorityUnavailableError(Exception):
    """
        Raised when :func:`ca_adapter.sign_csr` is invoked before the
        service bootstrap has installed an active CA handle. REST / wire
        layers translate to HTTP 503.
    """


class CsrValidationError(Exception):
    """
        Raised when a submitted CSR cannot be parsed, fails signature
        verification, or uses an unacceptable key algorithm. REST / wire
        layers translate to HTTP 400.
    """


class CsrScopeMismatchError(Exception):
    """
        Raised when the Subject CN of a submitted CSR does not match the
        pod name scoped by the enrollment token. REST / wire layers
        translate to HTTP 403 with ``reason=scope_mismatch``.
    """


class CertRevokedError(Exception):
    """
        Raised when a caller presents a certificate serial that has
        already been recorded in ``clients_client_revocations``. REST /
        wire layers translate to HTTP 403 with
        ``reason=revoked_cert_presented``.
    """
