# E-plugin-api — Requirements

## Introduction

E-plugin-api is the externally-stable subset of Layer E: the published
factory protocols, resource extension bases, manifest schema,
capability vocabulary, scope API, and test-harness fixtures that
external teams may build against under a documented deprecation
window. Internal-only protocols remain behind `E-factory-protocols`
and `E-resource-extensions`; `E-plugin-api` re-exports and stability-
tags only the subset that has passed the stability review. It ships
in Phase 10 after the internal catalog has stabilized enough to
deliver useful commitments.

## Requirements

### Requirement 1: Versioned import surface

**User Story:** As an external plugin author, I want to `import
pychestrate.plugin.v1 as papi` and find a stable surface for the
published protocols and resource bases, so that my plugin survives
internal refactors that change non-public layout.

**Acceptance Criteria (EARS):**

1. WHEN a caller imports `pychestrate.plugin.v1` THEN the system
   SHALL expose every published `FactoryProtocolBase` subclass,
   every published `ResourceExtension` base class, the
   `ExtensionManifest` dataclass, the capability vocabulary, and the
   `ExtensionConfigScope` read methods.
2. IF a caller imports a symbol not in the published catalog THEN
   the system SHALL raise `AttributeError` with a message pointing
   to the alternative.
3. WHERE `pychestrate.plugin.v2` is introduced THEN
   `pychestrate.plugin.v1` SHALL continue to work for a deprecation
   window declared in docs.

### Requirement 2: Deprecation window enforcement

**User Story:** As a platform maintainer, I want each published
symbol to carry deprecation metadata enforceable at import time, so
that authors see warnings early rather than breakage late.

**Acceptance Criteria (EARS):**

1. WHEN a deprecated symbol is imported from
   `pychestrate.plugin.v<N>` THEN the system SHALL emit a
   `DeprecationWarning` containing the deprecation date, the removal
   date, and the replacement symbol.
2. IF the removal date has passed AND the symbol is still present
   (misconfiguration) THEN the system SHALL emit a
   `pychestrate_plugin_api_overdue_deprecation` log event and keep
   the symbol available under the previous major to avoid breaking
   consumers mid-phase.
3. WHEN the service is built with `--strict-plugin-api` THEN the
   system SHALL raise `ConfigurationError` if any overdue deprecation
   is detected.

### Requirement 3: Contract stability review gate

**User Story:** As a platform maintainer, I want a check that
prevents a new protocol or base from becoming published until it
passes a stability review, so that premature publication does not
create long-term maintenance debt.

**Acceptance Criteria (EARS):**

1. WHEN a declaration module sets `stability = "published"` THEN
   the service CI SHALL require a companion entry in
   `docs/extensions/_stability_reviews/<name>.yaml` with
   `{reviewed_on, reviewer, notes}`.
2. IF the companion file is missing THEN the CI SHALL fail.
3. WHERE the reviewed-on date is older than 12 months THEN the CI
   SHALL emit a warning and require a re-review annotation.

### Requirement 4: Published test-harness fixtures

**User Story:** As an external plugin author, I want an officially-
supported pytest fixture that spins a fake Pychestrate service so I
can test my plugin in CI without vendoring the service source, so
that my CI is reliable and fast.

**Acceptance Criteria (EARS):**

1. WHEN a caller imports
   `pychestrate.plugin.v1.testing.service_fixture` THEN the system
   SHALL return a pytest fixture that yields a
   `FakeService` with `install_pack(pack_root=)`,
   `list_loaded_factories()`, and `emit_event()` methods.
2. WHERE the fixture's `install_pack` is called on an incompatible
   pack THEN it SHALL raise `ConfigurationError` with the same
   reason text the real service would emit.

## Property-Based Test Requirements

### Property 1: Published-subset closure

- **Invariant:** For any symbol exported from
  `pychestrate.plugin.v1`, that symbol's catalog entry has
  `stability = "published"` and a current stability review file.
- **Generator:** enumerate the module's `__all__`; pair with
  catalog entries.
- **Assertion:** Every paired entry satisfies both conditions; no
  entry is internal-only.
- **Sample size:** every symbol in `__all__` (bounded, not 1000);
  property exercised as a parametrized-over-symbols test plus a
  Hypothesis fuzz that injects synthetic internal entries and
  confirms they are not exported.

### Property 2: Deprecation-metadata completeness

- **Invariant:** For any deprecated symbol, the deprecation record
  has `deprecated_on`, `remove_on`, `replacement` all populated; and
  `remove_on > deprecated_on`.
- **Generator:** synthetic deprecation records.
- **Assertion:** Completeness + date ordering enforced at import
  time; overdue deprecations surface the log event.
- **Sample size:** 1000 generated cases.

### Property 3: Fixture parity with real service

- **Invariant:** For any pack that loads successfully against the
  real service, it also loads successfully against the fixture; for
  any pack that fails closed against the real service, it fails
  closed against the fixture with the same reason string.
- **Generator:** synthetic packs (valid + invalid).
- **Assertion:** Outcome parity across a matched pair of service
  instances.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Published-module import adds < 50 ms on
  first import; subsequent imports cached by Python's import system.
- **NFR-2 (Security):** Only `stability = "published"` entries are
  re-exported; capability vocabulary and scope read-only methods are
  the only security-sensitive published surface.
- **NFR-3 (Observability):** Metrics
  `pychestrate_plugin_api_imports_total{version}`,
  `pychestrate_plugin_api_deprecation_warnings_total{symbol}`,
  `pychestrate_plugin_api_overdue_deprecations_total`; log events
  `pychestrate_plugin_api_overdue_deprecation`,
  `pychestrate_plugin_api_stability_review_missing`; trace span
  `pychestrate_plugin_api.import`.
- **NFR-4 (Reliability):** Published surface is covered by
  contract tests that run in service CI on every commit.

## Out of Scope

- Internal protocol catalog (`E-factory-protocols`).
- Publishing implementation binaries (`10-release-channels`).
- Sandbox vocabulary definition (`E-extension-sandbox` owns it;
  plugin-api re-exports only).

## Dependencies

- **Depends on:** every other Layer E feature, plus
  `10-release-channels`, `10-observability`.
- **Depended on by:** external extension authors.
- **Extension points exposed:** this feature *publishes* the subset
  of Layer E extension points (factory protocols, resource bases,
  capability vocabulary, manifest schema, hook decorator). No new
  extension points of its own.
