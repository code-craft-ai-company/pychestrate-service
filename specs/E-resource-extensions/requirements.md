# E-resource-extensions — Requirements

## Introduction

E-resource-extensions is the Pychestrate-owned catalog of `ResourceExtension`
base classes — the "new kind of thing" extension surface (resource kinds,
pod member kinds, artifact renderers, dashboard tiles, CLI subcommands,
WebComponent bundles, REST endpoints, audit event types, etc.). Unlike
factory protocols, resource extensions do not participate in PRECEDENCE
override chains; they form *sets of kinds*. This feature ships in Phase 0.5
alongside `E-extension-host` and `E-factory-protocols`, and is populated
by every subsequent phase whose owning feature declares a `resource:`
surface. It sits between `E-extension-host` and every
downstream consumer layer.

## Requirements

### Requirement 1: Per-base collection model

**User Story:** As a feature author, I want to declare a new
`ResourceExtension` base class — e.g., `PodMemberKindExtension` — and have
Pychestrate automatically scan all loaded modules and expose every direct
subclass as a stable (name, type) list, so that my feature can enumerate
kinds at runtime without hand-wiring registration.

**Acceptance Criteria (EARS):**

1. WHEN a module declares a direct subclass of a known
   `ResourceExtension` base THEN the system SHALL add that subclass to
   the per-base collection keyed by the base class.
2. IF the same subclass is discovered more than once THEN the system
   SHALL deduplicate by qualified class name and emit
   `extension.loaded` at most once per `(base_type, qualname)`.
3. WHERE a base class declares `allow_indirect_subclasses = True` THEN
   the system SHALL include indirect subclasses too; otherwise it SHALL
   include only direct subclasses (default).
4. WHEN a consumer calls
   `catalog.collect_kinds(base_cls=PodMemberKindExtension)` THEN the
   system SHALL return a list of `(name, type)` pairs sorted by
   `name` (class attribute `resource_kind_name` if set, else
   `__qualname__`).

### Requirement 2: Catalog of registered bases

**User Story:** As a Pychestrate platform maintainer, I want one in-repo
catalog listing every declared `ResourceExtension` base class with its
owning feature id, so that a new base class cannot ship without showing
up in the catalog and in the admin UI.

**Acceptance Criteria (EARS):**

1. WHEN a module under
   `source/site/automojo/pychestrate/webservice/extension/resources/_declarations/`
   declares a `ResourceExtension` subclass marked with
   `is_resource_extension_base = True` THEN the system SHALL register it
   in `ResourceExtensionCatalog`.
2. IF two declared bases share the same `resource_base_name` THEN the
   system SHALL raise `ConfigurationError` naming both qualified names.
3. WHEN the CLI command `pychestrate-admin resources list` is invoked
   THEN the system SHALL emit a sorted list of
   `(base_name, owning_feature, kind_count)` rows.

### Requirement 3: Declared schema per kind

**User Story:** As a resource-kind author, I want to declare a typed
attribute schema on my subclass, so that pod/resource registration can
validate against the schema without each consumer reinventing validation.

**Acceptance Criteria (EARS):**

1. WHEN a kind subclass declares `attribute_schema: Mapping[str, Type]`
   THEN the system SHALL expose it on
   `catalog.get_kind(base_cls=..., name=...).attribute_schema`.
2. IF a kind is registered without a `resource_kind_name` THEN the
   system SHALL derive one from `__qualname__` and emit a
   `pychestrate_extension_resource_kind_name_derived` warning.
3. WHEN two kinds under the same base share the same
   `resource_kind_name` THEN the system SHALL raise
   `ConfigurationError` and fail-closed startup.

### Requirement 4: Live rescan integration

**User Story:** As a service operator, I want a new resource kind in an
installed extension to appear after a live rescan, so that I can adopt
new kinds without restarting the service.

**Acceptance Criteria (EARS):**

1. WHEN `E-extension-host.rescan()` completes THEN the system SHALL
   re-walk the loaded modules, update every per-base collection, and
   emit `extension.resource_kinds_changed` with the diff.
2. WHILE a rescan is in progress the system SHALL continue serving
   `collect_kinds` from the previous snapshot.

## Property-Based Test Requirements

### Property 1: Collection determinism

- **Invariant:** For any set of `N` declared kinds under a single base,
  `collect_kinds` returns the same ordered list regardless of module
  discovery order.
- **Generator:** permutations of a hypothesis-generated list of
  `(name, qualname)` pairs.
- **Assertion:** `collect_kinds` output is deeply equal across every
  permutation.
- **Sample size:** 1000 generated cases.

### Property 2: Base isolation

- **Invariant:** For any two disjoint sets of declared kinds under two
  distinct bases, `collect_kinds(base=A)` never contains a kind declared
  under base `B` and vice versa.
- **Generator:** two independent kind sets, each tagged with a distinct
  base class.
- **Assertion:** Set intersection of the two returned lists is empty.
- **Sample size:** 1000 generated cases.

### Property 3: Duplicate-name fail-closed

- **Invariant:** For any pair of kinds under the same base sharing a
  `resource_kind_name`, catalog registration raises
  `ConfigurationError` and the catalog's public collection contains
  neither partial nor swapped state.
- **Generator:** a valid kind set plus a biased duplicate injection.
- **Assertion:** On collision, `catalog.collect_kinds(base_cls=...)` is
  empty during the failed bootstrap attempt.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** `collect_kinds` is `O(1)` against a cached
  per-base tuple; cache rebuild on rescan is `O(K log K)` where `K` is
  the kind count per base.
- **NFR-2 (Security):** Catalog is read-only post-bootstrap; mutation
  helpers are gated by `extensions.manage_catalog` and only called on
  the rescan path.
- **NFR-3 (Observability):** Metrics
  `pychestrate_extension_resource_base_registered_total{base}`,
  `pychestrate_extension_resource_kind_registered_total{base,kind}`,
  `pychestrate_extension_resource_collect_total{base}`; log events
  `pychestrate_extension_resource_base_registered`,
  `pychestrate_extension_resource_kind_registered`,
  `pychestrate_extension_resource_kinds_changed`; trace span
  `pychestrate_extension.resource_catalog.collect`.
- **NFR-4 (Reliability):** Fail-closed on duplicate base or kind names;
  rescan changes are atomic (new snapshot replaces the previous view
  with a single reference swap).

## Out of Scope

- PRECEDENCE semantics (those belong to factory protocols in
  `E-factory-protocols`).
- Per-kind capability gating (`E-extension-sandbox`).
- UI rendering of kinds (`E-extension-registry-ui`).

## Dependencies

- **Depends on:** `E-extension-host`, `0-message-bus`.
- **Depended on by:** every feature that declares a `resource:`
  extension surface: `0-persistence`, `0-system-health`,
  `1-authentication`, `1-rbac`, `1-audit-log`, `2-projects`,
  `2-tagging`, `2-notification-hub`, `2-project-templates`, `3-*`,
  `4-*`, `5-*`, `6-*`, `7-*`, `8-rest-api-v1`, `8-cli`, `9-*`.
- **Extension points exposed:** none itself; it is the collection
  mechanism for every `resource:` point declared downstream.
