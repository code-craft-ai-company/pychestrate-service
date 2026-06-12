"""
.. module:: clients.enrollment.factories.scope_identity_verifier
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference ``client_identity_verifier`` — scope equality check.

.. moduleauthor:: Code Craft AI LLC

M1 policy: accept the enrollment when the inbound ``pod_name`` matches
the pod name committed at token-issue time. Production operators should
register a verifier that additionally checks CSR subject, attestation,
and any site-specific policy hooks.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.clients.enrollment.factories.identity_verifier import (
    ClientIdentityVerifierProtocol,
    EnrollmentPayload,
    TokenScope,
    VerificationReport,
)


SCOPE_VERIFIER_ALGORITHM: str = "phase2-scope-equality"


class ScopeIdentityVerifier(ClientIdentityVerifierProtocol):
    """
        Accept when the inbound ``pod_name`` matches the token scope.
        Rejects on any mismatch.
    """

    factory_protocol_name: str = "client_identity_verifier"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 2000

    @classmethod
    def algorithm_name(cls) -> str:
        rtnval = SCOPE_VERIFIER_ALGORITHM
        return rtnval

    @classmethod
    def verify(
            cls,
            *,
            token_scope: TokenScope,
            payload: EnrollmentPayload
        ) -> VerificationReport:
        if token_scope.pod_name != payload.pod_name:
            rtnval = VerificationReport(
                accepted=False,
                reason="pod_name_mismatch",
            )
            return rtnval

        rtnval = VerificationReport(accepted=True, reason="")
        return rtnval
