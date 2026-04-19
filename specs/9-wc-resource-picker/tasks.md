# 9-wc-resource-picker — Tasks

## Milestones

- **M1 — Skeleton:** `<pyc-resource-picker>` registered, fetches pool summary + first page, renders a single-select list themed via tokens.
- **M2 — Core Behavior:** Filters (capabilities/tags/search/include-unhealthy), pagination, multi-select + min/max constraints, live availability stream, stale detection, confirm payload.
- **M3 — Hardening:** Property tests, metrics, accessibility, virtualisation above 500 rows, polling fallback, Sphinx docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/automojo/pychestrate/webservice/webinterface/components/pyc-resource-picker/` with TypeScript build wiring.
- [ ] T1.2 — Implement `pyc-resource-picker.ts::PycResourcePicker` Custom Element with observed attributes `pool-id`, `capabilities`, `tags`, `include-unhealthy`, `multiple`, `min-select`, `max-select`, `autofocus-search`, `aria-label`.
- [ ] T1.3 — Implement `transport/resource-transport.ts` fetching `/api/v1/pools/{pool_id}/summary.json` and `/resources`.
- [ ] T1.4 — Implement `selection-model.ts` single-select mode with `toggle`, `replace`, `clear`, `fingerprint`.
- [ ] T1.5 — Author `styles.css` referencing `--pyc-resource-picker-*` tokens, multi-line per AGENTS.md.
- [ ] T1.6 — Emit `pyc-resource-picker-loaded` and `pyc-resource-picker-selection-changed`.
- [ ] T1.7 — Serve bundle at `/ui/components/pyc-resource-picker/pyc-resource-picker.js`.

### M2 — Core Behavior

- [ ] T2.1 — Implement filter state with 200 ms debounced search re-query.
- [ ] T2.2 — Implement cursor-based pagination with `Intersection Observer` load-more.
- [ ] T2.3 — Implement multi-select mode with `min-select`/`max-select` constraints and `pyc-resource-picker-selection-invalid` emission.
- [ ] T2.4 — Implement `availability-tracker.ts` and SSE subscription against `/api/v1/pools/{pool_id}/availability.stream`.
- [ ] T2.5 — Implement stale detection and `pyc-resource-picker-stale` emission.
- [ ] T2.6 — Implement `confirm()` flow emitting `pyc-resource-picker-confirm` or `-confirm-blocked`.
- [ ] T2.7 — Implement keyboard handler (ArrowUp/Down, Space/Enter, Home/End, Esc, /, Ctrl+A, Ctrl+D).
- [ ] T2.8 — Surface `slot="header"`, `slot="summary"`, `slot="pool-unavailable"`, `slot="confirm-action"`.
- [ ] T2.9 — Render visually-hidden live region for stale and selection-count announcements.

### M3 — Hardening

- [ ] T3.1 — Beacon client metrics per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: TTI p95 < 220 ms, search re-query p95 < 300 ms, availability apply p95 < 5 ms, 60 fps scroll through 2 000 rows. Fail CI on regression.
- [ ] T3.3 — Axe audit: `role="listbox"`, `role="option"`, `aria-multiselectable`, focus ring; fail CI on violations.
- [ ] T3.4 — Implement `virtual-list.ts` virtualisation above 500 rows.
- [ ] T3.5 — Polling fallback every 5 s when SSE disconnects; reconnect when available.
- [ ] T3.6 — Enforce `selection-hard-cap` (default 1 000) regardless of `max-select`.
- [ ] T3.7 — Sphinx authoring doc: tag contract, attributes, properties, events, slots, tokens, a11y, host-page patterns.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (monotone selection), Property 2 (sound stale detection), Property 3 (idempotent re-render) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 8 scenario — pick 3 resources from the `rf-lab` pool matching `vector-sig-gen`; stream an availability event marking one reserved; element surfaces stale and blocks confirm.
- [ ] TT-4 — Browser E2E (Playwright-style): open a dispatch dialog hosting the picker; type a search, verify debounce, select 2 items, press confirm and assert the payload event fires with the expected `selectionFingerprint`.
- [ ] TT-5 — Multi-select keyboard test: Ctrl+A selects all visible (multi mode), Ctrl+D clears, Space toggles, ArrowDown moves focus.
- [ ] TT-6 — Security test: `search` input with 10 KiB of text is truncated to 128 characters before dispatch; no request URL exceeds the configured URL limit.
- [ ] TT-7 — Polling-fallback test: disconnect SSE, confirm the element polls availability every 5 s and clears stale markers on reconnect.

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
