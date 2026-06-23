# E-extension-manifest — Requirements

## Introduction

E-extension-manifest defines the `pychestrate_ext.yaml` manifest file that
ships inside every `pychestrate-ext-<name>` distribution. The manifest
declares identity (name, version, author), inventory (protocols implemented,
resource kinds registered, bus subscriptions, capabilities requested),
dependency metadata (declared extension dependencies), and compatibility
bounds (`min_service_version`, `max_service_version`). The host refuses to
load manifests that are absent (strict mode), malformed, or whose version
bounds exclude the running service version. This feature ships in Phase
0.5 next to `E-extension-host`; `E-extension-compat-check` consumes the
version bounds, `E-extension-sandbox` (Phase 8) consumes the capability
list.

## Requirements

### Requirement 1: Manifest discovery and parsing

**User Story:** As a Pychestrate host, I want to locate and parse the
manifest for every discovered extension package, so that I can make
load-or-refuse decisions with all declared metadata on hand before any
Python class is registered.

**Acceptance Criteria (EARS):**

1. WHEN the host scans a namespace package under
   `ccai/factories/pychestrate` or `ccai/extensions/pychestrate`
   THEN the system SHALL look for a sibling `pychestrate_ext.yaml` in
   the package's distribution root (`importlib.metadata.Distribution.files`).
2. IF a `pychestrate_ext.yaml` is missing and strict mode is active
   THEN the system SHALL refuse to load any class from the package and
   emit `extension.manifest_missing`.
3. WHERE strict mode is inactive AND the manifest is missing THEN the
   system SHALL load with a synthesized default manifest of
   `{name: "<dist-name>", version: "0.0.0", capabilities: []}` and emit
   a `pychestrate_extension_manifest_synthesized` warning.
4. WHEN a manifest is present but malformed YAML THEN the system SHALL
   raise `ConfigurationError` naming the offending path and line, and
   fail-closed without registering any of the package's classes.

### Requirement 2: Required and optional fields

**User Story:** As an extension author, I want a stable, documented
manifest schema, so that I know exactly what fields Pychestrate needs and
which are optional.

**Acceptance Criteria (EARS):**

1. WHEN a manifest is parsed THEN the system SHALL require `name`,
   `version` (PEP 440), and `schema_version` (manifest schema version,
   integer starting at 1).
2. IF any required field is missing THEN the system SHALL raise
   `ConfigurationError` listing every missing field via
   `os.linesep.join`.
3. WHERE the manifest declares `protocols: [<name>, ...]`,
   `resources: [<base_name>, ...]`, `capabilities: [<cap>, ...]`,
   `subscriptions: [<topic>, ...]`, `depends_on: [<ext-name>, ...]`,
   `min_service_version`, `max_service_version`, `author`,
   `homepage`, `license` THEN the system SHALL expose each field on
   the `ExtensionManifest` object.
4. WHEN an unknown top-level key is present THEN the system SHALL emit
   `pychestrate_extension_manifest_unknown_key` warning but NOT fail
   (forward-compatible).

### Requirement 3: Version bound enforcement

**User Story:** As a service operator, I want to refuse loading any
extension whose declared compatibility bounds exclude the running
service version, so that incompatible extensions never silently corrupt
state.

**Acceptance Criteria (EARS):**

1. WHEN `running_service_version` is outside the manifest's
   `[min_service_version, max_service_version]` PEP 440 interval THEN
   the system SHALL refuse to register any class from the package and
   emit `extension.load_failed` with reason `version_out_of_bounds`.
2. IF `min_service_version` is absent THEN the system SHALL treat it as
   `0.0.0`.
3. IF `max_service_version` is absent THEN the system SHALL treat it as
   `+infinity` (the upper bound is open).
4. WHERE the version bounds parse as invalid PEP 440 THEN the system
   SHALL raise `ConfigurationError` naming the offending field.

### Requirement 4: Declared inventory cross-check

**User Story:** As a platform maintainer, I want the manifest's declared
inventory (protocols, resources, subscriptions) to match what the
package actually ships, so that a mis-declared capability is caught at
load time not at first call.

**Acceptance Criteria (EARS):**

1. WHEN the manifest declares `protocols: [X, Y]` THEN the system SHALL
   verify at least one `FactoryExtension` with `factory_protocol_name`
   in `{X, Y}` loads from the package.
2. IF a declared protocol has no matching factory THEN the system SHALL
   raise `ConfigurationError` with the manifest path and the
   undelivered protocol name.
3. WHERE the package contributes a factory whose
   `factory_protocol_name` is not in the manifest's `protocols` list
   THEN the system SHALL emit
   `pychestrate_extension_manifest_protocol_undeclared` and (in strict
   mode) refuse to register the factory.

## Property-Based Test Requirements

### Property 1: Fail-closed outside version window

- **Invariant:** For any extension manifest whose
  `(min_service_version, max_service_version)` window excludes the
  running service version, the load attempt fails closed — no class,
  subscription, or capability from that package becomes active.
- **Generator:** hypothesis tuples of
  `(running_version, min_version, max_version)` with biased
  in-window/out-of-window distributions.
- **Assertion:** When running is outside the window,
  `host.list_factory_protocols()` contains none of the package's
  factories, `catalog.collect_kinds` excludes its kinds, and the bus
  has no subscription wired.
- **Sample size:** 1000 generated cases.

### Property 2: Parser round-trip stability

- **Invariant:** For any well-formed `ExtensionManifest` object,
  `parse(serialize(m)) == m` holds across every declared field.
- **Generator:** hypothesis strategies constructing fully-populated
  manifests with random optional-field presence.
- **Assertion:** Equality holds after YAML round-trip and after JSON
  round-trip.
- **Sample size:** 1000 generated cases.

### Property 3: Declared-vs-delivered inventory consistency

- **Invariant:** For any manifest with `protocols: L`, `resources: R`,
  the loaded package's delivered sets are equal to `L` and `R` in
  strict mode.
- **Generator:** synthetic package + manifest pairs with biased
  mismatches.
- **Assertion:** Mismatch cases fail closed with a readable
  `ConfigurationError`; matched cases load cleanly.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Manifest discovery + parse completes in
  under 20 ms per package; full manifest pass over 100 packages
  completes in under 1 s.
- **NFR-2 (Security):** YAML parser uses `yaml.safe_load`; manifests
  never trigger arbitrary tag resolution. Manifest file path must
  resolve under the distribution root (no path traversal).
- **NFR-3 (Observability):** Metrics
  `pychestrate_extension_manifest_parsed_total{result}`,
  `pychestrate_extension_manifest_version_rejected_total`,
  `pychestrate_extension_manifest_missing_total`; log events
  `pychestrate_extension_manifest_parsed`,
  `pychestrate_extension_manifest_rejected`,
  `pychestrate_extension_manifest_synthesized`; trace span
  `pychestrate_extension.manifest.parse`.
- **NFR-4 (Reliability):** Fail-closed on malformed YAML, missing
  required fields, invalid PEP 440, and inventory mismatches. Warnings
  only for unknown top-level keys (forward compatibility).

## Out of Scope

- Capability enforcement (`E-extension-sandbox`).
- Version-schema-based protocol bumps (`E-extension-compat-check`).
- Admin UI rendering (`E-extension-registry-ui`).

## Dependencies

- **Depends on:** `E-extension-host`, `E-factory-protocols`,
  `E-resource-extensions`.
- **Depended on by:** `E-extension-lifecycle`, `E-extension-precedence`,
  `E-extension-compat-check`, `E-extension-config`, `E-extension-hooks`,
  `E-extension-sandbox`, `E-extension-registry-ui`, `E-plugin-api`.
- **Extension points exposed:** none; this feature defines the manifest
  schema consumed by every other Layer E feature.
