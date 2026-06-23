# 9-run-detail-ui — Tasks

## Milestones

- **M1 — Skeleton:** `<pyc-run-detail>` registered, fetches run context, renders header + three panes `<pyc-result-viewer>`, `<pyc-log-stream>`, `<px-artifact-browser>`, themed via tokens.
- **M2 — Core Behavior:** State SSE subscription + aggregated reconnect banner, cross-pane selection bridge, artifact preview right-rail, cancel / requeue-failing actions, terminal-state transitions.
- **M3 — Hardening:** Property tests, client metrics, a11y, help dialog, deep-link support, Sphinx docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/ccai/pychestrate/webservice/webinterface/components/pyc-run-detail/` with TypeScript build wiring.
- [ ] T1.2 — Implement `pyc-run-detail.ts::PycRunDetail` with observed attributes `run-id`, `default-pane`, `aria-label`.
- [ ] T1.3 — Implement `transport/run-context-transport.ts` fetching `/api/v1/runs/{run_id}/context`.
- [ ] T1.4 — Implement `run-header.ts` rendering run identity, state badge, timing.
- [ ] T1.5 — Instantiate `<pyc-result-viewer>`, `<pyc-log-stream>`, `<px-artifact-browser>` with shared `run-id`.
- [ ] T1.6 — Author `styles.css` referencing `--pyc-run-detail-*` tokens, multi-line per AGENTS.md.
- [ ] T1.7 — Mount `GET /runs/<id>` server-side shell and serve bundle at `/ui/components/pyc-run-detail/pyc-run-detail.js`.

### M2 — Core Behavior

- [ ] T2.1 — Subscribe to `/api/v1/runs/{run_id}/state.stream` and update header state badge; emit `pyc-run-detail-state-changed`.
- [ ] T2.2 — Implement `stream-status-aggregator.ts` consolidating pane reconnect events into a single header banner.
- [ ] T2.3 — Implement `cross-pane-bridge.ts` forwarding `pyc-result-viewer-select` into `log.jumpToSequence` and artifact-browser path filter.
- [ ] T2.4 — Implement `preview-controller.ts` for the right-rail artifact preview mount/unmount flow.
- [ ] T2.5 — Implement Cancel action (POST `:cancel` with reason) gated by `run.cancel`.
- [ ] T2.6 — Implement Requeue-Failing action (POST `:requeue_failing`) gated by permission.
- [ ] T2.7 — Implement Open-Compare affordance routing to `6-compare-runs`.
- [ ] T2.8 — Handle terminal-state transition: switch result viewer to terminal doc, log stream out of live mode, emit `pyc-run-detail-terminal`.
- [ ] T2.9 — Implement keyboard handler (`Ctrl+1/2/3`, `Shift+C`, `Shift+R`, `?`, `Esc`).

### M3 — Hardening

- [ ] T3.1 — Beacon client metrics per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: page TTI p95 < 600 ms, context fetch p95 < 150 ms, inter-pane forward p95 < 10 ms, preview mount p95 < 500 ms. Fail CI on regression.
- [ ] T3.3 — Axe audit: `role="main"`, per-pane `role="region"`, header `role="banner"`, preview focus trap, focus ring; fail CI on violations.
- [ ] T3.4 — Implement `help-dialog.ts` with focus trap and full keybinding list.
- [ ] T3.5 — Deep-link support: parse `?node=<path>&artifact=<relpath>` and pre-drive selection and preview.
- [ ] T3.6 — Sphinx authoring doc: page composition, event contracts, keybindings, observability.
- [ ] T3.7 — Verify no hard-coded colors / hex / absolute font sizes in `styles.css`.
- [ ] T3.8 — Preview fallback to `<px-artifact-generic-download>` on renderer mount failure with banner.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (idempotent selection forwarding), Property 2 (single-voiced reconnect banner), Property 3 (state-machine-driven header) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 5 scenario — open a running testbase run, watch live progress, select a failing test, log jumps, artifact preview mounts with the right renderer; cancel succeeds.
- [ ] TT-4 — Browser E2E (Playwright-style): navigate to `/runs/<id>`, keyboard-select a failing node with `ArrowDown`/`Enter`, verify log jump and artifact path update, open an artifact preview, press `Esc` to close and verify focus returns.
- [ ] TT-5 — Extension-integration test: install a custom `ArtifactRendererExtension`; clicking a matching artifact mounts the extension's custom element in the preview panel; on bundle failure, fallback renderer mounts and a banner appears.
- [ ] TT-6 — Reconnect consolidation test: simulate result viewer + log stream disconnecting at different times; only one banner is visible at a time with the most-severe reason.
- [ ] TT-7 — Deep-link test: load `/runs/<id>?node=suite/A/test_b&artifact=artifacts/smoke/log.txt`; verify initial selection and preview mount.

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
