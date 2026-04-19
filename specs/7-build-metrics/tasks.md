# 7-build-metrics — Tasks

## Milestones

- **M1 — Skeleton:** `MetricDefinitionExtension` subclasses for duration, result, queue; `BuildMetricResolver` with queue-state map; first metric writes visible in `0-timeseries-backend`.
- **M2 — Core Behavior:** Cache-hit-ratio metric, artifact-bytes metric, oversized-artifact event, per-project branch-label policy, label sanitization.
- **M3 — Hardening:** Cardinality guards, LRU eviction + counter, self-metrics/logs/traces, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/metrics/domains/build/` package per design.md.
- [ ] T1.2 — Implement `resolver.py::BuildMetricResolver` with `on_build_queued`, `on_build_started`, `on_build_completed` stubs.
- [ ] T1.3 — Implement `source/site/automojo/extensions/pychestrate/metric_definition/build/duration.py::BuildDurationMetric` (histogram; buckets `[1,5,15,30,60,120,300,600,1800,3600]`).
- [ ] T1.4 — Implement `BuildQueueMetric` (histogram; buckets `[0.1,1,5,15,60,300,900]`).
- [ ] T1.5 — Implement `BuildResultMetric` (counter; `result` ∈ `{success,failure,cancelled,timeout}`).
- [ ] T1.6 — Wire subscriptions for `entity.build.queued`, `entity.build.started`, `entity.build.completed` to `BuildMetricResolver` via `MetricDefinitionExtension.subscriptions`.
- [ ] T1.7 — Verify end-to-end: a synthetic build lifecycle emits three samples visible in `TimeseriesFacade`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `BuildCacheHitRatioMetric` gauge; skip emit when `hits + misses == 0`.
- [ ] T2.2 — Implement `BuildArtifactBytesMetric` histogram; subscribe to `entity.build.artifact_published`.
- [ ] T2.3 — Emit `entity.build.artifact.oversized` when `bytes_total > artifact_alert_size_bytes`.
- [ ] T2.4 — Implement `labels.py::resolve_branch_label` with `raw` and `collapse_by_pattern` modes (defaulting to project setting).
- [ ] T2.5 — Implement `labels.py::sanitize_label_value` — truncate to 200 bytes + deterministic sha256 suffix.
- [ ] T2.6 — Wire artifact type classification through `ArtifactClassifierRegistry`; fall back to `other`.
- [ ] T2.7 — Skip emit + increment `dropped_total{reason="missing_project"}` when `project_id` unresolvable.

### M3 — Hardening

- [ ] T3.1 — Implement bounded `queue_state` with LRU eviction at `queue_state_max_entries` (default 50 000).
- [ ] T3.2 — Enforce per-metric cardinality guard at `cardinality_max_per_metric` (default 100 000); drop sample, increment `pychestrate_metrics_ingest_dropped_total{reason="cardinality_exceeded"}`.
- [ ] T3.3 — Rate-limit `pychestrate.build_metrics.cardinality_exceeded` log to once-per-hour-per-metric.
- [ ] T3.4 — Emit self-metrics `pychestrate_build_metrics_emit_duration_seconds`, `pychestrate_build_metrics_dropped_total`, `pychestrate_build_metrics_queue_state_size`.
- [ ] T3.5 — Emit OTel spans per design.md Observability.
- [ ] T3.6 — Benchmark NFR-1: emit p99 < 5 ms per build event.
- [ ] T3.7 — Sphinx docs for the build metric catalog (names, labels, buckets, meaning).

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (duration non-negativity), Property 2 (cache ratio in range), Property 3 (queue time ordering) at 1000 cases each.
- [ ] TT-3 — Integration test: drive `6-build-orchestration` through a queued→started→completed lifecycle with cache report; assert all five metric families populate.
- [ ] TT-4 — Extension-point test: test-only `MetricDefinitionExtension` with a new `pychestrate_build_custom_total` registers cleanly and receives events alongside the built-in catalog.
- [ ] TT-5 — Cardinality test: generate 110 000 unique `(project,pipeline,branch)` triples and assert cardinality guard drops the tail.
- [ ] TT-6 — Policy test: branch `refs/pull/42/head` collapses to `pull-request` under `collapse_by_pattern` policy, stays raw under `raw`.
- [ ] TT-7 — Oversized artifact test: `bytes_total = 5 GiB` triggers `entity.build.artifact.oversized` and the histogram sample still emits.

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
