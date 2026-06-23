"""
.. module:: clients.enrollment
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Client enrollment — token issuance, redemption, revocation.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.clients.enrollment.factories.csr_subject_verifier import (
    CsrSubjectVerifier,
)
from ccai.pychestrate.webservice.clients.enrollment.factories.scope_identity_verifier import (
    ScopeIdentityVerifier,
)
from ccai.pychestrate.webservice.clients.enrollment.factories.stdlib_token_issuer import (
    StdlibHmacTokenIssuer,
)
from ccai.pychestrate.webservice.extensions.registry import register_factory_implementation


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``enrollment_token_issuer`` +
        ``client_identity_verifier`` factory implementations. Both
        M1 (:class:`ScopeIdentityVerifier`) and M2
        (:class:`CsrSubjectVerifier`) verifiers are registered — the
        host's ``PRECEDENCE`` ordering picks the CSR verifier first
        (``PRECEDENCE=100``) while leaving the M1 verifier reachable
        as a deliberate fallback via ``by_order`` lookups.

        :returns: None.
    """
    register_factory_implementation(implementation=StdlibHmacTokenIssuer)
    register_factory_implementation(implementation=ScopeIdentityVerifier)
    register_factory_implementation(implementation=CsrSubjectVerifier)
    return
