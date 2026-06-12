"""
.. module:: security.auth
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 1-authentication feature — sessions, providers, MFA.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import register_factory_implementation
from ccai.pychestrate.webservice.security.auth.factories.local_provider import LocalCredentialAuthProvider
from ccai.pychestrate.webservice.security.auth.factories.stdlib_scrypt_hasher import (
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
