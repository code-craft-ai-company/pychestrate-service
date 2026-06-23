"""
.. module:: identity.users
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 1-user-management feature — canonical user/group identity records.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.identity.users.factories.local_directory import (
    LocalDatabaseUserDirectorySource,
)
from ccai.pychestrate.webservice.extensions.registry import register_factory_implementation


def register_builtin_extensions() -> None:
    """
        Register the in-tree reference implementations for the
        ``user_directory_source`` factory protocol.

        :returns: None.
    """
    register_factory_implementation(implementation=LocalDatabaseUserDirectorySource)
    return
