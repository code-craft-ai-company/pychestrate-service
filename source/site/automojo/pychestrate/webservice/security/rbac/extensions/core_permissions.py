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
    # Org-scoped secret write access for the full-CRUD REST surface
    # (POST / PUT / DELETE /api/v1/secrets at ORG scope). Introduced
    # by 1-secrets-vault PR p20g. ``system:secrets.admin`` is a
    # superset and also satisfies every scoped check.
    "system:secrets.write": (
        "Create, rotate, and delete org-scoped secrets via the REST surface"
    ),
    # Project-scoped secret read access. A caller also needs
    # membership on the secret's project; this permission gates the
    # value-read of PROJECT-scoped secrets. Introduced by PR p20g.
    "system:project_secrets.read": (
        "Read project-scoped secret values for projects the caller belongs to"
    ),
    # Project-scoped secret write access (create / rotate / delete of
    # PROJECT-scoped secrets). Membership on the project is also
    # required. Introduced by PR p20g.
    "system:project_secrets.write": (
        "Create, rotate, and delete project-scoped secrets for member projects"
    ),
    "system:audit.read": "Read the audit record stream",
    "system:flags.admin": "Administer feature-flag lifecycle",
    "system:directory.sync": "Trigger a user_directory_source sync cycle",
    "system:auth.admin": "Administer authentication provider configuration",
    "system:auth.read": "Introspect active sessions and MFA enrollments",
    "system:resources.manage": (
        "Administer the resources surface "
        "(pools, IP pools, allocations, health probes)"
    ),
    # UX-gating permission introduced by 1-rbac Requirement 5.
    # Consumed by 9-site-shell to decide whether to render the
    # "Admin" sidebar group. It is NOT a security boundary --
    # individual admin actions remain protected by their own
    # per-action permissions enforced server-side by each owning
    # feature's route guards.
    "system:ui.admin.view": (
        "UX signal: render the admin sidebar group in the site shell"
    ),
    # Operator-facing read access for the run-state surface
    # (GET /api/v1/runs and GET /api/v1/runs/{id}). Required by
    # 5-run-state-machine PR p19c.
    "system:runs.read": (
        "Read runs and run-state listings via the REST surface"
    ),
    # Operator-facing read access for the test-catalog REST
    # surface (GET /api/v1/projects/{id}/test-catalog). Introduced
    # by 6-test-orchestration PR p19d.
    "system:test_catalog.read": (
        "Read test-catalog entries via the REST surface"
    ),
    # Operator/CI write access for catalog upserts and importer
    # runs. Introduced by 6-test-orchestration PR p19d.
    "system:test_catalog.write": (
        "Create, update, and import test-catalog entries via the REST surface"
    ),
    # Operator-facing trigger access for
    # POST /api/v1/projects/{id}/test-runs. Introduced by
    # 6-test-orchestration PR p19d.
    "system:test_runs.create": (
        "Trigger new test runs via the REST surface"
    ),
    # Operator-facing read access for the build-orchestration REST
    # surface (GET /api/v1/projects/{id}/builds and its artifacts).
    # Introduced by 6-build-orchestration PR p20a.
    "system:builds.read": (
        "Read build runs and build artifacts via the REST surface"
    ),
    # Operator/CI trigger access for
    # POST /api/v1/projects/{id}/builds. Introduced by
    # 6-build-orchestration PR p20a.
    "system:builds.create": (
        "Trigger new build runs via the REST surface"
    ),
    # Operator-facing read access for the pipeline-definition REST
    # surface (GET /api/v1/projects/{id}/pipelines, DAG validation,
    # and the matrix-expand preview). Introduced by
    # 6-pipeline-definition + 6-matrix-sharding PR p20k.
    "system:pipelines.read": (
        "Read pipeline definitions, validate DAGs, and preview"
        " matrix expansion via the REST surface"
    ),
    # Operator/CI write access for pipeline-definition upsert and
    # delete. Introduced by 6-pipeline-definition PR p20k.
    "system:pipelines.write": (
        "Create, update, and delete pipeline definitions via the REST surface"
    ),
    # Operator-facing read access for the source-integrations REST
    # surface (GET /api/v1/projects/{id}/source-integrations).
    # Introduced by 6-source-integrations PR p20a.
    "system:source_integrations.read": (
        "Read source-integration (SCM) configs via the REST surface"
    ),
    # Operator/CI write access for source-integration registration.
    # Introduced by 6-source-integrations PR p20a.
    "system:source_integrations.write": (
        "Register and update source-integration (SCM) configs via the REST surface"
    ),
    # Operator-facing read access for the environment-registry
    # REST surface (GET /api/v1/projects/{id}/environments).
    # Introduced by 6-environment-registry PR p20b.
    "system:environments.read": (
        "Read target environments via the REST surface"
    ),
    # Operator/CI write access for environment registration.
    # Introduced by 6-environment-registry PR p20b.
    "system:environments.write": (
        "Register and update target environments via the REST surface"
    ),
    # Operator-facing read access for the provisioning-runs REST
    # surface (GET /api/v1/projects/{id}/provisioning-runs).
    # Introduced by 6-infra-orchestration PR p20b.
    "system:provisioning.read": (
        "Read provisioning runs via the REST surface"
    ),
    # Operator/CI trigger access for
    # POST /api/v1/projects/{id}/provisioning-runs. Introduced by
    # 6-infra-orchestration PR p20b.
    "system:provisioning.create": (
        "Trigger new provisioning runs via the REST surface"
    ),
    # Operator-facing read access for the drift-detection REST
    # surface (GET .../environments/{id}/drift). Introduced by
    # 6-drift-detection PR p20b.
    "system:drift.read": (
        "Read drift status and drift reports via the REST surface"
    ),
    # Operator/CI trigger access for
    # POST .../environments/{id}/drift:check. Introduced by
    # 6-drift-detection PR p20b.
    "system:drift.check": (
        "Trigger drift checks via the REST surface"
    ),
    # Operator-facing read access for the project-management REST
    # surface (GET /api/v1/projects and GET .../projects/{id}).
    # Introduced by 2-projects PR p20e.
    "system:projects.read": (
        "Read projects and project listings via the REST surface"
    ),
    # Operator/CI write access for project creation, patching, and
    # lifecycle transitions. Introduced by 2-projects PR p20e.
    "system:projects.write": (
        "Create, update, and delete projects via the REST surface"
    ),
    # Operator-facing manage access for project member bindings
    # (add / list / remove). Introduced by 2-projects PR p20e.
    "system:projects.members.manage": (
        "Manage project member bindings via the REST surface"
    ),
    # 7-test-metrics / 7-metrics-ingest PR p20f: metric-query REST
    # surface (GET /api/v1/metrics/catalog, /metrics/timeseries,
    # and .../projects/{id}/test-metrics).
    "system:metrics.read": (
        "Read metric catalog, timeseries, and test-result rollups"
    ),
    # Reserved for the metric-write REST surface (metrics ingest
    # over HTTP). Introduced by 7-metrics-ingest PR p20f.
    "system:metrics.write": (
        "Write metric samples via the REST surface"
    ),
    # 7-project-dashboards PR p20f: project-dashboard REST surface
    # read access (GET .../projects/{id}/dashboards).
    "system:dashboards.read": (
        "Read project dashboards via the REST surface"
    ),
    # 7-project-dashboards PR p20f: project-dashboard REST surface
    # write access (POST .../projects/{id}/dashboards).
    "system:dashboards.write": (
        "Create and update project dashboards via the REST surface"
    ),
    # 7-alerts-budgets PR p20f: metric-alert REST surface read
    # access (GET .../projects/{id}/metric-alerts).
    "system:metric_alerts.read": (
        "Read metric-alert rules via the REST surface"
    ),
    # 7-alerts-budgets PR p20f: metric-alert REST surface write
    # access (POST .../projects/{id}/metric-alerts).
    "system:metric_alerts.write": (
        "Create and manage metric-alert rules via the REST surface"
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
