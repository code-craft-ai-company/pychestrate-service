"""
.. module:: security.rbac.extensions.core_permissions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-tree permission pack shipping the core ``system:*`` keys.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.security.rbac.extensions.permission_extension import (
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
        "Create, rotate, and delete org-scoped secrets"
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
        "Read runs and run-state listings"
    ),
    # Cancel any in-flight run (POST /api/v1/runs/{id}/cancel), in any
    # project -- what the global "Cancel run" control needs. Project
    # members cancel through the project-scoped ``project:runs.cancel``.
    "system:runs.cancel": (
        "Cancel any in-flight run"
    ),
    # Operator-facing read access for the test-catalog REST
    # surface (GET /api/v1/projects/{id}/test-catalog). Introduced
    # by 6-test-orchestration PR p19d.
    "system:test_catalog.read": (
        "Read test-catalog entries"
    ),
    # Operator/CI write access for catalog upserts and importer
    # runs. Introduced by 6-test-orchestration PR p19d.
    "system:test_catalog.write": (
        "Create, update, and import test-catalog entries"
    ),
    # Operator-facing trigger access for
    # POST /api/v1/projects/{id}/test-runs. Introduced by
    # 6-test-orchestration PR p19d.
    "system:test_runs.create": (
        "Trigger new test runs"
    ),
    # Operator-facing read access for the build-orchestration REST
    # surface (GET /api/v1/projects/{id}/builds and its artifacts).
    # Introduced by 6-build-orchestration PR p20a.
    "system:builds.read": (
        "Read build runs and build artifacts"
    ),
    # Operator/CI trigger access for
    # POST /api/v1/projects/{id}/builds. Introduced by
    # 6-build-orchestration PR p20a.
    "system:builds.create": (
        "Trigger new build runs"
    ),
    # 6-rpa-orchestration (Phase 11): read access to RPA job types,
    # specifications, and jobs via the REST surface.
    "system:rpa.read": (
        "Read RPA job types, specifications, and jobs"
    ),
    # Trigger / cancel RPA jobs and manage project specifications.
    "system:rpa.create": (
        "Trigger RPA jobs and manage RPA specifications"
    ),
    # Register job types and publish / retire versions (deployment-wide).
    "system:rpa.job_types.manage": (
        "Register RPA job types and publish or retire their versions"
    ),
    # 9-ui-profiles (Phase 11): choose which automation surfaces the
    # deployment presents by default.
    "system:ui.profile.manage": (
        "Set the deployment-wide UI profile (visible automation surfaces)"
    ),
    # Operator-facing read access for the pipeline-definition REST
    # surface (GET /api/v1/projects/{id}/pipelines, DAG validation,
    # and the matrix-expand preview). Introduced by
    # 6-pipeline-definition + 6-matrix-sharding PR p20k.
    "system:pipelines.read": (
        "Read pipeline definitions, validate DAGs, and preview"
        " matrix expansion"
    ),
    # Operator/CI write access for pipeline-definition upsert and
    # delete. Introduced by 6-pipeline-definition PR p20k.
    "system:pipelines.write": (
        "Create, update, and delete pipeline definitions"
    ),
    # Operator/CI access to trigger a pipeline run -- the DAG-walking
    # orchestrator that dispatches each stage's build / test /
    # provision job. Introduced by 6-pipeline-execution PR p20q.
    "system:pipelines.run": (
        "Trigger pipeline runs (DAG-walking stage-job dispatch)"
    ),
    # Operator-facing read access for pipeline runs and their
    # per-stage status. Introduced by 6-pipeline-execution PR p20q.
    "system:pipeline_runs.read": (
        "Read pipeline runs and per-stage status"
    ),
    # Operator-facing read access for the source-integrations REST
    # surface (GET /api/v1/projects/{id}/source-integrations).
    # Introduced by 6-source-integrations PR p20a.
    "system:source_integrations.read": (
        "Read source-integration (SCM) configs"
    ),
    # Operator/CI write access for source-integration registration.
    # Introduced by 6-source-integrations PR p20a.
    "system:source_integrations.write": (
        "Register and update source-integration (SCM) configs"
    ),
    # Operator-facing read access for the environment-registry
    # REST surface (GET /api/v1/projects/{id}/environments).
    # Introduced by 6-environment-registry PR p20b.
    "system:environments.read": (
        "Read target environments"
    ),
    # Operator/CI write access for environment registration.
    # Introduced by 6-environment-registry PR p20b.
    "system:environments.write": (
        "Register and update target environments"
    ),
    # Operator-facing read access for the provisioning-runs REST
    # surface (GET /api/v1/projects/{id}/provisioning-runs).
    # Introduced by 6-infra-orchestration PR p20b.
    "system:provisioning.read": (
        "Read provisioning runs"
    ),
    # Operator/CI trigger access for
    # POST /api/v1/projects/{id}/provisioning-runs. Introduced by
    # 6-infra-orchestration PR p20b.
    "system:provisioning.create": (
        "Trigger new provisioning runs"
    ),
    # Operator-facing read access for the drift-detection REST
    # surface (GET .../environments/{id}/drift). Introduced by
    # 6-drift-detection PR p20b.
    "system:drift.read": (
        "Read drift status and drift reports"
    ),
    # Operator/CI trigger access for
    # POST .../environments/{id}/drift:check. Introduced by
    # 6-drift-detection PR p20b.
    "system:drift.check": (
        "Trigger drift checks"
    ),
    # Operator-facing read access for the project-management REST
    # surface (GET /api/v1/projects and GET .../projects/{id}).
    # Introduced by 2-projects PR p20e.
    "system:projects.read": (
        "Read projects and project listings"
    ),
    # Operator/CI write access for project creation, patching, and
    # lifecycle transitions. Introduced by 2-projects PR p20e.
    "system:projects.write": (
        "Create, update, and delete projects"
    ),
    # Operator-facing manage access for project member bindings
    # (add / list / remove). Introduced by 2-projects PR p20e.
    "system:projects.members.manage": (
        "Manage project member bindings"
    ),
    # Shows the Projects area in the site shell. Derived for every
    # user who can use at least one project -- as a project member or
    # through a global project role -- rather than bound through a
    # role (webinterface.blueprints.projects.project_access; PRJ-17).
    "system:projects.access": (
        "Use the Projects area (derived from project membership and project roles)"
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
        "Write metric samples"
    ),
    # 7-project-dashboards PR p20f: project-dashboard REST surface
    # read access (GET .../projects/{id}/dashboards).
    "system:dashboards.read": (
        "Read project dashboards"
    ),
    # 7-project-dashboards PR p20f: project-dashboard REST surface
    # write access (POST .../projects/{id}/dashboards).
    "system:dashboards.write": (
        "Create and update project dashboards"
    ),
    # 7-alerts-budgets PR p20f: metric-alert REST surface read
    # access (GET .../projects/{id}/metric-alerts).
    "system:metric_alerts.read": (
        "Read metric-alert rules"
    ),
    # 7-alerts-budgets PR p20f: metric-alert REST surface write
    # access (POST .../projects/{id}/metric-alerts).
    "system:metric_alerts.write": (
        "Create and manage metric-alert rules"
    ),
    # 4-resources PR p20p: resource-management REST surface. The
    # broad ``system:resources.manage`` admin grant predates this
    # split -- these read/write keys gate the granular REST routes.
    "system:resources.read": (
        "Read resources, resource health, and usage history"
    ),
    "system:resources.write": (
        "Register and mutate resources"
    ),
    "system:resource_pools.read": (
        "Read resource pools, pool members, and reservations"
    ),
    "system:resource_pools.write": (
        "Create resource pools and manage pool members and "
        "reservations"
    ),
    # Fleet pods + clients surface: read/write keys gating the
    # pods controller (/api/v1/projects/{id}/pod-definitions,
    # /pods/..., /pod-templates, run-scoped variables) and the
    # clients-admin controller (/api/v1/clients). Also consumed by
    # the ``fleet.pods`` / ``fleet.clients`` sidebar entries in
    # :mod:`webinterface.site_shell.nav_manifest`. The
    # unauthenticated client enrollment/redeem flow authenticates
    # via enrollment tokens, not these keys.
    "system:pods.read": (
        "Read pod definitions, pod state, registrations, topology, "
        "and pod templates"
    ),
    "system:pods.write": (
        "Create pod definitions and templates, materialize "
        "templates, and mutate run-scoped pod variables"
    ),
    "system:clients.read": (
        "Read enrolled clients and client detail"
    ),
    "system:clients.write": (
        "Revoke clients and update client attributes"
    ),
    # 8-webhooks-in / 8-webhooks-out PR p21a: operator-facing
    # webhooks REST surface (inbound integration configs +
    # deliveries, outbound subscriptions + delivery history).
    # The unauthenticated inbound receiver authenticates via
    # the domain's signature verification, not these keys.
    "system:webhooks.read": (
        "Read inbound webhook integrations, inbound deliveries, "
        "outbound subscriptions, and delivery history"
    ),
    "system:webhooks.write": (
        "Register and manage inbound webhook integrations and "
        "outbound subscriptions"
    ),
    # Notification channels and routing rules (audit ORG-F08). Administrative:
    # a channel makes the server send mail and HTTP requests with stored
    # credentials, so these are held by system-admin only.
    "system:notifications.read": (
        "See the notification channels, the rules that send through them, "
        "and recent deliveries"
    ),
    "system:notifications.write": (
        "Add, change and delete notification channels and routing rules, "
        "and send test messages"
    ),
    # Operator-facing read access for the embeddable-views catalog
    # (GET /api/v1/embed/views). Introduced by 8-embeddable-views
    # PR p21b. The /embed/{view_key} serving route itself is
    # token-authed (signed URL), not RBAC-gated.
    "system:embed.read": (
        "Read the embeddable-views catalog"
    ),
    # Operator-facing access to mint signed embed URLs
    # (POST /api/v1/embed/views/{view_key}:sign). Introduced by
    # 8-embeddable-views PR p21b.
    "system:embed.sign": (
        "Mint signed embed URLs"
    ),
    # Operator-facing read access for the plugin-api meta surface
    # (GET /api/v1/plugin-api/_meta/* and GET /api/v1/ext).
    # Introduced by 8-plugin-api PR p21b.
    "system:plugin_api.read": (
        "Read the plugin-api published-surface catalog and mounted"
        " extension endpoints"
    ),
    # 6-blast-radius-guards PR p21c: blast-radius-guard REST
    # surface. Guards bind registry rules onto an environment to
    # cap provisioning blast radius.
    "system:guards.read": (
        "Read blast-radius guards and evaluate guard previews"
    ),
    "system:guards.write": (
        "Attach, toggle, and disable blast-radius guards"
    ),
    # 7-slo-views PR p21c: SLO-view REST surface read/write access.
    "system:slos.read": (
        "Read SLO definitions and current burn-rate status"
    ),
    "system:slos.write": (
        "Create and delete SLO definitions"
    ),
    # 10-release-channels PR p21c: release-channel REST surface
    # read/write access.
    "system:release_channels.read": (
        "Read published release-channel entries"
    ),
    "system:release_channels.write": (
        "Publish releases onto a channel"
    ),
    # Project-scoped release-templates feature: read/write
    # permissions guarding the REST and webworks UI surfaces for
    # release-template CRUD.
    "system:release_templates.read": (
        "Read project-scoped release templates"
    ),
    "system:release_templates.write": (
        "Create, update, and delete project-scoped release templates"
        ""
    ),
    # 10-backup-dr PR p21d: backup / disaster-recovery REST
    # surface. Backups snapshot the DB, object-store references,
    # and secrets metadata into a pluggable storage backend.
    "system:backups.read": (
        "Read backup records, status, and manifests"
    ),
    "system:backups.write": (
        "Trigger backups and request restores"
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
