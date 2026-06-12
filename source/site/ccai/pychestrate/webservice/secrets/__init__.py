"""
.. module:: secrets
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 1-secrets-vault feature — secret storage, rotation, and ACLs.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import register_factory_implementation

from ccai.pychestrate.webservice.secrets.factories.local_backend import LocalEncryptedSecretsBackend


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``secrets_backend`` reference implementation.

        :returns: None.
    """
    register_factory_implementation(implementation=LocalEncryptedSecretsBackend)
    return
