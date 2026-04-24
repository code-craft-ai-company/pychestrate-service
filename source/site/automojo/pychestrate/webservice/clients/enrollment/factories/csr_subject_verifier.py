"""
.. module:: clients.enrollment.factories.csr_subject_verifier
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: M2 ``client_identity_verifier`` — CSR Subject CN check.

.. moduleauthor:: Automation Mojo LLC

M2 policy: the M1 ``ScopeIdentityVerifier`` rule still applies (inbound
``pod_name`` must match the token scope) AND — when a CSR is supplied —
the CSR Subject CN must also match ``pod_name``.

The verifier intentionally does **not** require a CSR: the service still
supports the M1 bearer-only redemption path for clients that have not
yet been updated to present a CSR. Callers that want the strict M2
"CSR required" policy should enforce it at the transport layer (refuse
bearer-only redemption) rather than here; that keeps the verifier's
contract compatible with both M1 and M2 flows without needing an opt-in
gate on the extension registry.

This verifier runs at ``PRECEDENCE=100`` so once it is registered it
wins over the M1 ``ScopeIdentityVerifier`` (``PRECEDENCE=2000``). Both
verifiers return identical results for payloads without a CSR, so the
precedence flip is observable only on payloads that do carry one.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from cryptography import x509
from cryptography.x509.oid import NameOID

from automojo.pychestrate.webservice.clients.enrollment.factories.identity_verifier import (
    ClientIdentityVerifierProtocol,
    EnrollmentPayload,
    TokenScope,
    VerificationReport,
)


CSR_SUBJECT_VERIFIER_ALGORITHM: str = "phase2-csr-subject"


class CsrSubjectVerifier(ClientIdentityVerifierProtocol):
    """
        M2 identity verifier. Requires that the submitted CSR's
        Subject CN matches the token scope, in addition to the M1
        pod_name equality check.
    """

    factory_protocol_name: str = "client_identity_verifier"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 100

    @classmethod
    def algorithm_name(cls) -> str:
        """
            Canonical verifier identifier.

            :returns: Algorithm string constant.
        """
        rtnval = CSR_SUBJECT_VERIFIER_ALGORITHM
        return rtnval

    @classmethod
    def verify(
            cls,
            *,
            token_scope: TokenScope,
            payload: EnrollmentPayload
        ) -> VerificationReport:
        """
            Check the payload in two stages:

            1. ``payload.pod_name`` must equal ``token_scope.pod_name``
               (same rule as the M1 verifier).
            2. When ``payload.csr_pem`` is present, the CSR must parse,
               its signature must verify, and its Subject CN must
               equal ``token_scope.pod_name``.

            When no CSR is supplied step 2 is skipped so the service
            remains compatible with M1 bearer-only clients. Operators
            who want to require a CSR should enforce that at the
            transport / REST layer rather than here.

            :param token_scope: The scope the token was issued against.
            :param payload: Normalized inbound payload.

            :returns: :class:`VerificationReport` describing the outcome.
        """
        if token_scope.pod_name != payload.pod_name:
            rtnval = VerificationReport(accepted=False, reason="pod_name_mismatch")
            return rtnval

        if payload.csr_pem is None or len(payload.csr_pem) == 0:
            rtnval = VerificationReport(accepted=True, reason="")
            return rtnval

        try:
            csr = x509.load_pem_x509_csr(payload.csr_pem)
        except ValueError:
            rtnval = VerificationReport(accepted=False, reason="csr_unparseable")
            return rtnval

        if csr.is_signature_valid is False:
            rtnval = VerificationReport(accepted=False, reason="csr_signature_invalid")
            return rtnval

        attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if len(attrs) == 0:
            rtnval = VerificationReport(accepted=False, reason="csr_cn_missing")
            return rtnval
        subject_cn = attrs[0].value
        if isinstance(subject_cn, bytes):
            subject_cn = subject_cn.decode("utf-8")

        if subject_cn != token_scope.pod_name:
            rtnval = VerificationReport(accepted=False, reason="scope_mismatch")
            return rtnval

        rtnval = VerificationReport(accepted=True, reason="")
        return rtnval
