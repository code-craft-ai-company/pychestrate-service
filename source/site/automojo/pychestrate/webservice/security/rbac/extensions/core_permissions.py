"""
.. module:: security.rbac.extensions.core_permissions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-tree permission pack shipping the core ``system:*`` keys.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.security.rbac.extensions.permission_extension import (
    PermissionDescriptor,
    PermissionExtension,
)


_CORE_PERMISSION_DESCRIPTIONS = {
    "system:users.read": "Read identity users and groups",
    "system:users.write": "Create, update, and deactivate identity users",
    "system:groups.admin": "Administer groups and group memberships",
    "system:rbac.admin": "Assign and revoke RBAC role bindings",
    "system:rbac.read": "Read RBAC roles, permissions, and bindings",
    "system:secrets.admin": "Administer secrets, ACLs, and rotation",
    "system:secrets.read": "Read secret metadata (never plaintext over REST)",
    "system:audit.read": "Read the audit record stream",
    "system:flags.admin": "Administer feature-flag lifecycle",
    "system:directory.sync": "Trigger a user_directory_source sync cycle",
    "system:auth.admin": "Administer authentication provider configuration",
    "system:auth.read": "Introspect active sessions and MFA enrollments",
    "system:resources.manage": (
        "Administer the resources surface "
        "(pools, IP pools, allocations, health probes)"
    ),
}


class CorePermissionExtension(PermissionExtension):
    """
        Reference ``PermissionExtension`` shipping the core ``system:*``
        permission keys consumed by Layer 1 features.
    """

    resource_extension_name: str = "permission_extension"
    permission_keys: tuple = tuple(_CORE_PERMISSION_DESCRIPTIONS.keys())

    @classmethod
    def describe(cls, *, permission_key: str) -> PermissionDescriptor:
        description = _CORE_PERMISSION_DESCRIPTIONS.get(permission_key, "")
        namespace = "system"
        if ":" in permission_key:
            namespace = permission_key.split(":", 1)[0]

        rtnval = PermissionDescriptor(
            permission_key=permission_key,
            description=description,
            namespace=namespace,
        )
        return rtnval
