# 7-pod-metrics — Tasks

## Milestones

- **M1 — Skeleton:** Bring-up/tear-down metrics with pairing map, lifecycle result counter, first end-to-end emit on a synthetic lifecycle.
- **M2 — Core Behavior:** Active-count sampler, failure classification, dynamic/static label uniformity, boot reconstruction.
- **M3 — Hardening:** LRU eviction + counter, enum guard for `failure_class`, self-metrics/logs/traces, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/metrics/domains/pod/` package per design.md.
- [ ] T1.2 — Implement `PodBringupMetric`, `PodTeardownMetric`, `PodLifecycleResultMetric` under `source/site/automojo/extensions/pychestrate/metric_definition/pod/`.
- [ ] T1.3 — Implement `resolver.py::PodMetricResolver` with `pairing_map`, `on_pod_state_changed`.
- [ ] T1.4 — Wire `entity.pod.state_changed` subscription.
- [ ] T1.5 — Verify end-to-end: synthetic pod lifecycle `bringing_up → ready → running → tearing_down → torn_down` emits both duration metrics once each.

### M2 — Core Behavior

- [ ] T2.1 — Implement `PodActiveCountMetric` and `sampler.py::PodActiveSampler.tick()` iterating `_active_pods`.
- [ ] T2.2 — Implement `on_pod_registered` / `on_pod_deregistered` to maintain the active-pod set.
- [ ] T2.3 — Implement `failure_classes.py::classify_failure` mapping upstream strings onto the closed enum; log `pychestrate.pod_metrics.unknown_failure_class` on fallback.
- [ ] T2.4 — Implement `PodFailureMetric` and emit on `bringing_up → failed` transition.
- [ ] T2.5 — Ensure `pod_kind` label present on every metric emit; `provisioner = "n/a"` for static pods.
- [ ] T2.6 — Implement `rebuild_pairing_from_registry()` at service start.
- [ ] T2.7 — Wire `entity.pod.registered`, `entity.pod.materialized`, `entity.pod.deregistered`, `entity.pod.torn_down` subscriptions.

### M3 — Hardening

- [ ] T3.1 — Enforce LRU eviction at `pod_pairing_max_entries` (default 20 000); emit `pychestrate_pod_metrics_pairing_evicted_total`.
- [ ] T3.2 — Increment `pychestrate_pod_metrics_unpaired_total{phase}` when terminal state arrives without matching pairing entry.
- [ ] T3.3 — Emit self-metrics `pychestrate_pod_metrics_emit_duration_seconds`, `pychestrate_pod_metrics_unpaired_total`, `pychestrate_pod_metrics_pairing_evicted_total`, `pychestrate_pod_metrics_active_sampler_tick_duration_seconds`.
- [ ] T3.4 — Emit OTel spans per design.md Observability.
- [ ] T3.5 — Benchmark NFR-1: per-event emit p99 < 5 ms; 10 000-pod sampler pass p99 < 150 ms.
- [ ] T3.6 — Sphinx docs for the pod metric catalog, with dynamic-vs-static query cookbook.
- [ ] T3.7 — Sanitize `template` label values through the shared truncation sanitizer.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (duration non-negativity), Property 2 (emit exclusivity per lifecycle), Property 3 (active count invariant) at 1000 cases each.
- [ ] TT-3 — Integration test: run 50 parallel pod lifecycles (mix of static + dynamic) and assert all metric families populate.
- [ ] TT-4 — Extension-point test: test-only `MetricDefinitionExtension` contributes `pychestrate_pod_custom_total`.
- [ ] TT-5 — Eviction test: force pairing map to capacity + 1; assert oldest entry evicted, counter increments, subsequent terminal event increments `unpaired_total`.
- [ ] TT-6 — Boot reconstruction test: 10 pods in `bringing_up` at boot; service restart; their eventual `ready` events still produce duration samples.
- [ ] TT-7 — Failure classification test: upstream event with `failure_class="martian"` maps to `UNKNOWN`, logs once.

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
