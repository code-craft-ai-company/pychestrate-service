# E-extension-compat-check — Tasks

## Milestones

- **M1 — Skeleton:** `CompatChecker` class exists with
  `check_manifest_window` and `check_factory_schema` returning
  rejections (or None); wired after manifest parse and after host
  load.
- **M2 — Core Behavior:** Full decision matrix (below/at/ahead/
  missing), rejection persistence in `ManifestRegistry`, CLI / REST
  diagnostic surface, fleet report.
- **M3 — Hardening:** Metrics/logs/traces, deprecation-window
  flagging, Sphinx docs for the schema-version discipline.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/ccai/pychestrate/webservice/extension/compat/`.
- [ ] T1.2 — Implement `CompatRejection` dataclass.
- [ ] T1.3 — Implement `CompatChecker.check_manifest_window` against
  a `packaging.version.Version` running service version.
- [ ] T1.4 — Wire window check after `parse_manifest` and record
  rejections in `ManifestRegistry`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `check_factory_schema` with the full
  decision matrix.
- [ ] T2.2 — Wire factory-schema checks into the host's post-import
  step so rejected factories never register.
- [ ] T2.3 — Emit `extension.compat_rejected` and
  `extension.compat_schema_ahead` bus events.
- [ ] T2.4 — Implement `generate_report` computing per-protocol
  counters across loaded factories.
- [ ] T2.5 — Add `pychestrate-admin compat check|report` CLI
  subcommands.
- [ ] T2.6 — Add `GET /admin/extensions/{name}/compat` and
  `GET /admin/extensions/compat/report` REST routes.

### M3 — Hardening

- [ ] T3.1 — Emit metrics and log events per design.md Observability.
- [ ] T3.2 — Add "candidate for next bump drop" flag in the report
  for the oldest-still-valid impl version per protocol.
- [ ] T3.3 — Integrate with `E-extension-registry-ui` to surface
  per-ext compat status.
- [ ] T3.4 — Sphinx docs for the schema-version discipline in
  `E-extension-docs`.
- [ ] T3.5 — Negative test harness: synthetic pack with impl version
  below catalog triggers rejection with the correct metric + event.
- [ ] T3.6 — Remove all TODO/FIXME; pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement, including
  pre-release ordering cases (`2.0.0rc1` vs `1.9.0`).
- [ ] TT-2 — Property-based tests for Property 1 (window
  fail-closed), 2 (schema monotonicity), 3 (diagnostic faithfulness)
  at 1000 cases each.
- [ ] TT-3 — Integration test: running service at `1.5.0`, three
  packs declaring windows `[1.0.0, 2.0.0)`, `[1.7.0, 2.0.0)`,
  `[1.0.0, 1.3.0)`; expect load, reject, reject with specific
  reasons; diagnostic endpoint matches.
- [ ] TT-4 — Extension-point test: out-of-tree
  `pychestrate-ext-sample-compat` runs three impl-version scenarios
  (below/at/ahead); outcomes match requirements; CLI report reflects
  counts.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Reference in-tree extension declares the schema-version
      attribute; a test-only override at a different version
      demonstrates the accept/reject matrix.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for schema version discipline.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 0.5 exit criterion in
      specs/implementation-plan.md.
