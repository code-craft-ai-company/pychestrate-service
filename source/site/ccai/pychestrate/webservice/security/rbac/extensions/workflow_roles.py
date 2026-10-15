"""
.. module:: security.rbac.extensions.workflow_roles
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Standard roles for the common ways people use the product (ADM-06).

.. moduleauthor:: Code Craft AI LLC

Building a role meant choosing from 73 permission keys, so the first thing an administrator did on a new installation was work out what a
"tester" or a "developer" needs. These presets answer that for the common workflows. They are built-in: they ship with the service, cannot
be edited in place, and follow the product as it gains features. An administrator who wants a variation copies one (Roles, Copy Role) and changes
the copy, which is then a custom role the administrator owns.

Every role is *what anyone who works in the product may see* (:data:`READ_ONLY_KEYS`) plus what the role does, so the roles are easy to explain
and to compare: a Developer can do everything a Tester can, and so on. None of them holds an administrative key (users, roles, secrets values,
authentication, backups to restore, feature flags, the Admin menu): those stay with ``system-admin``. A system role says which *features* a person
may use; which *projects* they may use them in is still decided by project membership and the project roles (owner, editor, viewer).

If an installation already has a custom role with the same name as one of these, the custom role is kept as it is: a built-in role never replaces
one that someone made.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Tuple

from ccai.pychestrate.webservice.security.rbac.extensions.role_extension import (
    PermissionGrant,
    RoleExtension,
)
from ccai.pychestrate.webservice.security.rbac.models import PermissionEffect


#: What anyone who works in the product may read: no secrets, no people, no access control, no audit.
READ_ONLY_KEYS: Tuple[str, ...] = (
    "system:projects.read",
    "system:runs.read",
    "system:builds.read",
    "system:test_catalog.read",
    "system:pipelines.read",
    "system:pipeline_runs.read",
    "system:dashboards.read",
    "system:metrics.read",
    "system:metric_alerts.read",
    "system:slos.read",
    "system:environments.read",
    "system:drift.read",
    "system:provisioning.read",
    "system:guards.read",
    "system:pods.read",
    "system:clients.read",
    "system:resources.read",
    "system:resource_pools.read",
    "system:release_channels.read",
    "system:release_templates.read",
    "system:source_integrations.read",
    "system:rpa.read",
    "system:webhooks.read",
)

#: A Tester runs tests, reads what they found, and keeps the test catalog.
TESTER_KEYS: Tuple[str, ...] = READ_ONLY_KEYS + (
    "system:test_runs.create",
    "system:test_catalog.write",
    "system:runs.cancel",
)

#: A Developer does what a Tester does, and starts builds and pipelines, keeps pipelines, dashboards, alerts and SLOs for their services,
#: runs RPA jobs and keeps the secrets of the projects they belong to.
DEVELOPER_KEYS: Tuple[str, ...] = TESTER_KEYS + (
    "system:builds.create",
    "system:pipelines.run",
    "system:pipelines.write",
    "system:rpa.create",
    "system:dashboards.write",
    "system:metric_alerts.write",
    "system:slos.write",
    "system:project_secrets.read",
    "system:project_secrets.write",
)

#: A Release manager starts builds and pipelines and decides what is published, and to which channel.
RELEASE_MANAGER_KEYS: Tuple[str, ...] = READ_ONLY_KEYS + (
    "system:builds.create",
    "system:pipelines.run",
    "system:runs.cancel",
    "system:release_channels.write",
    "system:release_templates.write",
)

#: A Lab manager looks after the lab's devices: registering them, their pools, bookings and allocations.
LAB_MANAGER_KEYS: Tuple[str, ...] = READ_ONLY_KEYS + (
    "system:resources.write",
    "system:resources.manage",
    "system:resource_pools.write",
)

#: A Platform operator looks after the machinery the work runs on: environments and provisioning, drift and the guards that limit it, the pods and
#: clients, and the dashboards, alerts and webhooks that watch them. Restoring a backup stays with ``system-admin``.
PLATFORM_OPERATOR_KEYS: Tuple[str, ...] = READ_ONLY_KEYS + (
    "system:environments.write",
    "system:provisioning.create",
    "system:drift.check",
    "system:guards.write",
    "system:pods.write",
    "system:clients.write",
    "system:webhooks.write",
    "system:dashboards.write",
    "system:metric_alerts.write",
    "system:slos.write",
    "system:backups.read",
    "system:runs.cancel",
)


def _grants(keys: Tuple[str, ...]) -> Tuple[PermissionGrant, ...]:
    """Allow-grants for ``keys``, without repeats, in the order given."""
    return tuple(PermissionGrant(permission_key=key, effect=PermissionEffect.ALLOW) for key in dict.fromkeys(keys))


class ReadOnlyRole(RoleExtension):
    """
        See everything that is safe to see, change nothing.
    """

    resource_extension_name: str = "role_extension"
    role_name: str = "read-only"
    description: str = "See projects, runs, builds, tests, pipelines, dashboards, environments, pods and lab devices. Change nothing."
    permissions: tuple = _grants(READ_ONLY_KEYS)


class TesterRole(RoleExtension):
    """
        Run tests and keep the test catalog.
    """

    resource_extension_name: str = "role_extension"
    role_name: str = "tester"
    description: str = "Everything Read-only can see, and run tests, keep the test catalog and cancel runs."
    permissions: tuple = _grants(TESTER_KEYS)


class DeveloperRole(RoleExtension):
    """
        Test, build, and keep pipelines and the monitoring of one's own services.
    """

    resource_extension_name: str = "role_extension"
    role_name: str = "developer"
    description: str = "Everything a Tester can do, and start builds and pipelines, edit pipelines, dashboards, alerts and SLOs, run RPA jobs and keep project secrets."
    permissions: tuple = _grants(DEVELOPER_KEYS)


class ReleaseManagerRole(RoleExtension):
    """
        Decide what is published and where.
    """

    resource_extension_name: str = "role_extension"
    role_name: str = "release-manager"
    description: str = "Everything Read-only can see, and start builds and pipelines, cancel runs, and publish releases to channels and keep release templates."
    permissions: tuple = _grants(RELEASE_MANAGER_KEYS)


class LabManagerRole(RoleExtension):
    """
        Look after the lab's devices.
    """

    resource_extension_name: str = "role_extension"
    role_name: str = "lab-manager"
    description: str = "Everything Read-only can see, and register and change lab devices, manage pools, reservations and allocations (including checking a device in for someone)."
    permissions: tuple = _grants(LAB_MANAGER_KEYS)


class PlatformOperatorRole(RoleExtension):
    """
        Look after what the work runs on.
    """

    resource_extension_name: str = "role_extension"
    role_name: str = "platform-operator"
    description: str = "Everything Read-only can see, and manage environments, provisioning, drift checks and guards, pods and clients, and the dashboards, alerts and webhooks that watch them."
    permissions: tuple = _grants(PLATFORM_OPERATOR_KEYS)


WORKFLOW_ROLES = (ReadOnlyRole, TesterRole, DeveloperRole, ReleaseManagerRole, LabManagerRole, PlatformOperatorRole)


__all__ = [
    "DEVELOPER_KEYS",
    "DeveloperRole",
    "LAB_MANAGER_KEYS",
    "LabManagerRole",
    "PLATFORM_OPERATOR_KEYS",
    "PlatformOperatorRole",
    "READ_ONLY_KEYS",
    "RELEASE_MANAGER_KEYS",
    "ReadOnlyRole",
    "ReleaseManagerRole",
    "TESTER_KEYS",
    "TesterRole",
    "WORKFLOW_ROLES",
]
