# 7-resource-metrics — Tasks

## Milestones

- **M1 — Skeleton:** Wait-time and pool-size metrics, `ResourceMetricResolver`, basic sampler tick, first end-to-end emit.
- **M2 — Core Behavior:** Utilization ratio, conflict/quarantine counters with enum attribution, forced-release counter, health probe duration metric.
- **M3 — Hardening:** Sampler overrun handling, rule registry refresh on `extension.reloaded`, self-metrics/logs/traces, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/ccai/pychestrate/webservice/metrics/domains/resource/` package per design.md.
- [ ] T1.2 — Implement `ResourcePoolSizeMetric` and `ResourceReservationWaitMetric` under `source/site/ccai/extensions/pychestrate/metric_definition/resource/`.
- [ ] T1.3 — Implement `resolver.py::ResourceMetricResolver.on_reservation_created` → wait metric.
- [ ] T1.4 — Implement `sampler.py::UtilizationSampler.tick()` that snapshots pool state and emits `pool_size` gauges.
- [ ] T1.5 — Wire subscription `entity.reservation.created` and start the sampler at service boot.
- [ ] T1.6 — Verify end-to-end: one reservation + one sampler tick populate both metrics.

### M2 — Core Behavior

- [ ] T2.1 — Implement `ResourcePoolUtilizationMetric` and emit from the sampler per tick.
- [ ] T2.2 — Implement `ResourceConflictMetric` and `resolver.on_conflict_detected` with rule-name validation against `ConflictRuleRegistry`.
- [ ] T2.3 — Implement `ResourceQuarantineMetric` and `resolver.on_resource_quarantined`; wire `truncate_reason` at 120 bytes.
- [ ] T2.4 — Implement `ResourceForcedReleaseMetric` and `resolver.on_reservation_forced_released` with `source` enum.
- [ ] T2.5 — Implement `ResourceHealthProbeDurationMetric` and `resolver.on_health_probe_completed`.
- [ ] T2.6 — Wire remaining subscriptions: `entity.conflict.detected`, `entity.resource.quarantined`, `entity.reservation.forced_released`, `entity.resource.health_probe_completed`.
- [ ] T2.7 — Subscribe to `extension.reloaded` to refresh `conflict_rule_allow_list`.
- [ ] T2.8 — Emit pool utilization of `0.0` for zero-size pools (absence is ambiguous).

### M3 — Hardening

- [ ] T3.1 — Handle sampler overrun: log `pychestrate.resource_metrics.sampler_overrun` and skip to next tick when overrun exceeds `utilization_sample_overrun_warn_seconds`.
- [ ] T3.2 — Catch `InventoryTransientError` in sampler; single 500 ms retry then skip.
- [ ] T3.3 — Emit self-metrics `pychestrate_resource_metrics_emit_duration_seconds`, `pychestrate_resource_metrics_sampler_overrun_total`, `pychestrate_resource_metrics_unregistered_conflict_rule_total`, `pychestrate_resource_metrics_sampler_tick_duration_seconds`, `pychestrate_resource_metrics_pool_snapshot_error_total`.
- [ ] T3.4 — Emit OTel spans per design.md Observability.
- [ ] T3.5 — Benchmark NFR-1: per-event emit p99 < 5 ms; 10 000-resource sampler pass p99 < 400 ms.
- [ ] T3.6 — Sphinx docs for the resource metric catalog.
- [ ] T3.7 — Wire `1-audit-log` sidecar for raw quarantine reasons; gate via `audit.read:sidecar`.
- [ ] T3.8 — Rate-limit unregistered-rule log to once-per-hour-per-rule.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (utilization in range), Property 2 (wait non-negativity), Property 3 (sampler tick bound) at 1000 cases each.
- [ ] TT-3 — Integration test: create 3 pools of varying size, generate reservation + conflict + quarantine events, assert all metric families populate correctly.
- [ ] TT-4 — Extension-point test: test-only `MetricDefinitionExtension` contributes `pychestrate_resource_custom_total` and receives events.
- [ ] TT-5 — Overrun test: mock inventory that blocks for 45 s on a 30 s interval; assert tick is skipped, overrun metric increments, service recovers.
- [ ] TT-6 — Unregistered-rule test: `entity.conflict.detected` with `rule="bogus"` emits counter with `rule="unregistered"` + one log.
- [ ] TT-7 — Transient error test: mock inventory raises `InventoryTransientError` once then succeeds; sampler retries and completes the tick.

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
