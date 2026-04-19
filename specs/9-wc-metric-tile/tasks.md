# 9-wc-metric-tile — Tasks

## Milestones

- **M1 — Skeleton:** `<pyc-metric-tile>` registered with `kind="number"`, queries `/api/v1/metrics/query`, refreshes on cadence, themed via tokens.
- **M2 — Core Behavior:** Built-in kinds (sparkline, gauge, histogram), thresholds, formatters, extension kind dispatch, drilldown, refresh backoff.
- **M3 — Hardening:** Property tests, client metrics, a11y, extension quarantine, benchmarks, Sphinx docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/automojo/pychestrate/webservice/webinterface/components/pyc-metric-tile/` with TypeScript build wiring.
- [ ] T1.2 — Implement `pyc-metric-tile.ts::PycMetricTile` Custom Element with observed attributes `kind`, `query`, `range`, `step`, `unit`, `title`, `subtitle`, `refresh-seconds`, `thresholds`, `announce-refresh`, `aria-label`.
- [ ] T1.3 — Implement `transport/tile-transport.ts` against `/api/v1/metrics/query`.
- [ ] T1.4 — Implement built-in `<pyc-metric-tile-number>` inner child.
- [ ] T1.5 — Author `styles.css` referencing `--pyc-metric-tile-*` tokens, multi-line per AGENTS.md.
- [ ] T1.6 — Implement `refresh-scheduler.ts` with `refresh-seconds` cadence and tab-backgrounded throttling.
- [ ] T1.7 — Serve bundle at `/ui/components/pyc-metric-tile/pyc-metric-tile.js`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `value-formatter.ts` with SI-aware formatting per unit.
- [ ] T2.2 — Implement `threshold-evaluator.ts` with ordinal states `ok < warn < crit`.
- [ ] T2.3 — Implement built-in `<pyc-metric-tile-sparkline>` (64x24 SVG).
- [ ] T2.4 — Implement built-in `<pyc-metric-tile-gauge>` with threshold-colored arc.
- [ ] T2.5 — Implement built-in `<pyc-metric-tile-histogram>` rendering quantile lines.
- [ ] T2.6 — Implement `tile-kind-registry.ts` resolving built-ins + `/api/v1/extensions/dashboard_tile_kinds.json`.
- [ ] T2.7 — Implement dynamic `import()` with caching for extension bundles.
- [ ] T2.8 — Implement drilldown affordance for `supports-drilldown: true` kinds; emit `pyc-metric-tile-drilldown`.
- [ ] T2.9 — Implement 5-consecutive-failure backoff with retry affordance.
- [ ] T2.10 — Surface `slot="header-right"`, `slot="footer"`, `slot="error"`, `slot="extra"`.

### M3 — Hardening

- [ ] T3.1 — Beacon client metrics per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: TTI p95 < 200 ms cache hit, first refresh p95 < 500 ms, 20-tile dashboard sustains 60 fps. Fail CI on regression.
- [ ] T3.3 — Axe audit: `role="region"`, accessible name updated on refresh, focus ring honored; fail CI on violations.
- [ ] T3.4 — Extension quarantine on inner-element throw; fall back to numeric tile without breaking neighbors.
- [ ] T3.5 — Cancel in-flight queries on unmount via `AbortController`.
- [ ] T3.6 — Reflect `data-pyc-metric-tile-state="ok|warn|crit|error"`.
- [ ] T3.7 — Sphinx authoring doc: tag contract, attributes, properties, events, slots, tokens, a11y, extension authoring guide.
- [ ] T3.8 — Verify no hard-coded colors / hex / absolute font sizes in `styles.css`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (stable unit formatter), Property 2 (monotone threshold selection), Property 3 (idempotent extension dispatch) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 9 scenario — dashboard composes 8 tiles of mixed kinds; all refresh within cadence; one tile errors, the rest keep refreshing.
- [ ] TT-4 — Extension-point test: ship an out-of-tree `AcmeSloBurnRateTile` (`kindId="slo-burn-rate"`); assert bundle loads and inner element renders with forwarded attributes.
- [ ] TT-5 — Browser E2E (Playwright-style): open a dashboard page, verify sparkline redraws on refresh, gauge colors flip when a threshold crosses, drilldown click emits `pyc-metric-tile-drilldown`.
- [ ] TT-6 — Quarantine test: extension inner element throws in `connectedCallback`; parent falls back to numeric and quarantine flag is set for the instance.
- [ ] TT-7 — Abort-on-unmount test: remove the element during an in-flight query; abort fires and no state update after unmount.

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
