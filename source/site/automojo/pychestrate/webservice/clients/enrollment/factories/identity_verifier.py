"""
.. module:: clients.enrollment.factories.identity_verifier
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: FactoryProtocolBase for inbound client-identity verification.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, Mapping, Optional

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


@dataclass(frozen=True)
class TokenScope:
    """
        Scope values committed at token issue time. The verifier uses
        these to reject enrollment attempts whose inbound payload
        disagrees with the token scope.

        :param project_id: Owning project UUID.
        :param pod_name: Pod the agent claims.
    """
    project_id: str
    pod_name: str


@dataclass(frozen=True)
class EnrollmentPayload:
    """
        Normalized inbound payload submitted by an agent during token
        redemption. M1 passes the pod name + reported agent version; M2
        extends with CSR DER + attestation blobs.

        :param pod_name: Pod name the agent claims.
        :param agent_version: Reported agent version string.
        :param transport_name: Transport name the agent plans to use.
        :param extras: Opaque additional fields the verifier may inspect.
    """
    pod_name: str
    agent_version: Optional[str]
    transport_name: Optional[str]
    extras: Mapping[str, Any]


@dataclass(frozen=True)
class VerificationReport:
    """
        Outcome of an identity verification.

        :param accepted: Whether the enrollment request passes policy.
        :param reason: Short code explaining a rejection, empty on accept.
    """
    accepted: bool
    reason: str


class ClientIdentityVerifierProtocol(FactoryProtocolBase):
    """
        Contract for verifying inbound enrollment payloads beyond the
        token match. M1 verifiers check pod_name parity with the token
        scope; M2 verifiers add CSR subject validation, attestation
        checks, and per-organization policy hooks.
    """

    factory_protocol_name: str = "client_identity_verifier"
    protocol_schema_version: int = 1

    @classmethod
    def algorithm_name(cls) -> str:
        """
            Canonical verifier identifier.

            :returns: Algorithm string.
        """
        raise NotImplementedError("Subclasses must implement algorithm_name")

    @classmethod
    def verify(
            cls,
            *,
            token_scope: TokenScope,
            payload: EnrollmentPayload
        ) -> VerificationReport:
        """
            Decide whether to accept an enrollment request.

            :param token_scope: The scope the token was issued against.
            :param payload: Normalized inbound payload.

            :returns: :class:`VerificationReport`.
        """
        raise NotImplementedError("Subclasses must implement verify")
