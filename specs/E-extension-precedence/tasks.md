# E-extension-precedence — Tasks

## Milestones

- **M1 — Skeleton:** `PrecedenceOverrideTable` exists; `apply_precedence`
  produces a deterministic sort using declared values only.
- **M2 — Core Behavior:** Site pin file loaded, applied, re-applied on
  rescan; reserved bands enforced via manifest capability; CLI
  subcommands.
- **M3 — Hardening:** Metrics/logs/traces, diff events, snapshot
  digest includes effective values, Sphinx docs, stress tests.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/automojo/pychestrate/webservice/extension/precedence/`.
- [ ] T1.2 — Implement `PrecedencePin` and `PrecedenceOverrideTable` in
  `table.py`.
- [ ] T1.3 — Implement `apply_precedence(factory_classes=, table=,
  manifests=)` producing a sorted tuple keyed by
  `(effective_precedence, qualname)`.
- [ ] T1.4 — Wire the precedence layer into `E-extension-host`'s
  post-load chain construction.

### M2 — Core Behavior

- [ ] T2.1 — Implement `load_from_file(path=...)` using
  `yaml.safe_load` and schema-v1 validation.
- [ ] T2.2 — Resolve file path precedence:
  `PYCHESTRATE_PRECEDENCE_FILE` → `/etc/pychestrate/extension_precedence.yaml`
  → absent.
- [ ] T2.3 — Implement duplicate-qualname fail-closed with multiline
  error.
- [ ] T2.4 — Implement band enforcement in `bands.py`: raise
  `ConfigurationError` when a reserved-band value is applied without
  the manifest capability.
- [ ] T2.5 — Implement `PrecedenceOverrideTable.diff` for change-event
  generation.
- [ ] T2.6 — Subscribe to `extension.rescan_completed`; reload and
  emit `extension.precedence_override_changed` on diff.
- [ ] T2.7 — Add `pychestrate-admin precedence show|validate` CLI
  subcommands.
- [ ] T2.8 — Add `GET /admin/extensions/precedence` REST route.

### M3 — Hardening

- [ ] T3.1 — Ensure `ExtensionHost.snapshot_digest` includes effective
  PRECEDENCE values; add a regression test for node-to-node equality.
- [ ] T3.2 — Emit all metrics, log events, trace spans per design.md.
- [ ] T3.3 — Emit `extension.precedence_pin_unresolved` warnings for
  pin entries that do not match a loaded class.
- [ ] T3.4 — Generate Sphinx docs for pin-file schema and priority
  bands; wire into `E-extension-docs`.
- [ ] T3.5 — Add a stress test exercising 500 factories and 100 pins
  to confirm NFR-1 performance target.
- [ ] T3.6 — Remove all TODO/FIXME; pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS requirement including the
  duplicate-pin, unresolved-pin, and reserved-band paths.
- [ ] TT-2 — Property-based tests for Property 1 (determinism), 2
  (monotonicity), 3 (unresolved no-op) at 1000 cases each.
- [ ] TT-3 — Integration test: two services with identical packs +
  identical pin files produce equal `snapshot_digest`; a pin-file edit
  propagates on rescan.
- [ ] TT-4 — Extension-point test: out-of-tree
  `pychestrate-ext-sample-precedence` ships with a default PRECEDENCE
  of 1500; a pin file re-pins it to 120; the winning resolution
  changes accordingly.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Extension surface has a reference factory chain demonstrating
      upper, middle, and lower bands; a test-only override pin shifts
      the winner.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for pin-file schema and bands.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 0.5 exit criterion in
      specs/implementation-plan.md.
