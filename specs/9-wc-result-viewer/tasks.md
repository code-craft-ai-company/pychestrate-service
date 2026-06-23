# 9-wc-result-viewer — Tasks

## Milestones

- **M1 — Skeleton:** `<pyc-result-viewer>` registered, fetches summary, renders a static tree from `testrun_results.json` for terminal runs.
- **M2 — Core Behavior:** JSOS streaming, incremental upsert, filters, expansion state persistence, keyboard navigation, artifact-open events, progress bar.
- **M3 — Hardening:** Row virtualisation above threshold, property tests, client metrics, a11y audit, benchmarks, Sphinx docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/ccai/pychestrate/webservice/webinterface/components/pyc-result-viewer/` with TypeScript build wiring.
- [ ] T1.2 — Implement `pyc-result-viewer.ts::PycResultViewer` Custom Element with observed attributes `run-id`, `filter`, `expand-failures`, `virtualize-threshold`, `stream-mode`, `aria-label`.
- [ ] T1.3 — Implement `result-transport.ts` fetching `testrun_summary.json` and rendering counters + progress bar.
- [ ] T1.4 — Implement `result-tree.ts` with `upsert`, `children`, and outline projection.
- [ ] T1.5 — Implement `styles.css` referencing `--pyc-result-viewer-*` tokens, multi-line per AGENTS.md.
- [ ] T1.6 — Render terminal `testrun_results.json` into the tree.
- [ ] T1.7 — Serve bundle at `/ui/components/pyc-result-viewer/pyc-result-viewer.js`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `jsos-parser.ts` tolerant of arbitrary chunk splits; incrementing `malformedCount` on bad lines.
- [ ] T2.2 — Stream integration: when `stream-mode="auto"` and run not terminal, open JSOS stream; upsert records per `requestAnimationFrame`.
- [ ] T2.3 — Auto-expand failing branches when `expand-failures` is set.
- [ ] T2.4 — Persist expansion state in `sessionStorage` keyed by `pyc:rv:<run-id>`.
- [ ] T2.5 — Implement filter set parsing and `pyc-result-viewer-filter-changed` emission.
- [ ] T2.6 — Implement keyboard handler (ArrowUp/Down/Left/Right, Home/End, Enter, `*`, `/`, Esc).
- [ ] T2.7 — Emit `pyc-result-viewer-artifact-open` from per-node links.
- [ ] T2.8 — Surface `slot="empty"`, `slot="summary-right"`, `slot="stream-error"`, `slot="node-badge-extra"`.
- [ ] T2.9 — Render visually-hidden live region announcing failing transitions and filter counts.

### M3 — Hardening

- [ ] T3.1 — Implement `virtual-outline.ts`; switch on when outline size > `virtualize-threshold`.
- [ ] T3.2 — Beacon client metrics per design.md Observability.
- [ ] T3.3 — Benchmark NFR-1: TTI p95 < 250 ms, append p95 < 6 ms per batch, 50 000-record render p95 < 3 s, toggle p95 < 16 ms. Fail CI on regression.
- [ ] T3.4 — Axe audit: `role="tree"`, `role="treeitem"`, `aria-level`, `aria-expanded`, `aria-selected`, focus ring; fail CI on violations.
- [ ] T3.5 — Handle 401/403 with a distinct `slot="stream-error"` variant; 404 emits `pyc-result-viewer-run-missing`.
- [ ] T3.6 — Reject streams > 256 MiB cumulative content length; fall back to terminal document when available.
- [ ] T3.7 — Sphinx authoring doc: tag contract, attributes, properties, events, slots, tokens, a11y, examples.
- [ ] T3.8 — Verify no hard-coded colors, hex values, or absolute `px` font sizes in `styles.css`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (O(M) append cost across 1000 streams up to 100 000 records), Property 2 (idempotent re-render on attribute reset), Property 3 (chunk-boundary-independent JSOS parsing) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 5 scenario — ingest a fixture testbase run with 5 000 tests, verify summary TTI, streamed incremental render, filter to `failed,errored` shrinks outline, artifact event fires when link is activated.
- [ ] TT-4 — Browser E2E (Playwright-style): open a staged run, verify progress bar fills, failing branches auto-expand, `ArrowDown`/`Enter` selects a node, filter chip updates `pyc-result-viewer-filter-changed`, dark mode toggles without reload.
- [ ] TT-5 — Security test: assert node name containing `<script>` renders as text; artifact events carry only the path, never a raw URL.
- [ ] TT-6 — Resilience test: terminate stream mid-flight; element shows `slot="stream-error"` and retains already-appended nodes.
- [ ] TT-7 — Accessibility screen-reader snapshot: node status announcements land in the live region.

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
