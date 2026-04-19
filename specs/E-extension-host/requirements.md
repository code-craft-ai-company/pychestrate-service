# E-extension-host — Requirements

## Introduction

E-extension-host is the `SuperFactory`-style core of Pychestrate's Layer E
extensibility model. It scans the configured `automojo.factories.pychestrate.*`
and `automojo.extensions.pychestrate.*` namespaces on `sys.path` at service
startup, loads `FactoryExtension` and `ResourceExtension` descendants into
typed registries, sorts factories by `PRECEDENCE`, and exposes the lookup API
that every other Pychestrate feature consumes to acquire its drivers,
strategies, and resource kinds. It ships in Phase 0.5 before any feature
registers extension points, and sits between Layer 0 (`0-web-app-host`,
`0-message-bus`, `10-observability`) and every downstream layer (0..10). This
feature owns the host singleton; sibling Layer E features (`E-factory-protocols`,
`E-resource-extensions`, `E-extension-manifest`, `E-extension-lifecycle`,
`E-extension-precedence`, `E-extension-compat-check`) layer on top of its scan,
load, and lookup primitives.

## Requirements

### Requirement 1: Deterministic namespace scan at startup

**User Story:** As a service operator, I want Pychestrate to deterministically
discover every installed `pychestrate-ext-<name>` package at startup, so that
every configured driver and resource kind is available before the WSGI listener
accepts traffic.

**Acceptance Criteria (EARS):**

1. WHEN the service process reaches the Layer E bootstrap step THEN the system
   SHALL walk every directory on `sys.path` for `automojo/factories/pychestrate`
   and `automojo/extensions/pychestrate` trees and record a module list sorted
   by dotted name.
2. IF the same dotted module name is discovered on more than one `sys.path`
   entry THEN the system SHALL log a `pychestrate_extension_duplicate_module`
   warning and keep only the first occurrence.
3. WHILE the scan is in progress the system SHALL refuse to mark
   `0-system-health` readiness as `ready` for the `extensions` probe.
4. WHERE the environment variable `PYCHESTRATE_EXTENSION_SCAN_PATHS` is set the
   system SHALL restrict scanning to the comma-separated list of roots rather
   than all of `sys.path`.

### Requirement 2: Typed registry load with PRECEDENCE sort

**User Story:** As a Pychestrate core developer, I want discovered
`FactoryExtension` subclasses placed into a single chain sorted by `PRECEDENCE`
and `ResourceExtension` subclasses placed into per-base-type collections, so
that lookup by protocol method yields a deterministic override order.

**Acceptance Criteria (EARS):**

1. WHEN module loading completes THEN the system SHALL hold exactly one
   `ExtensionHost` singleton reachable via `get_extension_host()`.
2. IF two loaded `FactoryExtension` classes share the same `factory_protocol_name`
   and `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` naming both
   classes and fail service startup (fail-closed).
3. WHEN `create_instance_by_order` is invoked with a protocol method callable
   THEN the system SHALL return the instance produced by the highest-precedence
   (lowest numeric `PRECEDENCE`) matching factory.
4. WHERE the same `ResourceExtension` direct subclass is discovered under more
   than one module THEN the system SHALL emit the `extension.loaded` event
   exactly once keyed by `(base_type, qualname)`.

### Requirement 3: Admin re-scan without service restart

**User Story:** As a service operator, I want to trigger a live re-scan after
installing a new extension package, so that I can adopt a new driver without a
full service bounce and its connection-pool disruption.

**Acceptance Criteria (EARS):**

1. WHEN the admin route `POST /admin/extensions/rescan` is called by a caller
   with the `extensions.rescan` permission THEN the system SHALL re-walk the
   scan paths and load any modules not previously present.
2. IF a re-scan detects a module whose manifest rejects the running service
   version THEN the system SHALL refuse to add any class from that module and
   emit `extension.load_failed` with reason `version_out_of_bounds`.
3. WHILE a re-scan is in progress the system SHALL continue serving existing
   protocol lookups from the pre-scan snapshot and SHALL not block request
   threads.
4. WHEN a re-scan completes THEN the system SHALL emit
   `pychestrate_extension_rescan_completed` with counts
   `(modules_added, modules_removed, factories_added, resources_added)`.

### Requirement 4: Fail-closed load-time validation

**User Story:** As a platform engineer, I want the host to refuse to start with
partially loaded extension state, so that a broken extension never silently
disables a downstream feature.

**Acceptance Criteria (EARS):**

1. IF a module import raises any exception THEN the system SHALL catch the
   exception, emit `extension.load_failed` with the qualified module name and
   traceback, and re-raise a `ConfigurationError` with the collected failure
   list attached to its `lines` attribute.
2. WHEN any single factory or resource class rejects validation (missing
   `factory_protocol_name`, negative `PRECEDENCE`, duplicate subclass marker)
   THEN the system SHALL record the rejection and fail service startup with a
   consolidated multiline error message built via `os.linesep.join`.
3. WHERE `PYCHESTRATE_EXTENSION_SCAN_MODE=permissive` is set the system SHALL
   downgrade per-module import errors to warnings but SHALL still fail closed
   on duplicate-precedence collisions.

## Property-Based Test Requirements

### Property 1: Deterministic precedence ordering

- **Invariant:** For any set of N distinct `FactoryExtension` classes with
  pairwise-distinct `(factory_protocol_name, PRECEDENCE)` pairs, the order
  returned by `iterate_override_types_for_each` is deterministic across repeated
  loads and independent of discovery order.
- **Generator:** `hypothesis.strategies.lists(factory_class_strategy, min_size=1,
  max_size=32, unique_by=lambda c: (c.factory_protocol_name, c.PRECEDENCE))`
  with a permutation strategy over the discovery order.
- **Assertion:** For every permutation of the generated list, the chain
  returned by `ExtensionHost.iterate_override_types_for_each(method)` is byte-
  identical to the canonical chain (ascending `PRECEDENCE`, tie-broken by
  `qualname`).
- **Sample size:** 1000 generated cases.

### Property 2: Atomic load on invalid module

- **Invariant:** For any module set that contains at least one import-error
  module in strict mode, the `ExtensionHost` public registries observe no partial
  state — every `list_factory_protocols()` and `list_resource_kinds()` call
  before successful startup returns an empty view.
- **Generator:** mixed-validity module lists (some valid, some raising
  `ImportError`/`ValueError` at import), seeded with Hypothesis.
- **Assertion:** When `ExtensionHost.bootstrap(modules)` raises
  `ConfigurationError`, `host.extension_factories == []` and
  `host.resource_collections == {}`.
- **Sample size:** 1000 generated cases.

### Property 3: Rescan idempotence

- **Invariant:** For any steady-state module set, calling `rescan()` N times in
  a row leaves registry contents unchanged after the first call.
- **Generator:** any validated module set plus `N in range(2, 20)`.
- **Assertion:** `host.snapshot_digest()` is equal across iterations 1..N.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Cold scan + load of 100 modules must complete in
  under 750 ms on the reference developer machine; re-scan of an unchanged tree
  must complete in under 75 ms.
- **NFR-2 (Security):** Scan honors `PYCHESTRATE_EXTENSION_SCAN_PATHS` allow-list;
  re-scan route requires the `extensions.rescan` RBAC permission and is
  audit-logged via `1-audit-log` with actor, timestamp, and diff counts.
- **NFR-3 (Observability):** Emits metrics `pychestrate_extension_scan_duration_seconds`
  (histogram), `pychestrate_extension_factories_loaded_total` (gauge),
  `pychestrate_extension_resources_loaded_total` (gauge),
  `pychestrate_extension_load_failures_total` (counter); log events
  `pychestrate_extension_scan_started`, `pychestrate_extension_scan_completed`,
  `pychestrate_extension_load_failed`; trace span
  `pychestrate_extension.bootstrap`.
- **NFR-4 (Reliability):** Fail-closed on duplicate precedence and on strict-mode
  import errors; permissive mode allowed only in non-production. Host never
  mutates sys.modules entries it did not create.

## Out of Scope

- Hot unload of a loaded module's classes (Python does not support it safely);
  unload semantics are manifest-driven and land in `E-extension-lifecycle`.
- Capability enforcement (belongs to `E-extension-sandbox`, Phase 8).
- Site-pin PRECEDENCE overrides (belongs to `E-extension-precedence`).
- Manifest parsing (belongs to `E-extension-manifest`); the host consumes the
  parsed manifest object.

## Dependencies

- **Depends on:** `0-web-app-host`, `0-message-bus`, `0-system-health`,
  `10-observability`, `1-audit-log`.
- **Depended on by:** `E-factory-protocols`, `E-resource-extensions`,
  `E-extension-manifest`, `E-extension-lifecycle`, `E-extension-precedence`,
  `E-extension-compat-check`, `E-extension-config`, `E-extension-hooks`,
  `E-extension-sandbox`, `E-extension-registry-ui`, `E-plugin-api`, and every
  downstream layer that declares a factory or resource surface.
- **Extension points exposed:** none directly — this feature is the host that
  *implements* the extension surfaces declared by other features.
