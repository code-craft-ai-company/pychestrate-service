# E-extension-pack-template — Tasks

## Milestones

- **M1 — Skeleton:** `PackGenerator` renders a minimal v1 corpus into
  a target dir; CLI `new` subcommand present.
- **M2 — Core Behavior:** Full v1 corpus including manifest,
  sample factory, sample resource, contract tests, CI workflow;
  `upgrade` subcommand with diff; name normalization.
- **M3 — Hardening:** Atomic write, metrics/logs, Sphinx docs,
  corpus regression tests executed in service CI.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Create the package tree under
  `source/site/ccai/pychestrate/webservice/extension/pack_template/`.
  *(Subsystem rooted at ``extension.pack_template`` with ``models``,
  ``corpus_loader``, ``generator``, ``cli`` modules; corpus is
  vendored under ``corpus/v1/`` so service CI exercises it.)*
- [x] T1.2 — Implement `PackGenerationRequest`,
  `PackTemplateManifest`, `PackTemplateFile` dataclasses.
  *(Frozen dataclasses live in
  ``extension.pack_template.models``; ``COPY_RENDER_MODE`` /
  ``JINJA_RENDER_MODE`` constants document the supported modes.)*
- [x] T1.3 — Implement `PackGenerator.generate` rendering a minimal
  v1 corpus using Jinja2.
  *(``StrictUndefined`` Jinja env, ``__NAME__`` placeholder
  substitution in destination paths, refuses to overwrite a
  non-empty pack root, rejects unknown ``template_version``.)*
- [x] T1.4 — Implement `pychestrate-admin pack-template new` CLI.
  *(``cli.main`` argparse-driven; ``pychestrate.admin.__main__``
  routes ``pychestrate-admin <subsystem> …`` to the pack-template
  CLI; ``new`` and ``list-versions`` subcommands ship.)*
- [x] T1.5 — Implement `normalize_pack_name` with idempotence.
  *(NFKD-decompose → ASCII strip → non-alnum → ``-`` collapse →
  trim; prefixes ``ext-`` when the first character is not
  ``[a-z]``; ``SemanticError`` on empty result.)*

### M2 — Core Behavior

- [ ] T2.1 — Fill out corpus v1 with every file listed in design.md.
- [ ] T2.2 — Implement `upgrade` command with per-file diff
  computation.
- [ ] T2.3 — Implement `_meta.yaml` baseline tracking inside
  generated packs.
- [ ] T2.4 — Implement `--apply` writeback preserving user
  modifications via a conflict table.
- [ ] T2.5 — Generate a contract test under
  `tests/contract/test_layer_e.py.jinja` using the service's test
  harness fixture (published by `E-plugin-api`).
- [ ] T2.6 — Pin CI workflow GitHub Action versions to SHAs in the
  generated `.github/workflows/ci.yaml`.

### M3 — Hardening

- [ ] T3.1 — Make generation atomic: temp dir + rename.
- [ ] T3.2 — Emit metrics and log events per design.md.
- [ ] T3.3 — Add service-CI regression test that generates a pack,
  installs it into the service test harness, and asserts zero
  Layer E failure events.
- [ ] T3.4 — Sphinx docs on how to author a pack; wire into
  `E-extension-docs`.
- [ ] T3.5 — Remove all TODO/FIXME; pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS requirement, including
  refuse-on-existing-dir and name validation.
- [ ] TT-2 — Property-based tests for Property 1 (name
  normalization), 2 (regenerate no-drift), 3 (Layer E gate
  satisfaction) at 1000 cases each.
- [ ] TT-3 — Integration test: generate, install, load, re-generate
  with `upgrade --apply`, confirm zero drift; then modify one user
  file and confirm conflict detection.
- [ ] TT-4 — Extension-point test: generate a pack seeded with a
  real catalog protocol; load into the service; confirm the
  generated factory appears in `list_factory_protocols()`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Generated pack passes the service's own lint + type checks
      and `pychestrate-admin manifest validate`.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs published for `pack-template new|upgrade`.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 10 exit criterion in
      specs/implementation-plan.md.
