# Pychestrate Implementation Plan

This document captures the feature catalog and phased implementation plan for the
Pychestrate web service — the central UI and orchestration hub for the Pychestrate
continuous integration and orchestration system.

Pychestrate replaces a Jenkins-style central server with a thin dispatcher + archive + UI.
Execution and result delivery both live on a pod's **client machine**; Pychestrate never
runs jobs itself and never reaches past a pod's client to its members.

---

## Architectural Ground Rules

These constraints are load-bearing; every feature below assumes them.

- **Pod client is the single point of contact.** Every Automation Pod designates one
  client machine. Pychestrate only talks to the client agent. Pod members are never
  contacted directly.
- **The client runs jobs and delivers results.** Build, infrastructure, and test jobs
  execute in a process tree owned by the client agent. Pychestrate does not spawn job
  processes.
- **Result delivery is push-only.** The client writes the full result tree to the
  shared results backend and/or POSTs progress summaries to Pychestrate's forwarding
  endpoint. Pychestrate's ingester is passive.
- **testbase is the result contract.** Pychestrate's ingest must accept the artifact
  set produced by `codecraftai-testbase`:
  `testrun_summary.json`, `testrun_results_stream.jsos`, `testrun_results.json`,
  `testsummary.html`, plus `artifacts/`, `taskings/`, `tc-by-products/`, `diagnostics/`
  subtrees. Live progress matches testbase's `ProgressConcentratorServer` and
  `ForwardingInfo` shapes.
- **All UI controls are WebComponents.** Framework-agnostic custom elements, themed
  via CSS custom properties, embeddable outside Pychestrate.
- **Every significant behavior has an extension point.** The Layer E extensibility
  model (below) — modeled on `codecraftai-extension` — governs how external packages add
  drivers, strategies, event subscribers, UI contributions, and new resource kinds
  without forking Pychestrate.

---

## Layer E — Extensibility (Cross-Cutting)

The extensibility layer is modeled directly on `codecraftai-extension`. It is listed as
a separate layer because every other layer's features consume it.

### Design Inheritance from `codecraftai-extension`

Two complementary mechanisms, kept deliberately distinct:

1. **Factory Protocol Extensions** — *override or provide a named behavior.*
   - A `FactoryProtocolBase` subclass declares `factory_protocol_name` and the
     classmethod signatures that implementations must satisfy.
   - Implementations inherit `FactoryExtension`, share the same `factory_protocol_name`,
     and set a numeric `PRECEDENCE` (lower = higher priority; last-match wins for
     `_by_order` calls).
   - Consumers look up by protocol method via a `SuperFactory`-style registry
     (`create_instance_by_order`, `create_instance_for_each`,
     `get_override_types_by_order`, `iterate_override_types_for_each`).
2. **Resource Extensions** — *add a new kind of thing to a registry.*
   - A `ResourceExtension` subclass is the collection base type.
   - `collect_resource_extensions_under_code_container` / `_under_folder` walks
     scanned namespaces and returns direct subclasses as `(name, type)` pairs.
   - Consumers iterate the collected list; no PRECEDENCE semantics, no override
     merging — it is a *set of kinds*, not a *chain of overrides*.

Pychestrate inherits the scan-on-sys.path discovery pattern: extensions live under
`ccai/factories/pychestrate/...` and `ccai/extensions/pychestrate/...`,
distributed as ordinary Python packages named `pychestrate-ext-<name>`.

Pychestrate **adds** versioning and lifecycle semantics that `codecraftai-extension`
leaves to the caller, because extensions run inside a long-lived, multi-tenant
service rather than a CLI process.

### Layer E Features

- **E-extension-host** — The `SuperFactory`-style core: scans the configured
  namespaces at service startup, loads factory and resource extensions into typed
  registries, sorts by `PRECEDENCE`, and re-scans on demand (admin action). One
  instance per service process; owned by Layer 0.
- **E-factory-protocols** — The Pychestrate-owned catalog of declared
  `FactoryProtocolBase` subclasses (see the "Extension Opportunities" section for
  every protocol name). Each protocol has a Sphinx-documented contract and a
  reference implementation shipped in-tree.
- **E-resource-extensions** — The Pychestrate-owned catalog of `ResourceExtension`
  base classes (resource kinds, pod member kinds, artifact renderers, dashboard
  tiles, CLI subcommands, etc.).
- **E-extension-manifest** — Optional `pychestrate_ext.yaml` per package declaring
  name, version, author, protocols implemented, resource kinds registered,
  declared dependencies, and `min_service_version` / `max_service_version`. The host
  refuses to load manifests that don't match the running service version.
- **E-extension-lifecycle** — Standardized hooks: `on_load`, `on_service_ready`,
  `on_project_loaded(project)`, `on_service_draining`, `on_unload`. Factories and
  resources declare which hooks they implement; the host invokes them in precedence
  order with a per-hook timeout.
- **E-extension-precedence** — Preserves upstream semantics (lower number =
  higher priority), plus a per-site override file that can re-pin PRECEDENCE for a
  specific extension without touching its source.
- **E-extension-config** — Per-extension config scope in `2-global-variables` and
  `1-secrets-vault` (keys prefixed `ext.<ext-name>.`). Extensions never read
  unscoped config directly.
- **E-extension-hooks** — Event-subscriber style: an extension class declares
  `@subscribes_to("entity.job.completed")`-style subscriptions; the host wires them
  to `0-message-bus` at load time. Distinct from factory protocols because it is
  reactive, not called-by-consumer.
- **E-extension-sandbox** — Capability manifest that gates what an extension may
  touch: `read:secrets`, `write:artifacts`, `dispatch:jobs`, `net:outbound`,
  `process:subprocess`. Enforced at registry-lookup time so an extension cannot
  call a protocol it has not been granted capability for. Lets operators install
  untrusted extensions with confidence.
- **E-extension-compat-check** — Manifest-driven version gate plus a protocol
  schema version carried on each `FactoryProtocolBase` so adding a new required
  method becomes a bump rather than a silent runtime AttributeError.
- **E-extension-registry-ui** — Admin page listing loaded extensions: name,
  version, protocols/resources, precedence, capabilities granted, health, last
  error, last call counts. Uses `9-admin-ui`.
- **E-extension-pack-template** — Canonical cookiecutter / starter repo for a new
  `pychestrate-ext-<name>` package: layout, manifest, tests, CI, examples of a
  factory protocol impl and a resource extension.
- **E-extension-docs** — Published docs site enumerating every declared factory
  protocol and resource extension base, with contracts and the shipped reference
  implementation. Generated from source; tied to `10-release-channels`.
- **E-plugin-api** — External-stable surface exposed from `8-plugin-api`: the
  *supported* subset of factory protocols and resource extensions, with
  deprecation windows. Internal-only protocols live behind Layer E but are not
  published here.

---

## Layered Feature Catalog

Features are named `{layer}-{feature-name}` so they can be referenced in issues, PRs,
and the phased plan below.

Each feature lists its **Ext:** surface when one exists. Format:

- `factory: <protocol-name> …` — named behaviors extensions may override/implement.
- `resource: <base-type> …` — discoverable kinds extensions may register.
- `event: <topic> …` — bus topics extensions may subscribe to via
  `E-extension-hooks`.

### Layer 0 — Platform Foundation

- **0-web-app-host** — WebWorks-based app bootstrap and WSGI server.
- **0-persistence** — Relational DB (Postgres), schema migrations, entity repository layer.
  - **Ext:** `resource: EntityMigrationExtension` — extensions ship their own
    migration packs under a namespaced schema prefix.
- **0-message-bus** — Internal async pub/sub for entity events.
  - **Ext:** `event: *` — every published topic is a subscription surface for
    `E-extension-hooks`; the bus is the backbone of reactive extensibility.
- **0-object-store** — Abstraction over the shared artifact/result backend.
  - **Ext:** `factory: object_store_driver` — SMB, NFS, S3, Azure Blob, GCS, custom.
- **0-timeseries-backend** — Metrics write/read layer.
  - **Ext:** `factory: timeseries_driver` — Prometheus, InfluxDB, Timescale, native.
- **0-system-health** — Internal liveness/readiness and dependency checks.
  - **Ext:** `resource: SystemHealthProbeExtension` — custom probes the health
    endpoint aggregates.
- **0-maintenance-mode** — Read-only / drain switch per system or project.

### Layer 1 — Identity, Access, Secrets

- **1-user-management** — Accounts, groups, profile.
  - **Ext:** `factory: user_directory_source` — LDAP, SCIM, custom HR-system sync.
- **1-authentication** — SSO (OIDC/SAML) plus local fallback, sessions.
  - **Ext:** `factory: auth_provider` (per protocol); `resource: MFAMethodExtension`.
- **1-rbac** — Role model, project-scoped permission matrix.
  - **Ext:** `resource: PermissionExtension` and `resource: RoleExtension` — new
    permission keys and role presets from extension packs.
- **1-secrets-vault** — Encrypted store, per-secret ACLs, rotation metadata.
  - **Ext:** `factory: secrets_backend` — local DB, HashiCorp Vault, AWS SM,
    Azure KV, GCP SM, custom.
- **1-audit-log** — Append-only record of config, secret, and dispatch actions.
  - **Ext:** `factory: audit_sink` (local, SIEM forwarder, Splunk HEC);
    `resource: AuditEventTypeExtension`.
- **1-feature-flags** — Runtime toggles for staged rollout.
  - **Ext:** `factory: feature_flag_backend` — local, LaunchDarkly-style, custom.

### Layer 2 — Core Entity Model

- **2-projects** — Top-level workspace grouping everything below.
  - **Ext:** `event: entity.project.created|archived|deleted`;
    `resource: ProjectMetadataFieldExtension`.
- **2-global-variables** — Hierarchical typed config with inheritance tracing.
  - **Ext:** `factory: variable_resolver` — pull values from external config
    services; `factory: secret_ref_dereferencer`.
- **2-tagging** — Shared tag model for resources, jobs, pods, artifacts.
  - **Ext:** `resource: TagTaxonomyExtension` — declared taxonomies and
    validators.
- **2-retention-policies** — Lifecycle rules per data class.
  - **Ext:** `factory: retention_action` — archive, cold-tier, delete, custom.
- **2-notification-hub** — Routing to email/Slack/webhook/PagerDuty.
  - **Ext:** `factory: notification_channel` (per channel type);
    `resource: NotificationTemplateExtension`.
- **2-project-templates** — Scaffolded "new project" presets.
  - **Ext:** `resource: ProjectTemplateExtension`.

### Layer 3 — Client & Pod Plane

- **3-client-agent-protocol** — Wire contract for enroll/heartbeat/dispatch/progress/result.
  - **Ext:** `factory: client_transport` — HTTP/2, WebSocket, gRPC, mTLS tunnel.
- **3-client-enrollment** — Bootstrap token → mTLS identity; revocation.
  - **Ext:** `factory: enrollment_token_issuer`; `factory: client_identity_verifier`.
- **3-client-registry** — Registered clients, versions, capabilities, last-seen.
  - **Ext:** `resource: ClientAttributeExtension` — declared capability kinds.
- **3-pod-definitions** — Declarative pod spec.
  - **Ext:** `resource: PodMemberKindExtension`; `factory: pod_spec_validator`.
- **3-static-pods** — Pre-wired pods registered by a client.
  - **Ext:** `event: entity.pod.registered|deregistered`.
- **3-dynamic-pods** — Template → materialized pod; client brought up as final step.
  - **Ext:** `factory: pod_provisioner` (per provisioning backend);
    `resource: PodTemplateExtension`.
- **3-pod-lifecycle** — State machine with hooks.
  - **Ext:** `event: entity.pod.state_changed`.
- **3-pod-topology-view** — Graph of pod members and links.
  - **Ext:** `resource: PodMemberRendererExtension` — WebComponent contributions
    for custom member kinds.
- **3-pod-scoped-config** — Variables/secrets scoped to a pod run.
  - Reuses `2-global-variables` and `1-secrets-vault` extension surfaces.
- **3-client-capability-advertisement** — Reported toolchains, members, concurrency caps.
  - **Ext:** `resource: CapabilityKindExtension`.
- **3-agent-upgrade-channel** — Staged agent rollout, per-pod pinning.
  - **Ext:** `factory: upgrade_artifact_source`; `factory: rollout_policy`.
- **3-client-inventory-ui** — Fleet view.

### Layer 4 — Resource Management

- **4-resource-inventory** — Externally-owned devices, IPs, subnets, licenses.
  - **Ext:** `resource: ResourceKindExtension` — the primary extension surface in
    this layer. Each kind declares typed attrs, validators, and default probes.
- **4-resource-pools** — Capability-tagged pools.
  - **Ext:** `factory: pool_allocation_strategy`.
- **4-checkout-checkin** — Reserve/release API.
  - **Ext:** `resource: CheckoutValidatorExtension`;
    `event: entity.reservation.created|released|forced_released`.
- **4-reservation-scheduler** — Queue + priority + fair-share + deadline hints.
  - **Ext:** `factory: reservation_scheduler` — FIFO, fair-share, priority,
    deadline, custom.
- **4-conflict-deconfliction** — Exclusive/shared modes, overlap rules.
  - **Ext:** `resource: ConflictRuleExtension`.
- **4-lease-heartbeat** — Leased reservations with renewal.
  - **Ext:** `factory: lease_renewal_policy`.
- **4-resource-health** — Pluggable probes, quarantine, last-good.
  - **Ext:** `factory: resource_health_probe` (keyed by resource kind) — the
    canonical per-kind extension pattern.
- **4-usage-history** — Per-resource timeline for capacity/flake analysis.
  - **Ext:** `resource: UsageAnalyticsHookExtension`.

### Layer 5 — Job Execution Plane

- **5-job-envelope** — Signed dispatch payload.
  - **Ext:** `resource: EnvelopeFieldExtension` — extensions add signed claims
    (e.g., infra-scope token) to envelopes their jobs require.
- **5-job-dispatch** — Scheduler → pod client via capability match.
  - **Ext:** `factory: dispatch_strategy`.
- **5-dispatch-receipt** — Client-issued local run id used for reconciliation.
- **5-run-state-machine** — Authoritative run states and transitions.
  - **Ext:** `event: entity.run.state_changed|cancelled|completed|failed`.
- **5-progress-ingest** — HTTP receiver for testbase `ForwardingInfo` summary POSTs.
  - **Ext:** `factory: progress_parser` (keyed by format tag) — testbase default,
    custom runner formats, gtest-json, JUnit-live, etc.
- **5-result-ingest-watcher** — Watches shared results root and parses the tree.
  - **Ext:** `factory: result_tree_parser` (keyed by format tag);
    `resource: ArtifactClassifierExtension` — classify files into artifact
    categories by path / magic bytes / mime.
- **5-shared-results-backend** — Per-run path allocation on the object store.
  - Reuses `0-object-store` drivers.
- **5-artifact-store** — Content-addressed retention with promotion paths.
  - **Ext:** `factory: promotion_strategy`; `resource: ArtifactTypeExtension` —
    typed artifact schemas (e.g., SBOM, container-image, firmware-image).
- **5-cancel-reconcile** — RPC-cancel + reconciliation against client truth.
- **5-offline-tolerance** — Degraded-pod state with buffered replay.

### Layer 6 — Orchestration Domains

- **6-pipeline-definition** — Pipeline-as-code (stages, parallel, matrix).
  - **Ext:** `resource: PipelineStepKindExtension` — new reusable step types
    packaged outside Pychestrate.
- **6-source-integrations** — SCM webhooks + polling + commit-status posting.
  - **Ext:** `factory: scm_provider` (GitHub, GitLab, Bitbucket, Gitea, custom);
    `resource: WebhookPayloadParserExtension`.
- **6-build-orchestration** — Build jobs, runs, reproducibility metadata.
  - **Ext:** `factory: build_runner_kind`; `factory: build_cache_backend`.
- **6-build-artifacts** — Typed outputs with promotion.
  - Reuses `5-artifact-store` extension surfaces.
- **6-infra-orchestration** — Terraform/Pulumi/Ansible job types.
  - **Ext:** `factory: infra_tool_driver`.
- **6-environment-registry** — Declared environments and current versions.
  - **Ext:** `resource: EnvironmentKindExtension`.
- **6-drift-detection** — Scheduled declared-vs-actual checks.
  - **Ext:** `factory: drift_checker` (per infra tool).
- **6-blast-radius-guards** — Role + env gating for destructive infra jobs.
  - **Ext:** `resource: GuardRuleExtension`.
- **6-test-orchestration** — Test jobs, runs, triggers.
  - **Ext:** `factory: test_runner_kind`.
- **6-test-catalog** — Registered suites with owner/tags/capabilities/runtime hints.
  - **Ext:** `factory: test_catalog_importer` (per source system — gtest
    discovery, pytest collect, custom registry).
- **6-matrix-sharding** — Fan-out and reassembly.
  - **Ext:** `factory: sharding_strategy`.
- **6-live-run-view** — Streamed progress surfaced from `5-progress-ingest`.
- **6-artifact-browser** — In-UI walk of `artifacts/<label>/` with previews.
  - **Ext:** `resource: ArtifactRendererExtension` — per-mime WebComponent
    renderers (image, audio, log, packet capture, flamegraph, custom).
- **6-flake-tracking** — Per-test stability, quarantine, retry policy.
  - **Ext:** `factory: flake_classifier`.
- **6-triage-bug-linking** — Known-issue / new-bug / infra-flake classification.
  - **Ext:** `factory: bug_tracker_driver` (Jira, Linear, GitHub Issues, custom).
- **6-compare-runs** — Side-by-side result/log/artifact diff.
  - **Ext:** `resource: ArtifactDiffViewerExtension`.

### Layer 7 — Metrics & Analytics

- **7-metrics-ingest** — Emission from every domain event.
  - **Ext:** `factory: metric_exporter` — push to external systems;
    `resource: MetricDefinitionExtension` — declare new counters/gauges/histograms.
- **7-build-metrics** / **7-test-metrics** / **7-orchestration-metrics** /
  **7-resource-metrics** / **7-pod-metrics** — domain rollups.
  - **Ext:** all share `resource: MetricDefinitionExtension`.
- **7-project-dashboards** — Composable tile layouts.
  - **Ext:** `resource: DashboardTileKindExtension` — WebComponent tile
    contributions.
- **7-alerts-budgets** — Threshold routing to `2-notification-hub`.
  - **Ext:** `resource: AlertRuleKindExtension`; channels reuse
    `2-notification-hub` factories.
- **7-slo-views** — Declared SLOs with burn-rate displays.
  - **Ext:** `resource: SLODefinitionExtension`.

### Layer 8 — Public Interfaces

- **8-rest-api-v1** — Versioned external API mirroring all capabilities.
  - **Ext:** `resource: RestEndpointExtension` — extensions contribute endpoints
    under `/api/v1/ext/<ext-name>/…`. Scoped so extension APIs never collide with
    core routes.
- **8-webhooks-in** — Inbound trigger endpoints.
  - **Ext:** `factory: inbound_webhook_parser` (per provider).
- **8-webhooks-out** — Outbound state-change notifications.
  - Reuses `2-notification-hub` drivers.
- **8-cli** — First-class CLI over `8-rest-api-v1`.
  - **Ext:** `resource: CLISubcommandExtension`.
- **8-embeddable-views** — Signed-URL embedding for external portals.
- **8-plugin-api** — External-stable surface; see `E-plugin-api`.

### Layer 9 — WebComponents UI

- **9-ui-design-tokens** — Shared CSS custom-property theme.
  - **Ext:** `resource: DesignTokenPackExtension` — white-label / per-tenant
    token overrides.
- **9-wc-log-stream** / **9-wc-result-viewer** / **9-wc-pipeline-dag** /
  **9-wc-pod-topology** / **9-wc-resource-picker** / **9-wc-secret-editor** /
  **9-wc-metric-tile** — framework-agnostic custom elements.
  - **Ext:** `resource: WebComponentBundleExtension` — extensions ship their own
    elements bundled with the extension pack; the host serves them under a
    namespaced static path.
- **9-admin-ui** — Users/roles/secrets/feature-flags/system health/extensions.
  - Hosts the `E-extension-registry-ui`.
- **9-project-dashboard-ui** — Per-project composed dashboard.
  - Composes tiles from `7-project-dashboards` extension surface.
- **9-run-detail-ui** — Run page composing log stream + result viewer + artifact browser.
  - Composes renderers from `6-artifact-browser` extension surface.

### Layer 10 — Operations

- **10-backup-dr** — DB + object store + secrets backup.
  - **Ext:** `factory: backup_storage_backend`.
- **10-release-channels** — Service + agent release trains.
  - **Ext:** `factory: release_channel_policy`.
- **10-observability** — Tracing, structured logs, exported metrics.
  - **Ext:** `factory: trace_exporter` — OTLP, Jaeger, Honeycomb, custom.

---

## Phased Implementation Plan

Phases deliver end-to-end thin slices rather than pure bottom-up. Layer E lands
early; subsequent phases ship the *extension points* for their features as a
matter of course.

### Phase 0 — Platform Readiness *(foundational, no user feature)*

Land `0-web-app-host` (already done), `0-persistence`, `0-message-bus`,
`0-object-store`, `0-system-health`, `10-observability`. Stand up CI for the
service itself.

**Exit criterion:** a no-op entity survives a restart, events are observable on
the bus, an object can be written to and read from the shared store.

### Phase 0.5 — Extension Host

Land the extensibility layer before any feature that will register extension
points: `E-extension-host`, `E-factory-protocols` (the catalog wiring — individual
protocols are populated as their owning feature ships), `E-resource-extensions`,
`E-extension-manifest`, `E-extension-lifecycle`, `E-extension-precedence`,
`E-extension-compat-check`. Defer `E-extension-sandbox` until there are
capabilities worth gating; defer `E-extension-registry-ui` until `9-admin-ui`.

**Exit criterion:** a sample out-of-tree `pychestrate-ext-example` package
containing one factory protocol impl and one resource extension loads on startup,
appears in a diagnostic listing, and survives a re-scan. `0-object-store`
acquires its SMB/S3 drivers through the host (proves the registry on a live
dependency).

### Phase 1 — Identity & Projects

Build `1-user-management`, `1-authentication`, `1-rbac`, `1-audit-log`,
`2-projects`, `2-global-variables`, `2-tagging`, `2-notification-hub`. Add
`10-backup-dr` baseline. Register each layer's factory protocols
(`auth_provider`, `secrets_backend`, `notification_channel`, `variable_resolver`,
…) through `E-factory-protocols`. Land `E-extension-config` so extensions get
their scoped config/secrets surface.

**Exit criterion:** an admin can create a project, assign members, set variables,
and every action appears in the audit log. An out-of-tree extension can register
a new `notification_channel` and receive traffic.

### Phase 2 — Client & Pod Plane

Implement `3-client-agent-protocol`, `3-client-enrollment`, `3-client-registry`,
`3-pod-definitions`, `3-static-pods`, `3-pod-lifecycle`,
`3-client-capability-advertisement`, `3-client-inventory-ui` (minimal). Register
`PodMemberKindExtension` and `CapabilityKindExtension` — first-class extension
surfaces since pod member types are the most commonly customized thing.

**Exit criterion:** a real machine enrolls as a client, registers a static pod
with a custom member kind contributed by an extension, and shows `ready` in
the UI.

### Phase 3 — Minimal Test Run End-to-End

First user-visible slice. Implement Layer 5 (`5-job-envelope` through
`5-cancel-reconcile`), `6-test-orchestration`, `6-test-catalog`, `6-live-run-view`.
Register `progress_parser`, `result_tree_parser`, and `artifact_classifier`
extension points — even though only the testbase defaults ship in Phase 3, the
points exist from day one.

**Exit criterion:** a manually triggered testbase run on a registered pod
produces a visible run row, streams progress, and surfaces the full result tree.

### Phase 4 — Resources & Scheduling Fairness

Add Layer 4 end-to-end. Ship `ResourceKindExtension` and
`resource_health_probe` as the flagship per-kind extension surfaces — an
extension pack for a new device type should be writable end-to-end after this
phase.

**Exit criterion:** two test jobs contending for one device queue correctly;
an out-of-tree extension registers a new resource kind with custom health probes
and the scheduler honors it.

### Phase 5 — Test Orchestration Polish + First WebComponents

Add `6-matrix-sharding`, `6-artifact-browser`, `6-flake-tracking`,
`6-triage-bug-linking`, `6-compare-runs`, `5-offline-tolerance`. Begin UI:
`9-ui-design-tokens`, `9-wc-log-stream`, `9-wc-result-viewer`, `9-run-detail-ui`.
Register `ArtifactRendererExtension` and `WebComponentBundleExtension` — the UI
extension surface lands with the first WebComponents.

**Exit criterion:** test ops team adopts Pychestrate as daily driver. An
extension ships a custom artifact renderer (e.g., packet-capture viewer) and it
appears in the run detail UI.

### Phase 6 — Build Orchestration

Implement `6-pipeline-definition`, `6-source-integrations`,
`6-build-orchestration`, `6-build-artifacts`, `9-wc-pipeline-dag`. Register
`scm_provider`, `build_runner_kind`, `PipelineStepKindExtension`.

**Exit criterion:** a PR opens → Pychestrate dispatches a build → result posts
back to SCM; a custom SCM provider (e.g., internal Gitea-plus-ldap) can be
added by extension.

### Phase 7 — Infrastructure Orchestration

Implement `6-infra-orchestration`, `6-environment-registry`, `6-drift-detection`,
`6-blast-radius-guards`. Register `infra_tool_driver`, `drift_checker`,
`EnvironmentKindExtension`, `GuardRuleExtension`.

**Exit criterion:** standing envs can be provisioned/torn-down/drift-checked from
Pychestrate with role gating; an extension contributes a new infra tool.

### Phase 8 — Dynamic Pods & Sandbox

Add `3-dynamic-pods`, `3-pod-scoped-config`, `3-pod-topology-view`,
`9-wc-pod-topology`, `9-wc-resource-picker`. Now that extensions have
substantial capability (drivers, provisioners, SCM, bug trackers), land
`E-extension-sandbox` — the capability manifest — before any third-party
extensions are onboarded beyond the team.

**Exit criterion:** a test job requests a pod-by-template, Pychestrate
materializes it, runs, tears down, releases resources; an extension lacking
`dispatch:jobs` capability cannot call the dispatch protocol.

### Phase 9 — Metrics, Dashboards, Alerts

Stand up `0-timeseries-backend` fully. Implement `7-metrics-ingest` plus domain
metrics. UI: `9-wc-metric-tile`, `7-project-dashboards`,
`9-project-dashboard-ui`. Close with `7-alerts-budgets`, `7-slo-views`. Register
`MetricDefinitionExtension`, `DashboardTileKindExtension`,
`AlertRuleKindExtension`, `SLODefinitionExtension`, `metric_exporter`.

**Exit criterion:** every project has a dashboard; on-call has meaningful
alerts; an extension contributes a domain-specific tile.

### Phase 10 — Public Surface & Extensibility Completion

Harden `8-rest-api-v1`, add `8-webhooks-in`, `8-webhooks-out`, `8-cli`,
`8-embeddable-views`. Land `8-plugin-api` / `E-plugin-api` — the
*externally-stable* subset of Layer E protocols with deprecation windows.
Ship `E-extension-pack-template`, `E-extension-docs`, `E-extension-registry-ui`.
Add `3-agent-upgrade-channel`, `10-release-channels`. Add remaining admin
surface (`9-admin-ui`, `9-wc-secret-editor`, `1-feature-flags`,
`0-maintenance-mode`, `2-retention-policies`, `2-project-templates`).

**Exit criterion:** external teams can ship a `pychestrate-ext-<name>` package
against a documented, versioned plugin API without touching the service repo.

---

## Dependency Notes

- Layer E is foundational — `E-extension-host` must land in Phase 0.5 because
  later layers acquire their drivers (SMB/S3, auth providers, notification
  channels, resource health probes, etc.) *through* the registry rather than
  around it.
- Layer 3 depends only on Layer 1–2 and `0-message-bus` — it can start as soon
  as Phase 1 lands.
- Layer 5 depends on Layer 3 and Layer 0's object store; it is built *before*
  Layer 4 so the first test run is possible without a full resource broker.
- Layer 6 build/infra reuse Layer 5 entirely — no new dispatch plumbing.
- Layer 7 is additive; it can start the moment Layer 5 emits run events.
- Layer 9 WebComponents are introduced incrementally per phase — each component
  lands with the domain that needs it; `WebComponentBundleExtension` registers
  in Phase 5 alongside the first UI.
- `E-extension-sandbox` intentionally lags the initial Layer E landing (Phase
  0.5 → Phase 8): there is nothing meaningful to sandbox until the protocol
  catalog is wide enough that capability gating has teeth. Running without it in
  early phases is acceptable because only in-tree extensions exist.
- `E-plugin-api` is the last thing to harden (Phase 10): publishing a stable
  surface before the internal protocol catalog has stabilized produces
  compatibility debt that is expensive to unwind.
