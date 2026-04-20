"""
.. module:: clients.enrollment
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Client enrollment — token issuance, redemption, revocation.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.clients.enrollment.factories.scope_identity_verifier import (
    ScopeIdentityVerifier,
)
from automojo.pychestrate.webservice.clients.enrollment.factories.stdlib_token_issuer import (
    StdlibHmacTokenIssuer,
)
from automojo.pychestrate.webservice.extensions.registry import register_factory_implementation


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``enrollment_token_issuer`` +
        ``client_identity_verifier`` factory implementations.

        :returns: None.
    """
    register_factory_implementation(implementation=StdlibHmacTokenIssuer)
    register_factory_implementation(implementation=ScopeIdentityVerifier)
    return
