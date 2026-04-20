"""
.. module:: secrets
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 1-secrets-vault feature — secret storage, rotation, and ACLs.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import register_factory_implementation

from automojo.pychestrate.webservice.secrets.factories.local_backend import LocalEncryptedSecretsBackend


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``secrets_backend`` reference implementation.

        :returns: None.
    """
    register_factory_implementation(implementation=LocalEncryptedSecretsBackend)
    return
