"""
.. module:: variables
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 2-global-variables feature — typed configuration at system/project scope.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import register_factory_implementation
from automojo.pychestrate.webservice.variables.factories.database_resolver import (
    DatabaseVariableResolver,
)
from automojo.pychestrate.webservice.variables.factories.secret_ref_dereferencer import (
    VaultSecretRefDereferencer,
)


def register_builtin_extensions() -> None:
    """
        Register the reference :class:`DatabaseVariableResolver` for the
        ``variable_resolver`` factory and the reference
        :class:`VaultSecretRefDereferencer` for the
        ``secret_ref_dereferencer`` factory.

        :returns: None.
    """
    register_factory_implementation(implementation=DatabaseVariableResolver)
    register_factory_implementation(implementation=VaultSecretRefDereferencer)
    return
