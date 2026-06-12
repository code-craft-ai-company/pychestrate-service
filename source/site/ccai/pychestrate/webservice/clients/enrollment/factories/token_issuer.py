"""
.. module:: clients.enrollment.factories.token_issuer
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: FactoryProtocolBase for enrollment-token issuers.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass

from ccai.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


@dataclass(frozen=True)
class IssuedSecret:
    """
        The enrollment secret returned by an issuer.

        :param secret: Secret bytes encoded as an ASCII string. Returned to
                       the admin exactly once.
        :param stored_hash: The server-side digest the issuer expects
                            persisted in ``clients_enrollment_tokens.token_hash``.
        :param algorithm_name: Canonical algorithm name — stored alongside
                               the hash so older hashes continue to verify
                               after operators install a stronger issuer.
    """
    secret: str
    stored_hash: bytes
    algorithm_name: str


class EnrollmentTokenIssuerProtocol(FactoryProtocolBase):
    """
        Contract for generating, hashing, and verifying enrollment
        secrets. Implementations declare:

        - ``algorithm_name()``: canonical algorithm identifier.
        - ``generate()``: produce a fresh :class:`IssuedSecret`.
        - ``verify(secret, stored_hash)``: constant-time comparison.
    """

    factory_protocol_name: str = "enrollment_token_issuer"
    protocol_schema_version: int = 1

    @classmethod
    def algorithm_name(cls) -> str:
        """
            Canonical algorithm identifier stored on every issued token.

            :returns: Algorithm string.
        """
        raise NotImplementedError("Subclasses must implement algorithm_name")

    @classmethod
    def generate(cls, *, entropy_bits: int) -> IssuedSecret:
        """
            Produce a fresh enrollment secret + server-side digest.

            :param entropy_bits: Minimum acceptable secret entropy. The
                                 stdlib reference honors 128 bits.

            :returns: Populated :class:`IssuedSecret`.
        """
        raise NotImplementedError("Subclasses must implement generate")

    @classmethod
    def verify(cls, *, secret: str, stored_hash: bytes) -> bool:
        """
            Constant-time verification of a presented secret against the
            stored digest.

            :param secret: Secret the agent supplied.
            :param stored_hash: Digest loaded from the token row.

            :returns: True on match.
        """
        raise NotImplementedError("Subclasses must implement verify")
