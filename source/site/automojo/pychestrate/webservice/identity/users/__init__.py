"""
.. module:: identity.users
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 1-user-management feature — canonical user/group identity records.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.identity.users.factories.local_directory import (
    LocalDatabaseUserDirectorySource,
)
from automojo.pychestrate.webservice.extensions.registry import register_factory_implementation


def register_builtin_extensions() -> None:
    """
        Register the in-tree reference implementations for the
        ``user_directory_source`` factory protocol.

        :returns: None.
    """
    register_factory_implementation(implementation=LocalDatabaseUserDirectorySource)
    return
