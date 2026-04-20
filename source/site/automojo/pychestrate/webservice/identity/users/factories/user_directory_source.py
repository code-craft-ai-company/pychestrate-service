"""
.. module:: identity.users.factories.user_directory_source
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: FactoryProtocolBase for pluggable user directory sources.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Iterator, Optional

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


@dataclass(frozen=True)
class ExternalUserRecord:
    """
        One external user record produced by a ``user_directory_source``.

        :param external_id: Stable id in the external system.
        :param login_name: Unique login claimed by the source.
        :param primary_email: Contact email.
        :param display_name: Human-facing name.
        :param timezone: IANA timezone name.
        :param is_active: Whether the source considers this user active.
    """
    external_id: str
    login_name: str
    primary_email: str
    display_name: str
    timezone: str
    is_active: bool


@dataclass(frozen=True)
class ExternalGroupRecord:
    """
        One external group record produced by a ``user_directory_source``.

        :param external_id: Stable id in the external system.
        :param group_name: Unique group name.
        :param description: Free-form description.
        :param member_external_ids: External ids of group members.
    """
    external_id: str
    group_name: str
    description: str
    member_external_ids: tuple


class UserDirectorySourceProtocol(FactoryProtocolBase):
    """
        Contract for any ``user_directory_source`` implementation.

        Implementations yield the current full set of user and group records
        owned by the source. The directory sync loop diffs against the
        last-good snapshot and applies creates, updates, and deactivations
        through ``user_service``.
    """

    factory_protocol_name: str = "user_directory_source"
    protocol_schema_version: int = 1

    @classmethod
    def iter_user_records(cls) -> Iterator[ExternalUserRecord]:
        """
            Yield the current full set of user records owned by this source.

            :returns: Iterator over :class:`ExternalUserRecord`.
        """
        raise NotImplementedError("Subclasses must implement iter_user_records")

    @classmethod
    def iter_group_records(cls) -> Iterator[ExternalGroupRecord]:
        """
            Yield the current full set of group records owned by this source.

            :returns: Iterator over :class:`ExternalGroupRecord`.
        """
        raise NotImplementedError("Subclasses must implement iter_group_records")

    @classmethod
    def source_name(cls) -> str:
        """
            Return the identifier used as ``provisioning_source`` for
            records owned by this implementation.

            :returns: The source name string.
        """
        raise NotImplementedError("Subclasses must implement source_name")
