# E-extension-compat-check — Requirements

## Introduction

E-extension-compat-check is the compile-time-ish gate that stops a
silently incompatible extension from loading. It combines two
mechanisms:

1. The manifest's `min_service_version` / `max_service_version` PEP 440
   bounds (parsed by `E-extension-manifest`).
2. A numeric `FACTORY_PROTOCOL_SCHEMA_VERSION` on each
   `FactoryProtocolBase` declaration (owned by `E-factory-protocols`).

When either check fails, the extension is rejected with a specific
reason and no classes are registered. This feature ships in Phase 0.5
alongside the rest of the Layer E core because its absence creates
silent-runtime-`AttributeError`s the moment a protocol adds a new
method.

## Requirements

### Requirement 1: Service-version window enforcement

**User Story:** As a service operator, I want extensions whose declared
service-version window excludes the running version to be rejected at
load time, so that I never see a partial protocol implementation on the
wire.

**Acceptance Criteria (EARS):**

1. WHEN the running service version is outside
   `[min_service_version, max_service_version]` THEN the system SHALL
   reject the package and emit `extension.load_failed` with reason
   `service_version_out_of_bounds`.
2. IF `min_service_version` is absent THEN the system SHALL assume
   `0.0.0`; if `max_service_version` is absent, SHALL assume unbounded
   upper.
3. WHERE a pre-release service version (e.g., `2.0.0rc1`) is checked
   THEN the system SHALL follow PEP 440 pre-release ordering rules.

### Requirement 2: Protocol schema-version enforcement

**User Story:** As a core developer, I want adding a new required
method to a protocol to be a detectable bump that fails old
implementations at load rather than at first call, so that I can
evolve contracts safely.

**Acceptance Criteria (EARS):**

1. WHEN a `FactoryExtension` sets
   `FACTORY_PROTOCOL_SCHEMA_VERSION_IMPLEMENTED` lower than the
   catalog's declared `FACTORY_PROTOCOL_SCHEMA_VERSION` THEN the
   system SHALL reject the factory and emit `extension.load_failed`
   with reason `schema_version_too_old`.
2. IF the factory's impl version is higher than the catalog THEN the
   system SHALL accept the factory and emit
   `extension.protocol_schema_ahead` (forward-compatible).
3. WHERE a factory omits the implemented-version attribute AND the
   catalog's declared version is non-zero THEN the system SHALL
   reject with reason `schema_version_unspecified`.

### Requirement 3: Cross-check diagnostic surface

**User Story:** As an extension author debugging a rejection, I want a
single diagnostic endpoint that tells me exactly which check failed and
what I need to change, so that I can fix the manifest or bump the
schema version without guesswork.

**Acceptance Criteria (EARS):**

1. WHEN the CLI `pychestrate-admin compat check <manifest-path>` is
   run THEN the system SHALL print the running service version, the
   declared window, and the schema-version gap for every protocol the
   manifest declares.
2. WHEN the REST route
   `GET /admin/extensions/{name}/compat` is called with
   `extensions.read` permission THEN the system SHALL return the same
   information in JSON.
3. IF the extension was rejected at load time THEN the diagnostic
   SHALL include the exact `ConfigurationError` message and the
   refusal reason from `ManifestRegistry.list_refusals`.

### Requirement 4: Deprecation window reporting

**User Story:** As a platform maintainer about to bump a protocol's
schema version, I want a report of every currently-loaded factory with
its implemented-version delta, so that I can warn extension authors
before breaking them.

**Acceptance Criteria (EARS):**

1. WHEN `pychestrate-admin compat report` is run THEN the system
   SHALL emit a table of `(protocol, declared_version, worst_impl,
   ext_count_below_current, ext_count_at_current, ext_count_ahead)`.
2. WHERE an extension's implemented version is the oldest still-valid
   version on the service THEN the report SHALL flag it as "candidate
   for next bump drop".

## Property-Based Test Requirements

### Property 1: Window fail-closed

- **Invariant:** For any manifest whose declared window excludes the
  running version, load fails closed without partial registration
  (no factory classes, no resource kinds, no bus subscriptions
  active).
- **Generator:** hypothesis tuples of
  `(running, min, max)` with biased out-of-window distributions.
- **Assertion:** On out-of-window, host public state is unchanged
  relative to the pre-load snapshot.
- **Sample size:** 1000 generated cases.

### Property 2: Schema version monotonicity

- **Invariant:** For any protocol with catalog version `C` and impl
  version `I`, loading behavior is:
  - `I < C` → reject.
  - `I == C` → accept.
  - `I > C` → accept with warning.
  No other outcome is ever observed.
- **Generator:** `(C, I)` over `[0, 100]`.
- **Assertion:** Outcome classification matches the table.
- **Sample size:** 1000 generated cases.

### Property 3: Diagnostic faithfulness

- **Invariant:** For any rejection observed at load time, the
  diagnostic surface reports the same `refusal_reason` that was
  recorded in `ManifestRegistry.list_refusals`.
- **Generator:** random rejected-manifest scenarios.
- **Assertion:** String equality between the two fields.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Compat check adds < 1 ms per package on
  top of manifest parse.
- **NFR-2 (Security):** Diagnostic endpoints require
  `extensions.read`; do not leak secret or internal paths.
- **NFR-3 (Observability):** Metrics
  `pychestrate_extension_compat_rejected_total{reason}`,
  `pychestrate_extension_compat_schema_ahead_total{protocol}`;
  log events `pychestrate_extension_compat_rejected`,
  `pychestrate_extension_compat_schema_ahead`,
  `pychestrate_extension_compat_report_generated`; trace span
  `pychestrate_extension.compat.check`.
- **NFR-4 (Reliability):** Fail-closed default; no permissive bypass
  for schema-version-too-old (permissive mode only covers
  version-window mismatch and manifest-missing).

## Out of Scope

- Runtime contract enforcement (only load-time checks are here;
  runtime dispatch uses the lookup gates in `E-extension-sandbox`).
- Semver-style auto-compatibility (we use explicit integer schema
  bumps).

## Dependencies

- **Depends on:** `E-extension-host`, `E-extension-manifest`,
  `E-factory-protocols`.
- **Depended on by:** every downstream feature that evolves a
  protocol, `E-extension-registry-ui`, `E-plugin-api`.
- **Extension points exposed:** `FACTORY_PROTOCOL_SCHEMA_VERSION` on
  protocols and `FACTORY_PROTOCOL_SCHEMA_VERSION_IMPLEMENTED` on
  factories (both plain class attributes, no decorators).
