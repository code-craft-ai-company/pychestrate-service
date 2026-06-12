# 9-wc-pod-topology — Tasks

## Milestones

- **M1 — Skeleton:** `<pyc-pod-topology>` registered, fetches topology JSON, renders client + members with generic renderer and deterministic radial layout.
- **M2 — Core Behavior:** Hierarchical layout option, live state stream, renderer registry + extension bundle loading, selection + navigation events, in-tree reference renderers (linux-host, serial-console).
- **M3 — Hardening:** Property tests, client metrics, a11y audit, extension quarantine on failure, benchmarks, Sphinx docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/ccai/pychestrate/webservice/webinterface/components/pyc-pod-topology/` with TypeScript build wiring.
- [ ] T1.2 — Implement `pyc-pod-topology.ts::PycPodTopology` Custom Element with observed attributes `pod-id`, `layout`, `stream`, `metrics`, `aria-label`.
- [ ] T1.3 — Implement `transport/topology-transport.ts` fetching `/api/v1/pods/{pod_id}/topology.json`.
- [ ] T1.4 — Implement `layout/radial.ts` deterministic in member order.
- [ ] T1.5 — Implement in-tree `<pyc-pod-member-generic>` renderer and ship under its own component folder.
- [ ] T1.6 — Author `styles.css` referencing `--pyc-pod-topology-*` tokens, multi-line per AGENTS.md.
- [ ] T1.7 — Serve bundle at `/ui/components/pyc-pod-topology/pyc-pod-topology.js`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `layout/hierarchical.ts` with stable tie-breakers.
- [ ] T2.2 — Implement `renderer/registry.ts` loading `/api/v1/extensions/pod_member_renderers.json` and resolving by `PRECEDENCE`.
- [ ] T2.3 — Implement `renderer/mount.ts::MemberMountController` with dynamic `import()` of extension bundles under `/ext/<ext-name>/bundle/...`.
- [ ] T2.4 — Ship in-tree reference renderers `<pyc-pod-member-linux-host>` and `<pyc-pod-member-serial-console>`.
- [ ] T2.5 — Implement SSE state stream subscription and in-place status + link recoloring.
- [ ] T2.6 — Implement selection, neighbor highlighting, and `pyc-pod-topology-select` / `pyc-pod-topology-navigate` events.
- [ ] T2.7 — Implement keyboard handler (Tab, ArrowLeft/Right, Enter, Space, Esc).
- [ ] T2.8 — Subscribe to `metrics.stream` only for renderers whose record has `liveMetrics: true`.
- [ ] T2.9 — Render visually-hidden live region and shadow `role="list"` mirror.

### M3 — Hardening

- [ ] T3.1 — Beacon client metrics per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: TTI p95 < 300 ms, layout p95 < 120 ms for 64 members, state update p95 < 6 ms, bundle load p95 < 100 ms. Fail CI on regression.
- [ ] T3.3 — Axe audit: `role="application"`, member `role="button"`, focus ring honored; fail CI on violations.
- [ ] T3.4 — Implement per-instance extension quarantine on renderer attach failure.
- [ ] T3.5 — Reflect `data-pyc-pod-topology-stream="connecting|open|reconnecting|disconnected"`.
- [ ] T3.6 — Sphinx authoring doc: tag contract, attributes, properties, events, slots, tokens, a11y, extension authoring guide.
- [ ] T3.7 — Verify no hard-coded colors / hex / absolute font sizes in `styles.css`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (deterministic layout under member-order permutation), Property 2 (stable precedence-ordered dispatch), Property 3 (idempotent state replay) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 8 scenario — dynamic pod materializes with 8 members spanning 4 kinds; topology view renders all nodes, state transitions flow through SSE.
- [ ] TT-4 — Extension-point test: register an out-of-tree `AcmeRfSigGenRenderer` (`PRECEDENCE=200`) matching `memberKind="rf-siggen"`; assert the element mounts the custom tag for matching members and falls back to generic on bundle load failure.
- [ ] TT-5 — Browser E2E (Playwright-style): open a staged pod, verify member nodes render, click one, assert `pyc-pod-topology-select` fires; take a member offline via the stub stream, assert link color flips to the degraded token.
- [ ] TT-6 — Quarantine test: a renderer throws during `connectedCallback`; element falls back to generic and marks extension quarantined for the rest of the instance; metrics counter reflects the error.
- [ ] TT-7 — Resilience test: disconnect the state stream mid-session; element reflects `data-pyc-pod-topology-stream="disconnected"` and recovers full state on reconnect.

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
