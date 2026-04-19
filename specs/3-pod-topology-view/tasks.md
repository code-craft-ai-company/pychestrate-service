# 3-pod-topology-view — Tasks

## Milestones

- **M1 — Skeleton:** REST endpoint returns a composed `TopologyGraph`
  from three table reads; basic ETag; default renderer hints.
- **M2 — Core Behavior:** Extension-contributed renderer hints,
  divergence marking, `If-None-Match` handling, permission filtering,
  rate limit.
- **M3 — Hardening:** Partial-composition degradation, rescan cache
  invalidation, metrics, perf, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — DTOs `TopologyMember`, `TopologyLink`, `RendererHint`,
  `TopologyGraph` as frozen dataclasses.
- [ ] T1.2 — Implement `compose_topology` as a pure function reading
  definition version + registration + lifecycle rows.
- [ ] T1.3 — Implement `compute_etag` as SHA256 of canonical
  `(version, report_hash, state)` tuple.
- [ ] T1.4 — Implement REST router with `GET .../topology`, RBAC
  `pod.topology.read`.
- [ ] T1.5 — Ship built-in `GenericRenderer` (fallback) and two
  reference renderers (`LinuxHostRenderer`, `NetworkSwitchRenderer`).
- [ ] T1.6 — `load_renderer_hints` builds a map from extension host
  output at startup.

### M2 — Core Behavior

- [ ] T2.1 — `PodMemberRendererExtension(ResourceExtension)` class
  with `member_kind_name`, `tag_name`, `icon_ref`, `bundle_path`.
- [ ] T2.2 — Resolve renderer precedence: lowest `PRECEDENCE` wins per
  kind; emit `pychestrate_pod_topology_renderer_conflict` on conflicts.
- [ ] T2.3 — Implement divergence marking (symmetric difference of
  definition/report member names) with `divergence_reason` strings.
- [ ] T2.4 — `If-None-Match` handling returning 304.
- [ ] T2.5 — Filter `confidential`-tagged members when caller lacks
  `pod.topology.read.confidential`.
- [ ] T2.6 — Rate limit 30 rpm per caller.
- [ ] T2.7 — Ship remaining in-tree renderers (`WindowsHostRenderer`,
  `SerialConsoleRenderer`, `PduRenderer`).

### M3 — Hardening

- [ ] T3.1 — Graceful degradation: when registration row read fails,
  set `partial=true` and return a definition-only graph.
- [ ] T3.2 — Invalidate renderer cache on
  `entity.extension.host_rescan`.
- [ ] T3.3 — Emit all metrics in design.md Observability.
- [ ] T3.4 — Trace span `pod_topology.compose`.
- [ ] T3.5 — Perf validation: p99 <= 75 ms warm, <= 200 ms cold with a
  64-member spec.
- [ ] T3.6 — Sphinx docs for the REST endpoint, composer, and renderer
  extension base class.

## Test Tasks

- [ ] TT-1 — Unit tests per EARS clause in Requirements 1-3.
- [ ] TT-2 — Hypothesis tests for Property 1 (composer purity),
  Property 2 (ETag equivalence classes), Property 3 (divergence
  symmetric-difference).
- [ ] TT-3 — Integration test: pod in `ready` with 8 members, 12 links;
  divergence injected (one extra reported member); endpoint returns
  correct divergence flag and lifecycle_state.
- [ ] TT-4 — Extension-point test: out-of-tree `PacketCaptureRenderer`
  at `PRECEDENCE=60` for a custom member kind is loaded and returned in
  `renderer_hints`.
- [ ] TT-5 — Conditional response test: stable `ETag` yields 304;
  lifecycle change yields new `ETag` and 200.
- [ ] TT-6 — Confidential filter test: caller without
  `pod.topology.read.confidential` sees no confidential-tagged
  members.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] `PodMemberRendererExtension` has five in-tree references plus one
  test-only override.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 2 in
  specs/implementation-plan.md.
