# 9-ui-design-tokens — Tasks

## Milestones

- **M1 — Skeleton:** Canonical token manifest + `DesignTokenPackExtension` base + in-tree default light pack served at `/ui/design-tokens/active.css`.
- **M2 — Core Behavior:** Dark pack, cascade composition with `inherits_from`, `extension.reloaded` rebuild, admin-facing `packs.json`, multi-line CSS validator, `pyc-theme.js` helper.
- **M3 — Hardening:** Property tests, metrics/logs/traces, gzipping + ETag correctness, minified variant, quarantine on bad packs, Sphinx docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the `source/site/ccai/pychestrate/webservice/webinterface/design_tokens/` package per design.md Component Breakdown.
- [ ] T1.2 — Author `manifest.py` declaring the canonical `--pyc-*` namespace (color, space, font, radius, elevation, motion, focus).
- [ ] T1.3 — Implement `pack_protocol.py::DesignTokenPackExtension` base with `pack_id`, `inherits_from`, `PRECEDENCE`, `css_source_path`, `load_css`.
- [ ] T1.4 — Write `components/design_tokens/styles/pychestrate.default.light.css` in full multi-line form per AGENTS.md CSS convention.
- [ ] T1.5 — Implement `registry.py::DesignTokenRegistry.register_pack` + `resolve_cascade` + `rebuild_all`.
- [ ] T1.6 — Implement `dispatcher.py::DesignTokenDispatcher.serve_active` and mount `GET /ui/design-tokens/active.css`.
- [ ] T1.7 — Mount `GET /ui/design-tokens/packs.json` and `GET /ui/design-tokens/manifest.json`.

### M2 — Core Behavior

- [ ] T2.1 — Write `components/design_tokens/styles/pychestrate.default.dark.css` inheriting from the light pack, including `:root[data-pyc-theme="dark"]` overrides.
- [ ] T2.2 — Implement `cascade.py` composing base pack + `inherits_from` chain + selected pack in `PRECEDENCE` order.
- [ ] T2.3 — Implement `validator.py` rejecting minified source and any token not declared in the manifest.
- [ ] T2.4 — Subscribe to `extension.reloaded` and call `rebuild_all` atomically without dropping in-flight requests.
- [ ] T2.5 — Ship `components/design_tokens/pyc-theme.js` toggling `data-pyc-theme` on the document element and persisting selection in `pyc_token_pack` / `pyc_theme` cookies.
- [ ] T2.6 — Implement cookie-driven pack selection in `serve_active`, falling back to `pychestrate.default.light` on unknown values.
- [ ] T2.7 — Ship the test-only `PychestrateExampleTenantPack` reference extension to exercise precedence.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics (`pychestrate_ui_design_tokens_*`) and OTel spans per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: serve p99 < 5 ms, cascade rebuild < 200 ms across 16 packs, default pack gzipped < 12 KiB. Fail CI on regression.
- [ ] T3.3 — Serve gzipped payload and correct ETag; support `If-None-Match` revalidation.
- [ ] T3.4 — Serve `?min=1` minified variant from a separate cache key; canonical URL never serves minified bytes.
- [ ] T3.5 — Quarantine packs that fail `load_css` or `validator`; emit `pychestrate.ui.design_tokens.pack_missing` and keep serving last-good cascade.
- [ ] T3.6 — Reject `@import` to remote origins; only allow `@import` to registered local `pack_id`s.
- [ ] T3.7 — Sphinx docs for the token namespace, `DesignTokenPackExtension` authoring guide, and the `/ui/design-tokens/*` static surface.
- [ ] T3.8 — Verify multiline error messages use `os.linesep.join([...])` per AGENTS.md.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (idempotent token resolution), Property 2 (stable cascade ordering under PRECEDENCE permutation), and Property 3 (every manifest token has a default value) at 1000 cases each.
- [ ] TT-3 — Integration test: register three packs (default light, default dark, example tenant); switch active pack via cookie; assert served CSS is the expected concatenation.
- [ ] TT-4 — Extension-point test: load an out-of-tree `AcmeTenantPack` with `PRECEDENCE=200`; assert its declarations override the default light pack in the composed cascade.
- [ ] TT-5 — Browser E2E (Playwright-style): load a page that links `/ui/design-tokens/active.css`, verify `getComputedStyle(document.documentElement).getPropertyValue("--pyc-color-surface")` matches the active pack; toggle `pyc-theme.js` and verify the value flips to the dark equivalent without reload.
- [ ] TT-6 — Shadow-DOM resolution test: instantiate a minimal custom element with a shadow root; assert `var(--pyc-color-surface)` resolves inside the shadow root.
- [ ] TT-7 — Reload-safety test: issue 500 concurrent `GET /ui/design-tokens/active.css` while publishing `extension.reloaded`; zero 5xx responses.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
