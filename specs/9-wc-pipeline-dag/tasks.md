# 9-wc-pipeline-dag — Tasks

## Milestones

- **M1 — Skeleton:** `<pyc-pipeline-dag>` registered, fetches graph JSON, renders static SVG with deterministic layered layout, themed via tokens.
- **M2 — Core Behavior:** Live status stream, matrix expansion, zoom/pan/focus, keyboard navigation, selection highlighting, cycle detection with condensation render.
- **M3 — Hardening:** Property tests, client metrics, performance benchmarks, a11y audit, watchdog, Sphinx docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/ccai/pychestrate/webservice/webinterface/components/pyc-pipeline-dag/` with TypeScript build wiring.
- [ ] T1.2 — Implement `pyc-pipeline-dag.ts::PycPipelineDag` Custom Element with observed attributes `pipeline-run-id`, `direction`, `expand-matrix`, `zoom-min`, `zoom-max`, `initial-zoom`, `stream`, `aria-label`.
- [ ] T1.3 — Implement `layout/sugiyama.ts` with deterministic layer assignment, crossing minimisation, and stable tie-breakers keyed by `nodeId`.
- [ ] T1.4 — Implement `renderer/svg-renderer.ts` drawing nodes and edges with per-step-kind shapes.
- [ ] T1.5 — Author `styles.css` referencing `--pyc-pipeline-dag-*` tokens, multi-line per AGENTS.md.
- [ ] T1.6 — Fetch `graph.json` and emit `pyc-pipeline-dag-graph-loaded`.
- [ ] T1.7 — Serve bundle at `/ui/components/pyc-pipeline-dag/pyc-pipeline-dag.js`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `transport/status-transport.ts` SSE + WebSocket with exponential backoff and jitter.
- [ ] T2.2 — Update node badges on status events without re-laying out; throttle via `requestAnimationFrame`.
- [ ] T2.3 — Implement `layout/cycle-detector.ts` (Tarjan SCC) and render condensation super-node when cycles exist.
- [ ] T2.4 — Implement zoom / pan with cursor-anchored zoom and keyboard `R` reset / `F` fit-subgraph.
- [ ] T2.5 — Implement selection + transitive upstream/downstream highlighting.
- [ ] T2.6 — Implement matrix super-node expansion via `toggleMatrix` and `expand-matrix` attribute.
- [ ] T2.7 — Implement keyboard handler (Tab, ArrowLeft/Right, Enter, M, F, R, Esc).
- [ ] T2.8 — Surface `slot="toolbar"`, `slot="legend"`, `slot="graph-unavailable"`, `slot="node-extra"`.
- [ ] T2.9 — Render visually-hidden live region and topologically-ordered hidden `role="list"` mirror.
- [ ] T2.10 — Emit `pyc-pipeline-dag-navigate` secondary actions and `pyc-pipeline-dag-select` on click.

### M3 — Hardening

- [ ] T3.1 — Beacon client metrics per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: layout p95 < 350 ms for 500 nodes / 1 000 edges, status update p95 < 8 ms, 60 fps pan/zoom, TTI p95 < 400 ms. Fail CI on regression.
- [ ] T3.3 — Axe audit: `role="application"`, node `role="button"`, focus ring honored; fail CI on violations.
- [ ] T3.4 — Layout watchdog: 5 s wall-clock cap; exceeding emits `pyc-pipeline-dag-error`.
- [ ] T3.5 — Enforce `matrix-expansion-cap` (default 5 000).
- [ ] T3.6 — Reflect `data-pyc-pipeline-dag-stream="connecting|open|reconnecting|disconnected"`.
- [ ] T3.7 — Sphinx authoring doc: tag contract, attributes, properties, events, slots, tokens, a11y, examples.
- [ ] T3.8 — Verify no hard-coded colors / hex / absolute font sizes in `styles.css`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (deterministic acyclic layout), Property 2 (render-idempotent status replay), Property 3 (cycle-tolerant render) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 6 scenario — a pipeline with 5 parallel build shards and a fan-in deploy step streams status from pending → running → passed; DAG reflects live state without jumping.
- [ ] TT-4 — Browser E2E (Playwright-style): open a staged pipeline run, click a node, assert `pyc-pipeline-dag-select` fires with correct payload; press `F` and verify viewport centers on subgraph; press `R` and verify full-fit.
- [ ] TT-5 — Cycle-tolerance test: feed a graph with a cycle; element emits `pyc-pipeline-dag-error` and renders the condensation without throwing.
- [ ] TT-6 — Reconnect test: disconnect the status stream mid-run; element displays disconnected state and recovers all node statuses on reconnect.
- [ ] TT-7 — Determinism test: layout the same graph 100 times in independent contexts; every coordinate vector is byte-identical.

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
