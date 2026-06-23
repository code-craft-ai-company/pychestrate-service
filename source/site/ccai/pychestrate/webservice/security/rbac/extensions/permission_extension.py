"""
.. module:: security.rbac.extensions.permission_extension
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ResourceExtension base declaring permission key packs.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import ClassVar, Tuple

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension


@dataclass(frozen=True)
class PermissionDescriptor:
    """
        Metadata returned by a ``PermissionExtension`` for one key.

        :param permission_key: Canonical key string.
        :param description: Free-form description.
        :param namespace: ``system`` | ``project``.
    """
    permission_key: str
    description: str
    namespace: str


class PermissionExtension(ResourceExtension):
    """
        Base class declaring a pack of permission keys.

        Implementations set :attr:`permission_keys` to the keys they
        contribute and override :meth:`describe` to return a
        :class:`PermissionDescriptor` per key.
    """

    resource_extension_name: ClassVar[str] = "permission_extension"
    permission_keys: ClassVar[Tuple[str, ...]] = ()

    @classmethod
    def describe(cls, *, permission_key: str) -> PermissionDescriptor:
        """
            Return metadata (description, namespace) for a key.

            :param permission_key: The key to describe.

            :returns: The :class:`PermissionDescriptor`.
        """
        raise NotImplementedError("Subclasses must implement describe")
