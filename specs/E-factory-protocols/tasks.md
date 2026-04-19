# E-factory-protocols — Tasks

## Milestones

- **M1 — Skeleton:** `FactoryProtocolCatalog` exists, a single declared
  protocol registers at import time, and `ProtocolProxy.create_instance`
  returns `None` when no factory is loaded. Proves the wiring with the
  host.
- **M2 — Core Behavior:** Full declaration template linter, batch
  registration of every Phase 0.5 / Phase 1 protocol, duplicate-name and
  unknown-protocol fail-closed, catalog CLI subcommands, REST read
  surface.
- **M3 — Hardening:** Schema-version gating with forward-compatible
  warnings, Sphinx docs generation per protocol, integration with
  `E-extension-registry-ui`, and stability tagging for `E-plugin-api`.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/automojo/pychestrate/webservice/extension/protocols/`.
- [ ] T1.2 — Implement `FactoryProtocolCatalogEntry` dataclass in
  `entry.py`.
- [ ] T1.3 — Implement `FactoryProtocolCatalog` in `catalog.py` with
  `register`, `get`, `list_entries`; duplicate check raises
  `ConfigurationError`.
- [ ] T1.4 — Implement `get_factory_protocol_catalog()` singleton
  accessor.
- [ ] T1.5 — Add a single sample declaration
  `_declarations/object_store_driver.py` and register it at bootstrap.
- [ ] T1.6 — Implement `ProtocolProxy` with `create_instance` delegating
  to the host.

### M2 — Core Behavior

- [ ] T2.1 — Implement `register_from_module` scanning
  `_declarations/` and registering every `FactoryProtocolBase` subclass.
- [ ] T2.2 — Implement the declaration-template linter in `lint.py` and
  wire it into CI via `make lint`.
- [ ] T2.3 — Populate `_declarations/` with a stub per Phase 0.5 /
  Phase 1 protocol (`object_store_driver`, `timeseries_driver`,
  `auth_provider`, `secrets_backend`, `audit_sink`, `feature_flag_backend`,
  `variable_resolver`, `secret_ref_dereferencer`,
  `notification_channel`, `user_directory_source`).
- [ ] T2.4 — Implement `ProtocolProxy.create_instance_for_each`,
  `get_override_type`, `iterate_override_types`.
- [ ] T2.5 — Add `pychestrate-admin protocols list|show|check` CLI
  subcommands.
- [ ] T2.6 — Add `GET /admin/extensions/protocols` REST route with
  permission `extensions.read`.
- [ ] T2.7 — Subscribe to `extension.loaded` and validate each loaded
  factory's `factory_protocol_name` exists in the catalog; fail closed
  on unknown protocol in strict mode.

### M3 — Hardening

- [ ] T3.1 — Implement schema-version gating: refuse registration for
  `impl_version < catalog_version`; warn for ahead.
- [ ] T3.2 — Emit metrics and log events per design.md Observability.
- [ ] T3.3 — Emit `extension.protocol_registered` and
  `extension.protocol_schema_ahead` bus events.
- [ ] T3.4 — Generate Sphinx docs per protocol from the module-level
  docstring and classmethod signatures; wire into `E-extension-docs`.
- [ ] T3.5 — Tag every catalog entry with `stability`; ensure only
  `"published"` entries appear in `E-plugin-api`'s export.
- [ ] T3.6 — Wire catalog listing into `E-extension-registry-ui`'s admin
  page data source.
- [ ] T3.7 — Remove all TODO/FIXME and pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS requirement in
  requirements.md, including the four schema-version paths (equal,
  below, above, missing).
- [ ] TT-2 — Property-based tests implementing Property 1, 2, 3 at 1000
  cases each.
- [ ] TT-3 — Integration test: service boots with the full Phase 0.5
  protocol set, catalog list returns the expected names, and a
  deliberately-broken duplicate declaration aborts startup with a
  readable multiline error.
- [ ] TT-4 — Extension-point test: an out-of-tree
  `pychestrate-ext-sample-proto` package declares a new published
  protocol, it registers in the catalog, a second pack with a matching
  `FactoryExtension` is picked up by a resolve call, and a schema-bump
  override pack demonstrates forward-compatible load.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Every Phase 0.5/Phase 1 `factory:` surface listed in
      implementation-plan.md has a matching declaration in
      `_declarations/` with a reference implementation under
      `_reference/` (PRECEDENCE = 1000).
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for every declared protocol.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 0.5 exit criterion in
      specs/implementation-plan.md.
