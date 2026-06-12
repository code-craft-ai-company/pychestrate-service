"""
.. module:: security.rbac.extensions.project_permissions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-tree permission pack shipping the project:<action> keys.

.. moduleauthor:: Code Craft AI LLC

Project permissions are declared in *preset* form (``project:<action>``)
without a per-instance project id. The evaluator matches a live
``project:<id>:<action>`` binding against the preset form when resolving
whether a role grants a project-scoped action. Role presets therefore
stay reusable across every project.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.security.rbac.extensions.permission_extension import (
    PermissionDescriptor,
    PermissionExtension,
)


_PROJECT_PERMISSION_DESCRIPTIONS = {
    "project:projects.read": "Read project membership and metadata",
    "project:projects.admin": "Administer project settings and lifecycle",
    "project:members.write": "Add, remove, and modify project members",
    "project:variables.read": "Read project-scoped global variables",
    "project:variables.write": "Create, update, and delete project-scoped variables",
    "project:secrets.read": "Read project-scoped secret metadata",
    "project:secrets.write": "Create and rotate project-scoped secrets",
    "project:secrets.rotate": "Rotate existing project-scoped secrets",
    "project:runs.read": "Read project run history and progress",
    "project:runs.dispatch": "Dispatch test and build runs for the project",
    "project:runs.cancel": "Cancel in-flight project runs",
    "project:artifacts.read": "Read project artifacts and result trees",
    "project:artifacts.promote": "Promote project artifacts to longer retention",
}


class ProjectPermissionExtension(PermissionExtension):
    """
        Reference ``PermissionExtension`` shipping the core ``project:*``
        permission keys consumed by Layer 2+ features.
    """

    resource_extension_name: str = "permission_extension"
    permission_keys: tuple = tuple(_PROJECT_PERMISSION_DESCRIPTIONS.keys())

    @classmethod
    def describe(cls, *, permission_key: str) -> PermissionDescriptor:
        description = _PROJECT_PERMISSION_DESCRIPTIONS.get(permission_key, "")
        namespace = "project"
        if ":" in permission_key:
            namespace = permission_key.split(":", 1)[0]

        rtnval = PermissionDescriptor(
            permission_key=permission_key,
            description=description,
            namespace=namespace,
        )
        return rtnval
