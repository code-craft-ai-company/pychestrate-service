# E-extension-docs — Tasks

## Milestones

- **M1 — Skeleton:** Sphinx extension loads; `CatalogWalker` emits
  one stub page per declared protocol; toctree includes the generated
  tree.
- **M2 — Core Behavior:** Full protocol and resource pages with
  signatures, schema version, capability links, reference embed,
  compat table; stability filter via build flag.
- **M3 — Hardening:** Fail-closed on broken refs + missing
  references, metrics/log emission, linkcheck integration, release-
  channel publishing hook.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Create Sphinx root `docs/` with `conf.py`,
  `index.rst`, and the `extensions/` subfolder.
  *(``docs/conf.py`` registers the in-tree extension, prepends
  the repo ``source/site`` and ``source/packages`` paths so
  Sphinx imports resolve, and uses ``alabaster``. ``docs/index.rst``
  carries a top-level toctree pointing at the generated category
  indexes. ``docs/Makefile`` provides ``html`` + ``clean`` targets.)*
- [x] T1.2 — Create
  `source/site/automojo/pychestrate/webservice/extension/docs_ext/`
  with a `setup(app)` entry point.
  *(Subsystem rooted at ``extension.docs_ext`` with ``models``,
  ``catalog_walker`` modules and a ``templates/`` directory.
  ``setup(app)`` returns the documented metadata mapping and
  hooks ``builder-inited`` so pages render before Sphinx scans
  the source tree.)*
- [x] T1.3 — Implement a minimal `CatalogWalker.emit_protocol_pages`
  that emits one stub page per entry.
  *(``CatalogWalker`` accepts a :class:`Catalog` snapshot or
  loads one via ``plugin_api.runtime.get_active_catalog``;
  ``emit_protocol_pages`` writes ``<out>/protocols/<name>.rst``,
  ``emit_resource_pages`` writes ``<out>/resources/<name>.rst``,
  and ``emit_indexes`` writes per-category ``index.rst`` toctree
  files. ``emit_all`` does the union pass.)*
- [x] T1.4 — Wire the extension into `conf.py`; add a
  `make -C docs html` target invocation from the repo Makefile.
  *(Repo Makefile gains ``docs-html`` / ``docs-clean`` targets
  delegating to ``docs/Makefile``. ``conf.py``'s ``extensions``
  list registers ``automojo.pychestrate.webservice.extension.docs_ext``.)*

### M2 — Core Behavior

- [ ] T2.1 — Implement the full protocol Jinja template including
  signatures, schema version, capabilities, stability stamp,
  deprecation block, and reference embed via `literalinclude`.
- [ ] T2.2 — Implement the resource Jinja template with
  attribute schema table and in-tree reference kind link.
- [ ] T2.3 — Implement `emit_compat_table` comparing declared schema
  versions to reference implementations.
- [ ] T2.4 — Add build flag `PYCHESTRATE_DOCS_STABILITY` filtering
  published vs all.
- [ ] T2.5 — Wire `linkcheck -W` into the build target so broken
  links fail the build.

### M3 — Hardening

- [ ] T3.1 — Implement temp-dir + rename atomic output.
- [ ] T3.2 — Emit metrics and log events per design.md.
- [ ] T3.3 — Publish hook into `10-release-channels` artifact store.
- [ ] T3.4 — Add fail-closed error on missing reference file;
  message includes both the missing path and the requesting
  protocol.
- [ ] T3.5 — Remove all TODO/FIXME; pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS requirement, including the
  missing-reference and stability-filter paths.
- [ ] TT-2 — Property-based tests for Property 1 (coverage), 2
  (link integrity), 3 (stability filter closure) at 1000 cases
  each.
- [ ] TT-3 — Integration test: add a fake published protocol +
  reference, run the build, confirm the page exists, the
  `Published only` toggle includes it, and linkcheck passes.
- [ ] TT-4 — Extension-point test: declare a new in-tree protocol
  without a reference implementation; build fails closed with the
  expected error message.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Docs build is green in service CI.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 10 exit criterion in
      specs/implementation-plan.md.
