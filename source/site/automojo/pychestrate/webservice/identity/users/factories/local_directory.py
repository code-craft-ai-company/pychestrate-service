"""
.. module:: identity.users.factories.local_directory
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Local-database reference implementation of UserDirectorySourceProtocol.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Iterator

from automojo.pychestrate.webservice.identity.users.factories.user_directory_source import (
    ExternalGroupRecord,
    ExternalUserRecord,
    UserDirectorySourceProtocol,
)


class LocalDatabaseUserDirectorySource(UserDirectorySourceProtocol):
    """
        Reference implementation of ``user_directory_source`` that treats
        the local ``identity_users`` / ``identity_groups`` tables as the
        authority. Running a sync against this source is a no-op: there is
        no external system to pull from, so the diff is always empty.

        The implementation exists so that extension-host resolution can
        always return a registered implementation for ``source_name ==
        "local"`` without special-casing the absence of external sources.
    """

    factory_protocol_name: str = "user_directory_source"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def source_name(cls) -> str:
        rtnval = "local"
        return rtnval

    @classmethod
    def iter_user_records(cls) -> Iterator[ExternalUserRecord]:
        rtnval = iter(())
        return rtnval

    @classmethod
    def iter_group_records(cls) -> Iterator[ExternalGroupRecord]:
        rtnval = iter(())
        return rtnval
