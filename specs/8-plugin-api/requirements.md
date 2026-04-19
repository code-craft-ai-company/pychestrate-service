# 8-plugin-api — Requirements

## Introduction

`8-plugin-api` is the *externally-stable* subset of Pychestrate's
Layer E extensibility surface. Internally, dozens of factory
protocols and resource extensions exist (see `E-factory-protocols`
and `E-resource-extensions`); most are free to change shape as the
service evolves. `8-plugin-api` publishes the narrow, frozen subset
that external `pychestrate-ext-<name>` packages are *supported*
against — with compatibility guarantees, deprecation windows, and
a signed semantic version per protocol. It is the public contract
that `E-plugin-api` points at. This feature ships in **Phase 10 —
Public Surface & Extensibility Completion**; publishing anything
earlier would produce compatibility debt before the internal
protocol catalog has stabilized.

## Requirements

### Requirement 1: Published Protocol + Resource Catalog

**User Story:** As an external extension author, I want a published
list of supported factory protocols and resource extension bases,
so that I know what I can safely build against.

**Acceptance Criteria (EARS):**

1. WHEN the service starts THEN it SHALL expose
   `GET /api/v1/plugin-api/_meta/catalog` returning a JSON
   document enumerating every published factory protocol and
   resource extension base, each with `name`, `version`,
   `protocol_schema_version`, `status`
   (`supported | deprecated | removed-in-next-major`),
   `deprecation_date`, `sunset_date`, and `docs_url`.
2. WHEN an extension is loaded by `E-extension-host` THEN the host
   SHALL annotate each registered factory and resource with
   `via_plugin_api = True` if it targets a published protocol /
   resource, and `via_plugin_api = False` if it targets an
   internal-only protocol; the admin UI displays the flag.
3. IF an extension registers against an internal-only protocol
   from a package marked `is_external = True` (per manifest)
   THEN the host SHALL refuse to load the extension and SHALL
   emit `ConfigurationError` with
   `reason="internal_protocol_targeted"`.
4. WHERE the service is configured `plugin_api.strict_mode = True`
   the host SHALL refuse to load any external extension that
   targets a protocol whose `protocol_schema_version` is older
   than the current supported minimum.

### Requirement 2: Enumerated Published Surface

**User Story:** As a Pychestrate maintainer, I want the published
set to be small and explicit, so that we can hold the compatibility
line.

**Acceptance Criteria (EARS):**

1. WHEN Phase 10 GA ships THEN the published factory protocols
   SHALL be exactly:
   - `object_store_driver` (from `0-object-store`)
   - `timeseries_driver` (from `0-timeseries-backend`)
   - `auth_provider` (from `1-authentication`)
   - `secrets_backend` (from `1-secrets-vault`)
   - `notification_channel` (from `2-notification-hub`)
   - `inbound_webhook_parser` (from `8-webhooks-in`)
   - `scm_provider` (from `6-source-integrations`)
   - `build_runner_kind` (from `6-build-orchestration`)
   - `test_runner_kind` (from `6-test-orchestration`)
   - `infra_tool_driver` (from `6-infra-orchestration`)
   - `resource_health_probe` (from `4-resource-health`)
   - `pool_allocation_strategy` (from `4-resource-pools`)
   - `progress_parser` (from `5-progress-ingest`)
   - `result_tree_parser` (from `5-result-ingest-watcher`)
   - `metric_exporter` (from `7-metrics-ingest`).
2. WHEN Phase 10 GA ships THEN the published resource extension
   bases SHALL be exactly:
   - `ResourceKindExtension` (from `4-resource-inventory`)
   - `PodMemberKindExtension` (from `3-pod-definitions`)
   - `ArtifactRendererExtension` (from `6-artifact-browser`)
   - `ArtifactClassifierExtension` (from `5-result-ingest-watcher`)
   - `DashboardTileKindExtension` (from `7-project-dashboards`)
   - `WebComponentBundleExtension` (from `9-wc-*`)
   - `MetricDefinitionExtension` (from `7-metrics-ingest`)
   - `NotificationTemplateExtension` (from `2-notification-hub`)
   - `MFAMethodExtension` (from `1-authentication`)
   - `CLISubcommandExtension` (from `8-cli`)
   - `RestEndpointExtension` (from `8-rest-api-v1`).
3. IF any factory protocol or resource base not in the above
   lists is registered as published THEN the service SHALL refuse
   to start with a `ConfigurationError` identifying the offending
   surface.
4. WHERE additional surfaces are promoted in future releases they
   SHALL pass a promotion checklist
   (`stability_criteria_met == True`, 90-day RFC, documented
   reference implementation) before appearing here.

### Requirement 3: Deprecation Windows and Sunset

**User Story:** As an extension author, I want a guaranteed
deprecation window before a protocol disappears, so that I can
update my package without my users getting paged.

**Acceptance Criteria (EARS):**

1. WHEN a published protocol is marked `deprecated` THEN it SHALL
   remain *loadable* for a **minimum of 18 months** from the
   `deprecation_date`; removal SHALL happen only at a service
   major-version bump on or after `sunset_date`.
2. WHEN an extension is loaded THAT targets a `deprecated`
   protocol THEN the host SHALL publish
   `entity.plugin_api.deprecation_hit` with the protocol name,
   the extension name, and the sunset date, and SHALL continue
   loading normally.
3. IF a breaking change to a published protocol is contemplated
   THEN the change SHALL ship first under a new
   `protocol_schema_version`, leave the old version valid until
   sunset, and emit `pychestrate_plugin_api_schema_bumps_total`
   at bump time.
4. WHILE a protocol is `removed-in-next-major` the service SHALL
   emit a startup log warning listing every installed extension
   still bound to it.

### Requirement 4: Version Compatibility Enforcement

**User Story:** As an operator, I want the host to refuse to run
with an incompatible extension, so that I fail fast rather than in
the middle of a run.

**Acceptance Criteria (EARS):**

1. WHEN an extension manifest declares `min_service_version` and
   `max_service_version` THEN the host SHALL refuse to load the
   extension if the running service version is outside that
   range; the refusal SHALL surface as a `ConfigurationError`
   with the range echoed in the message.
2. WHEN an extension declares targeted
   `protocol_schema_version` that is below the service's
   published `min_supported_schema_version` for that protocol
   THEN the host SHALL refuse to load with
   `reason="schema_version_unsupported"`.
3. WHEN the service upgrades to a new minor version THEN the
   upgrade SHALL NOT raise the `min_supported_schema_version`
   for any published protocol; such raises happen only at a
   major-version bump, paired with a 18-month deprecation
   window.
4. WHERE an extension has `capabilities_required` that exceed the
   host's sandbox policy (per `E-extension-sandbox`) the host
   SHALL refuse to load and SHALL NOT partially load any subset.

### Requirement 5: Documentation + Reference Artifacts

**User Story:** As an external author kicking off a new extension,
I want generated docs and a working template, so that the fastest
path to a loaded extension is under a day.

**Acceptance Criteria (EARS):**

1. WHEN `E-extension-docs` ships THEN it SHALL include a section
   "Published Plugin API Surface" generated from the same catalog
   as `/api/v1/plugin-api/_meta/catalog`; every published
   protocol and resource SHALL have a Sphinx page, a reference
   implementation link, and one minimal example package.
2. WHEN `E-extension-pack-template` ships THEN it SHALL
   scaffold a package targeting the published surface only,
   include a CI step that runs `pyc ext validate` (or
   equivalent), and SHALL refuse to scaffold against
   internal-only protocols.
3. IF a published protocol's reference implementation is
   missing or does not load at service startup THEN the service
   SHALL refuse to start with
   `ConfigurationError(reason="published_protocol_reference_missing")`.

## Property-Based Test Requirements

### Property 1: Deprecation Window Honored

- **Invariant:** For any protocol marked `deprecated` at time T
  and any service version that ships before T + 18 months, the
  protocol SHALL still be loadable; the host SHALL publish
  `entity.plugin_api.deprecation_hit` exactly once per
  `(extension_name, protocol_name)` pair per service process
  lifetime.
- **Generator:** Hypothesis strategy producing
  `(protocol_name, deprecation_date, service_upgrade_date,
  extension_count)` tuples with `extension_count ∈ [1, 50]` and
  `service_upgrade_date` drawn from `[deprecation_date - 30d,
  deprecation_date + 24 months]`.
- **Assertion:** Every extension loads if and only if
  `service_upgrade_date < deprecation_date + 18 months`;
  deprecation event count equals the number of loaded extensions
  targeting the deprecated protocol.
- **Sample size:** 1000 generated cases.

### Property 2: Catalog ↔ Code Consistency

- **Invariant:** For any entry `E` in
  `/api/v1/plugin-api/_meta/catalog`, there SHALL exist exactly
  one in-tree reference implementation whose declared
  `factory_protocol_name` or `ResourceExtension` class name
  matches `E.name` and whose `protocol_schema_version` matches
  `E.protocol_schema_version`.
- **Generator:** Strategy drawing catalog entries at random and
  a code-walker that enumerates in-tree references from
  `automojo/factories/pychestrate/...` and
  `automojo/extensions/pychestrate/...`.
- **Assertion:** Bijection between catalog entries and the
  reference-implementation set (per `name`); no entries with
  missing refs, no refs without catalog entries.
- **Sample size:** 1000 generated cases (effectively all
  entries plus negative cases introducing synthetic mismatches,
  which must be rejected by the test oracle).

### Property 3: Schema-Version Monotonicity

- **Invariant:** For any published protocol, the stream of
  `protocol_schema_version` values ever shipped by the service
  SHALL be strictly monotonically increasing over service
  releases; `min_supported_schema_version` SHALL be
  non-decreasing.
- **Generator:** Strategy producing simulated release histories of
  length `[1, 50]` with random additions, bumps, and
  `min_supported` raises.
- **Assertion:** No generated history violates monotonicity
  without also crossing a major-version boundary; any violation
  at a non-major boundary is flagged as a test failure.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** The catalog endpoint SHALL respond in
  `< 30 ms` p95. Extension load-time host checks added by this
  feature SHALL add `< 50 ms` cumulative per extension.
- **NFR-2 (Security):** The catalog endpoint is readable under
  `system:plugin_api.read` (read-only). No endpoint in this
  feature mutates state. Extension manifests are validated against
  a JSON Schema; unknown keys SHALL cause a rejection unless
  namespaced under `x-<vendor>-`. Capability manifests from
  extensions SHALL be clamped by the host sandbox policy before
  enforcement.
- **NFR-3 (Observability):** Emit
  `pychestrate_plugin_api_extensions_loaded_total{source,status}`,
  `pychestrate_plugin_api_deprecation_hits_total{protocol}`,
  `pychestrate_plugin_api_schema_bumps_total{protocol}`,
  `pychestrate_plugin_api_refused_loads_total{reason}`, and log
  events `plugin_api.extension.loaded`,
  `plugin_api.extension.refused`,
  `plugin_api.deprecation.hit`,
  `plugin_api.schema.bumped`,
  `plugin_api.catalog.served`. Trace spans: `plugin_api.load`,
  `plugin_api.validate`, `plugin_api.catalog.build`.
- **NFR-4 (Reliability):** Catalog content is derived from code
  annotations at startup and cached for the process lifetime; a
  corrupted annotation SHALL cause a loud startup failure
  (`ConfigurationError`) rather than a silently-empty catalog.
  Extension load failures SHALL NOT affect the catalog endpoint
  or other extensions.

## Out of Scope

- The host implementation itself — owned by `E-extension-host`.
- Per-protocol contract semantics — owned by each protocol's home
  feature (e.g., `auth_provider` semantics live in
  `1-authentication`).
- Sandbox capability enforcement — owned by
  `E-extension-sandbox`. This feature *delegates* sandbox
  clamping but does not own the policy.
- Extension package publishing / distribution channel — owned by
  `10-release-channels`.

## Dependencies

- **Depends on:** `E-extension-host`, `E-factory-protocols`,
  `E-resource-extensions`, `E-extension-manifest`,
  `E-extension-compat-check`, `E-extension-sandbox`,
  `E-extension-docs`, `E-extension-pack-template`, plus every
  feature owning a published protocol or resource base.
- **Depended on by:** Every out-of-tree
  `pychestrate-ext-<name>` package; internal features remain free
  to use internal-only protocols outside this surface.
- **Extension points exposed:** This feature does not declare new
  factory protocols or resource bases — it *catalogues* existing
  ones. Events: `entity.plugin_api.deprecation_hit`,
  `entity.plugin_api.schema_bumped`,
  `entity.plugin_api.extension_refused`. See
  implementation-plan.md Layer E — `E-plugin-api`.
