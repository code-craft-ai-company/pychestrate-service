"""
.. module:: security.auth
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 1-authentication feature — sessions, providers, MFA.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import register_factory_implementation
from automojo.pychestrate.webservice.security.auth.factories.local_provider import LocalCredentialAuthProvider
from automojo.pychestrate.webservice.security.auth.factories.stdlib_scrypt_hasher import (
    StdlibScryptPasswordHasher,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree reference implementations for the
        ``auth_provider`` and ``password_hasher`` factory protocols.

        OIDC and SAML providers land in M2. Production deployments
        install a stronger ``password_hasher`` (e.g. ``pychestrate-ext-auth-argon2id``)
        at a lower ``PRECEDENCE`` so it resolves ahead of the in-tree
        stdlib-scrypt fallback.

        :returns: None.
    """
    register_factory_implementation(implementation=LocalCredentialAuthProvider)
    register_factory_implementation(implementation=StdlibScryptPasswordHasher)
    return
