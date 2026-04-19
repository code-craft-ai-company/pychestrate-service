# E-plugin-api — Tasks

## Milestones

- **M1 — Skeleton:** `pychestrate.plugin.v1` package exists with a
  small seed re-export set; `PluginApiCurator.compute_export_set`
  returns the seed; `__getattr__` routes unknown → AttributeError.
- **M2 — Core Behavior:** Deprecation metadata support; stability
  review corpus; CI audit job; `FakeService` test fixture; full
  published export set.
- **M3 — Hardening:** Strict-mode enforcement, metrics/logs,
  Sphinx docs integration, parity tests between fixture and real
  service.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/automojo/pychestrate/plugin/v1/` and
  `source/site/automojo/pychestrate/webservice/extension/plugin_api/`.
- [ ] T1.2 — Implement `Deprecation` dataclass and
  `PluginApiCurator.compute_export_set` by walking the catalogs.
- [ ] T1.3 — Implement `__getattr__` in `plugin/v1/__init__.py` for
  unknown-symbol AttributeError.
- [ ] T1.4 — Seed `__all__` with `FactoryProtocolBase`,
  `ResourceExtension`, `ExtensionManifest`,
  `CAPABILITY_VOCABULARY`, `subscribes_to`, `HookAspects`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `audit_reviews` walking
  `docs/extensions/_stability_reviews/` and flagging missing/stale
  entries.
- [ ] T2.2 — Implement `audit_deprecations` reading
  `docs/extensions/_deprecations/v1.yaml` and flagging overdue
  entries.
- [ ] T2.3 — Implement `regenerate_module` producing the `__all__`
  tuple from the curated set; CI drift check against the checked-in
  file.
- [ ] T2.4 — Implement `FakeService` and `service_fixture` pytest
  fixture under
  `pychestrate/plugin/v1/testing/`.
- [ ] T2.5 — Add `DeprecationWarning` emission in `__getattr__`
  using the deprecation records.
- [ ] T2.6 — Add the CI audit job invocation
  (`pychestrate-admin plugin-api audit`) to the service CI pipeline.

### M3 — Hardening

- [ ] T3.1 — Implement strict-mode overdue-deprecation failure
  behind `--strict-plugin-api`.
- [ ] T3.2 — Emit metrics and log events per design.md.
- [ ] T3.3 — Add trace span around `__getattr__`.
- [ ] T3.4 — Generate Sphinx docs for the published surface (reuse
  `E-extension-docs` with `stability=published`).
- [ ] T3.5 — Add end-to-end parity test: install a known pack
  against the real service and the fixture; assert equal outcomes.
- [ ] T3.6 — Remove all TODO/FIXME; pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement including
  unknown-symbol AttributeError and strict-mode overdue fail.
- [ ] TT-2 — Property-based tests for Property 1 (subset closure),
  2 (deprecation-metadata completeness), 3 (fixture parity) at
  1000 cases each.
- [ ] TT-3 — Integration test: external-style repo uses
  `pychestrate.plugin.v1` to implement a factory; installs via
  fixture; confirms registration + call-through.
- [ ] TT-4 — Extension-point test: a deprecated symbol import
  emits `DeprecationWarning` once per process; an unknown symbol
  raises `AttributeError`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Every published symbol has a current stability review file.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs published for the v1 surface.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 10 exit criterion in
      specs/implementation-plan.md.
