"""
.. module:: security.rbac.extensions.project_roles
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-tree project role presets shipped with the service.

.. moduleauthor:: Automation Mojo LLC

Each preset declares the ``project:<action>`` keys it grants. The
evaluator expands a live ``project:<id>:<action>`` evaluation by
matching the preset form — role presets are reusable across every
project.
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


class ProjectOwnerRole(RoleExtension):
    """
        Full administrative access to a single project.
    """

    resource_extension_name: str = "role_extension"
    role_name: str = "project-owner"
    description: str = "Full administrative access to one project."
    permissions: tuple = (
        PermissionGrant(permission_key="project:projects.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:projects.admin", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:members.write", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:variables.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:variables.write", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:secrets.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:secrets.write", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:secrets.rotate", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:runs.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:runs.dispatch", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:runs.cancel", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:artifacts.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:artifacts.promote", effect=PermissionEffect.ALLOW),
    )


class ProjectEditorRole(RoleExtension):
    """
        Day-to-day contributor: dispatches and cancels runs, reads
        secrets, edits variables. Cannot mutate project settings or
        members.
    """

    resource_extension_name: str = "role_extension"
    role_name: str = "project-editor"
    description: str = "Dispatch, cancel, and edit runs; read project secrets."
    permissions: tuple = (
        PermissionGrant(permission_key="project:projects.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:variables.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:variables.write", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:secrets.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:runs.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:runs.dispatch", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:runs.cancel", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:artifacts.read", effect=PermissionEffect.ALLOW),
    )


class ProjectViewerRole(RoleExtension):
    """
        Read-only project access.
    """

    resource_extension_name: str = "role_extension"
    role_name: str = "project-viewer"
    description: str = "Read-only access to one project."
    permissions: tuple = (
        PermissionGrant(permission_key="project:projects.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:variables.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:runs.read", effect=PermissionEffect.ALLOW),
        PermissionGrant(permission_key="project:artifacts.read", effect=PermissionEffect.ALLOW),
    )
