"""
.. module:: security.rbac
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 1-rbac feature — role, permission, and binding evaluation.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import register_resource_extension

from ccai.pychestrate.webservice.security.rbac.cache import wire_cache_invalidation
from ccai.pychestrate.webservice.security.rbac.extensions.core_permissions import (
    CorePermissionExtension,
)
from ccai.pychestrate.webservice.security.rbac.extensions.core_roles import (
    AuditorRole,
    SystemAdminRole,
)
from ccai.pychestrate.webservice.security.rbac.extensions.permission_extension import (
    PermissionExtension,
)
from ccai.pychestrate.webservice.security.rbac.extensions.project_permissions import (
    ProjectPermissionExtension,
)
from ccai.pychestrate.webservice.security.rbac.extensions.project_roles import (
    ProjectEditorRole,
    ProjectOwnerRole,
    ProjectViewerRole,
)
from ccai.pychestrate.webservice.security.rbac.extensions.role_extension import RoleExtension
from ccai.pychestrate.webservice.security.rbac.extensions.workflow_roles import WORKFLOW_ROLES


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
    for workflow_role in WORKFLOW_ROLES:
        register_resource_extension(base_class=RoleExtension, extension=workflow_role)
    register_resource_extension(base_class=RoleExtension, extension=ProjectOwnerRole)
    register_resource_extension(base_class=RoleExtension, extension=ProjectEditorRole)
    register_resource_extension(base_class=RoleExtension, extension=ProjectViewerRole)
    wire_cache_invalidation()
    return
