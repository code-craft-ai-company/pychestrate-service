"""
.. module:: security.rbac
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 1-rbac feature — role, permission, and binding evaluation.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import register_resource_extension

from automojo.pychestrate.webservice.security.rbac.cache import wire_cache_invalidation
from automojo.pychestrate.webservice.security.rbac.extensions.core_permissions import (
    CorePermissionExtension,
)
from automojo.pychestrate.webservice.security.rbac.extensions.core_roles import (
    AuditorRole,
    SystemAdminRole,
)
from automojo.pychestrate.webservice.security.rbac.extensions.permission_extension import (
    PermissionExtension,
)
from automojo.pychestrate.webservice.security.rbac.extensions.project_permissions import (
    ProjectPermissionExtension,
)
from automojo.pychestrate.webservice.security.rbac.extensions.project_roles import (
    ProjectEditorRole,
    ProjectOwnerRole,
    ProjectViewerRole,
)
from automojo.pychestrate.webservice.security.rbac.extensions.role_extension import RoleExtension


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``PermissionExtension`` and ``RoleExtension``
        packs shipped with the service, and wire the RBAC cache
        invalidation subscribers.

        :returns: None.
    """
    register_resource_extension(base_class=PermissionExtension, extension=CorePermissionExtension)
    register_resource_extension(base_class=PermissionExtension, extension=ProjectPermissionExtension)
    register_resource_extension(base_class=RoleExtension, extension=SystemAdminRole)
    register_resource_extension(base_class=RoleExtension, extension=AuditorRole)
    register_resource_extension(base_class=RoleExtension, extension=ProjectOwnerRole)
    register_resource_extension(base_class=RoleExtension, extension=ProjectEditorRole)
    register_resource_extension(base_class=RoleExtension, extension=ProjectViewerRole)
    wire_cache_invalidation()
    return
