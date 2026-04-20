"""
.. module:: security.rbac.extensions.role_extension
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ResourceExtension base declaring role presets.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import ClassVar, Tuple

from automojo.pychestrate.webservice.extensions.resource_extension import ResourceExtension
from automojo.pychestrate.webservice.security.rbac.models import PermissionEffect


@dataclass(frozen=True)
class PermissionGrant:
    """
        One (permission_key, effect) pair attached to a role preset.

        :param permission_key: Canonical permission key.
        :param effect: ALLOW | DENY.
    """
    permission_key: str
    effect: PermissionEffect


class RoleExtension(ResourceExtension):
    """
        Base class declaring a role preset.

        Implementations set :attr:`role_name`, :attr:`description`, and
        :attr:`permissions` to the grants the preset carries.
    """

    resource_extension_name: ClassVar[str] = "role_extension"
    role_name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    permissions: ClassVar[Tuple[PermissionGrant, ...]] = ()
