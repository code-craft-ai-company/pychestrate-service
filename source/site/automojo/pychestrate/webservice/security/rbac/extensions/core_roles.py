"""
.. module:: security.rbac.extensions.core_roles
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-tree role presets shipped with the service.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.security.rbac.extensions.role_extension import (
    PermissionGrant,
    RoleExtension,
)
from automojo.pychestrate.webservice.security.rbac.models import PermissionEffect


class SystemAdminRole(RoleExtension):
    """
        Role preset that grants every in-tree ``system:*`` permission.
    """

    resource_extension_name: str = "role_extension"
    role_name: str = "system-admin"
    description: str = "Full administrative access to system-scoped capabilities."
    permissions: tuple = (
        PermissionGrant(permission_key="system:users.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:users.write", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:groups.admin", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:rbac.admin", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:rbac.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:secrets.admin", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:secrets.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:audit.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:flags.admin", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:directory.sync", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:auth.admin", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:auth.read", effect=PermissionEffect.ALLOW),
    )


class AuditorRole(RoleExtension):
    """
        Role preset limited to read access over audit and RBAC introspection.
    """

    resource_extension_name: str = "role_extension"
    role_name: str = "auditor"
    description: str = "Read-only access to audit records and RBAC catalog."
    permissions: tuple = (
        PermissionGrant(permission_key="system:audit.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="system:rbac.read", effect=PermissionEffect.ALLOW),
    )
