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
        PermissionGrant(
            permission_key="system:resources.manage",
            effect=PermissionEffect.ALLOW,
        ),
        # 1-rbac Requirement 5: the built-in admin role grants
        # ``system:ui.admin.view`` so the site shell renders the
        # Admin sidebar group for admin sessions and hides it for
        # everyone else.
        PermissionGrant(
            permission_key="system:ui.admin.view",
            effect=PermissionEffect.ALLOW,
        ),
        # 5-run-state-machine PR p19c: operator-facing read access
        # to the run REST surface.
        PermissionGrant(
            permission_key="system:runs.read",
            effect=PermissionEffect.ALLOW,
        ),
        # 6-test-orchestration PR p19d: test-catalog + test-runs
        # REST surface grants for the admin role.
        PermissionGrant(
            permission_key="system:test_catalog.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:test_catalog.write",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:test_runs.create",
            effect=PermissionEffect.ALLOW,
        ),
        # 6-build-orchestration + 6-source-integrations PR p20a:
        # build-runs, build-artifacts, and source-integrations REST
        # surface grants for the admin role.
        PermissionGrant(
            permission_key="system:builds.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:builds.create",
            effect=PermissionEffect.ALLOW,
        ),
        # 6-pipeline-definition + 6-matrix-sharding PR p20k:
        # pipeline-definition + matrix-sharding REST surface grants
        # for the admin role.
        PermissionGrant(
            permission_key="system:pipelines.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:pipelines.write",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:pipelines.run",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:pipeline_runs.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:source_integrations.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:source_integrations.write",
            effect=PermissionEffect.ALLOW,
        ),
        # 6-environment-registry + 6-infra-orchestration +
        # 6-drift-detection PR p20b: environments, provisioning
        # runs, and drift-detection REST surface grants for the
        # admin role.
        PermissionGrant(
            permission_key="system:environments.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:environments.write",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:provisioning.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:provisioning.create",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:drift.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:drift.check",
            effect=PermissionEffect.ALLOW,
        ),
        # 2-projects PR p20e: project-management REST surface grants
        # (project CRUD + member-binding management) for the admin
        # role.
        PermissionGrant(
            permission_key="system:projects.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:projects.write",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:projects.members.manage",
            effect=PermissionEffect.ALLOW,
        ),
        # 1-secrets-vault PR p20g: org/project/user-scoped secrets
        # full-CRUD REST surface grants for the admin role.
        # ``system:secrets.admin`` already authorizes every scope,
        # but the explicit write / project-secrets grants keep the
        # admin role's catalog complete.
        PermissionGrant(
            permission_key="system:secrets.write",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:project_secrets.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:project_secrets.write",
            effect=PermissionEffect.ALLOW,
        ),
        # 7-test-metrics / 7-project-dashboards / 7-alerts-budgets
        # PR p20f: metrics, dashboards, and metric-alert REST
        # surface grants for the admin role.
        PermissionGrant(
            permission_key="system:metrics.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:metrics.write",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:dashboards.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:dashboards.write",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:metric_alerts.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:metric_alerts.write",
            effect=PermissionEffect.ALLOW,
        ),
        # 4-resources PR p20p: granular resource-management REST keys.
        PermissionGrant(
            permission_key="system:resources.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:resources.write",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:resource_pools.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:resource_pools.write",
            effect=PermissionEffect.ALLOW,
        ),
        # 8-webhooks-in / 8-webhooks-out PR p21a: operator-facing
        # webhooks REST surface grants for the admin role.
        PermissionGrant(
            permission_key="system:webhooks.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:webhooks.write",
            effect=PermissionEffect.ALLOW,
        ),
        # 8-embeddable-views / 8-plugin-api PR p21b: embed catalog +
        # signed-URL issuance, and the plugin-api meta surface.
        PermissionGrant(
            permission_key="system:embed.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:embed.sign",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:plugin_api.read",
            effect=PermissionEffect.ALLOW,
        ),
        # 6-blast-radius-guards / 7-slo-views / 10-release-channels
        # PR p21c: REST-surface grants for the admin role.
        PermissionGrant(
            permission_key="system:guards.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:guards.write",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:slos.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:slos.write",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:release_channels.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:release_channels.write",
            effect=PermissionEffect.ALLOW,
        ),
        # Project-scoped release templates feature.
        PermissionGrant(
            permission_key="system:release_templates.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:release_templates.write",
            effect=PermissionEffect.ALLOW,
        ),
        # 10-backup-dr PR p21d: backup / disaster-recovery REST
        # surface grants for the admin role.
        PermissionGrant(
            permission_key="system:backups.read",
            effect=PermissionEffect.ALLOW,
        ),
        PermissionGrant(
            permission_key="system:backups.write",
            effect=PermissionEffect.ALLOW,
        ),
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
