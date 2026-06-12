# E-factory-protocols — Requirements

## Introduction

E-factory-protocols is the Pychestrate-owned catalog of declared
`FactoryProtocolBase` subclasses — the named-behavior extension surface
(e.g., `object_store_driver`, `auth_provider`, `notification_channel`,
`resource_health_probe`). This feature owns the protocol declarations, the
catalog that tracks them, the Sphinx-documented contract per protocol, the
reference implementation shipped in-tree, and the tooling that enforces
protocol-name uniqueness and schema-version bumps. It sits in Phase 0.5
alongside `E-extension-host`; each subsequent phase populates its protocol
entries as the owning feature ships. E-factory-protocols sits between the
host (`E-extension-host`) and every feature that declares a factory
extension point.

## Requirements

### Requirement 1: Central catalog of declared protocols

**User Story:** As a Pychestrate platform maintainer, I want one in-repo
catalog listing every declared factory protocol with its name, owning
feature, and schema version, so that I can detect naming collisions at
build time and track protocol changes across phases.

**Acceptance Criteria (EARS):**

1. WHEN a module under `source/site/ccai/pychestrate/webservice/extension/protocols/`
   declares a new `FactoryProtocolBase` subclass THEN the system SHALL
   register the subclass in the process-wide `FactoryProtocolCatalog` keyed
   by `factory_protocol_name`.
2. IF two declared subclasses share the same `factory_protocol_name` THEN
   the system SHALL raise `ConfigurationError` at import time naming both
   qualified class names.
3. WHERE the module declares a `FACTORY_PROTOCOL_SCHEMA_VERSION` attribute
   on the subclass the system SHALL expose it on `catalog.get(name).schema_version`.
4. WHEN the CLI command `pychestrate-admin protocols list` is invoked
   THEN the system SHALL emit a sorted list of `(name, schema_version,
   owning_feature, reference_impl_qualname)` rows.

### Requirement 2: Contract-enforcing declaration template

**User Story:** As a feature author, I want a consistent template for
declaring a new factory protocol — classmethod signatures, docstring
contract, and a reference implementation stub — so that new protocols land
with uniform shape and pass the linter on first PR.

**Acceptance Criteria (EARS):**

1. WHEN a new protocol module is added THEN the system SHALL verify it
   declares `factory_protocol_name: str`, `FACTORY_PROTOCOL_SCHEMA_VERSION:
   int`, a module-level Sphinx contract block, and at least one
   classmethod annotated with an explicit return type.
2. IF a protocol declaration omits any of the required fields THEN the
   catalog registration SHALL raise `ConfigurationError` with the list of
   missing fields and block service startup.
3. WHEN a protocol's reference implementation is missing from
   `source/site/ccai/factories/pychestrate/_reference/` THEN the
   system SHALL emit a `pychestrate_extension_reference_missing` warning
   during bootstrap.

### Requirement 3: Host-integrated lookup surface

**User Story:** As a feature consumer, I want to resolve a protocol by its
Python class and classmethod, so that callsites stay type-checked rather
than using magic strings.

**Acceptance Criteria (EARS):**

1. WHEN `FactoryProtocolCatalog.resolve(protocol_cls=X)` is called
   THEN the system SHALL return a thin proxy exposing `create_instance`,
   `create_instance_for_each`, `get_override_type`, and
   `iterate_override_types` bound to the host lookup chain.
2. IF the caller's `protocol_cls` is not present in the catalog THEN the
   system SHALL raise `SemanticError` naming the class (never caught).
3. WHILE the host is bootstrapping the system SHALL queue catalog lookups
   until bootstrap completes rather than returning partial results.

### Requirement 4: Schema version gating

**User Story:** As a service operator, I want an extension whose implemented
protocol schema version is older than what the running service declares to
fail loading with a clear message, so that silent `AttributeError`s never
appear at call time.

**Acceptance Criteria (EARS):**

1. WHEN a `FactoryExtension` sets `FACTORY_PROTOCOL_SCHEMA_VERSION_IMPLEMENTED`
   lower than the catalog's declared version for that protocol THEN the
   system SHALL refuse to register the factory and emit
   `extension.load_failed` with reason `schema_version_too_old`.
2. IF the extension sets a version strictly higher than the catalog's
   version THEN the system SHALL log a
   `pychestrate_extension_protocol_schema_ahead` warning but still load
   (forward-compatible).
3. WHERE the extension omits the attribute THEN the system SHALL treat it
   as version `0` and fail-closed only when the catalog's version is
   non-zero.

## Property-Based Test Requirements

### Property 1: Catalog uniqueness

- **Invariant:** For any set of `N` declared protocol classes, catalog
  registration succeeds if-and-only-if every `factory_protocol_name` is
  unique; duplicates always raise `ConfigurationError`.
- **Generator:** `hypothesis.strategies.lists(protocol_name_strategy,
  min_size=1, max_size=64)` with a biased duplicate injector.
- **Assertion:** For every generated list, `catalog.register_all(classes)`
  either fully succeeds on a unique-name list or raises `ConfigurationError`
  on a list with any duplicate — no partial registration.
- **Sample size:** 1000 generated cases.

### Property 2: Schema-version monotone fail-closed

- **Invariant:** For any pair `(catalog_version, impl_version)` with
  `impl_version < catalog_version`, factory registration fails closed;
  for `impl_version >= catalog_version`, registration succeeds.
- **Generator:** `hypothesis.strategies.tuples(integers(min_value=0,
  max_value=64), integers(min_value=0, max_value=64))`.
- **Assertion:** Registration outcome matches the comparison; no
  mid-state where the factory is partially registered.
- **Sample size:** 1000 generated cases.

### Property 3: Resolve-proxy idempotence

- **Invariant:** For any protocol class `X`,
  `catalog.resolve(protocol_cls=X)` returns proxies that produce identical
  results on repeated calls against an unchanged host snapshot.
- **Generator:** any valid catalog + any valid host snapshot.
- **Assertion:** `proxy.get_override_type() == proxy.get_override_type()`
  across `N in range(2, 50)` invocations.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Catalog registration and resolve lookups are
  `O(1)` per call; full catalog snapshot serialization for the CLI must
  complete in under 50 ms for up to 500 protocols.
- **NFR-2 (Security):** Catalog is read-only after bootstrap; mutation
  helpers are gated by the `extensions.manage_catalog` permission and
  exist only for the live rescan flow in `E-extension-host`.
- **NFR-3 (Observability):** Emits
  `pychestrate_extension_protocol_registered_total{protocol,schema_version}`
  and `pychestrate_extension_protocol_lookup_total{protocol,result}`; log
  events `pychestrate_extension_protocol_registered`,
  `pychestrate_extension_protocol_schema_ahead`; trace span
  `pychestrate_extension.protocol_catalog.resolve`.
- **NFR-4 (Reliability):** Fail-closed on duplicate protocol names and
  schema-version-below-catalog; downgrade-forward-compatible on
  schema-ahead.

## Out of Scope

- Resource kind catalogs (`E-resource-extensions`).
- Lifecycle hooks (`E-extension-lifecycle`).
- Capability gating per protocol (`E-extension-sandbox`).
- External-stable protocol subset (`E-plugin-api`).

## Dependencies

- **Depends on:** `E-extension-host`.
- **Depended on by:** every feature that declares a `factory:` extension
  surface (per implementation-plan.md): `0-object-store`,
  `0-timeseries-backend`, `1-authentication`, `1-secrets-vault`,
  `1-audit-log`, `1-feature-flags`, `2-global-variables`,
  `2-notification-hub`, `2-retention-policies`, `3-*`, `4-*`, `5-*`,
  `6-*`, `7-metrics-ingest`, `10-observability`, `10-release-channels`.
- **Extension points exposed:** this feature *defines the declaration
  surface* used by every `factory:` extension point downstream; it is the
  catalog, not an instance.
