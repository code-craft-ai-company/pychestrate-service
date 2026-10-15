"""
.. module:: security.rbac.catalog
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Catalog loader for PermissionExtension and RoleExtension packs.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ccai.pychestrate.webservice.extensions.registry import list_resource_extensions
from ccai.pychestrate.webservice.security.rbac.exceptions import PermissionKeyCollisionError
from ccai.pychestrate.webservice.security.rbac.extensions.permission_extension import (
    PermissionDescriptor,
    PermissionExtension,
)
from ccai.pychestrate.webservice.security.rbac.extensions.role_extension import (
    PermissionGrant,
    RoleExtension,
)


@dataclass(frozen=True)
class CatalogSnapshot:
    """
        Immutable snapshot of registered permissions and roles.

        :param permissions: Mapping of permission_key to descriptor.
        :param roles: Mapping of role_name to tuple of grants.
        :param role_descriptions: Mapping of role_name to its description, so the Roles page can say what a built-in role is for.
    """
    permissions: Dict[str, PermissionDescriptor] = field(default_factory=dict)
    roles: Dict[str, Tuple[PermissionGrant, ...]] = field(default_factory=dict)
    role_descriptions: Dict[str, str] = field(default_factory=dict)


def load_catalog_from_registry() -> CatalogSnapshot:
    """
        Walk registered ``PermissionExtension`` and ``RoleExtension``
        subclasses and produce the canonical in-memory catalog.

        :returns: The :class:`CatalogSnapshot`.
        :raises: PermissionKeyCollisionError
    """
    permission_packs = list_resource_extensions(base_class=PermissionExtension)
    role_packs = list_resource_extensions(base_class=RoleExtension)

    permissions: Dict[str, PermissionDescriptor] = {}
    collisions: List[str] = []

    for pack in permission_packs:
        for key in pack.permission_keys:
            if key in permissions:
                collisions.append(key)
                continue
            descriptor = pack.describe(permission_key=key)
            permissions[key] = descriptor

    if len(collisions) > 0:
        err_msg_lines = ["Permission catalog load aborted — duplicate keys."]
        err_msg_lines.append("DUPLICATES: ({})".format(len(collisions)))
        for key in collisions:
            err_msg_lines.append("    {}".format(key))
        err_msg = os.linesep.join(err_msg_lines)
        raise PermissionKeyCollisionError(err_msg) from None

    roles: Dict[str, Tuple[PermissionGrant, ...]] = {}
    role_descriptions: Dict[str, str] = {}
    for role_pack in role_packs:
        roles[role_pack.role_name] = role_pack.permissions
        role_descriptions[role_pack.role_name] = str(role_pack.description or "")

    rtnval = CatalogSnapshot(permissions=permissions, roles=roles, role_descriptions=role_descriptions)
    return rtnval
